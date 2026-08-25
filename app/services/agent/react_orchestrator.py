"""ReAct orchestration for Tutor Agent tool use."""

from __future__ import annotations

import hashlib
import inspect
import json
import time
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.clients.llm_client_pool import get_llm_client
from app.config import LLMConfig
from app.db import trace_db
from app.schemas.chat import Source, ToolCallTrace, ToolTrace
from app.services import timings
from app.services.memory_settings import (
    MAX_TOOL_FAILURES,
    MAX_TOOL_ROUNDS,
    TOOL_OBSERVATION_MAX_CHARS,
)
from app.services.agent.tools.executor import ToolExecutor
from app.services.agent.tools.registry import ToolRegistry
from app.services.agent.model_registry import ModelSpec, resolve_model
from app.services.web_search_settings import WEB_SEARCH_MAX_CALLS_PER_CHAT


WEB_SEARCH_TOOL_NAME = "web_search"
RAG_TOOL_NAME = "search_learning_notes"
JD_TOOL_NAME = "search_job_descriptions"
ATTACHMENT_TOOL_NAME = "search_attachments"


def _tool_schema_name(tool: Any) -> str:
    """Extract the function name from one OpenAI tool schema object."""

    if isinstance(tool, dict):
        function = tool.get("function")
        if isinstance(function, dict):
            return str(function.get("name") or "")
    return ""


def _note_source_title(source: str, title_path: Any) -> str:
    """Build a public note title without exposing storage internals."""

    title = str(title_path or "").strip()
    if title:
        return f"{source} · {title}"
    return source


@dataclass
class StreamEvent:
    """An event yielded during streaming ReAct execution."""

    type: str  # "tool_call", "tool_result", "token", "done", "error"
    data: dict[str, Any]


@dataclass(frozen=True)
class _ModelRuntime:
    """Resolved request model, client, and provider-specific parameters."""

    client: OpenAI
    api_model: str
    trace_model: str
    request_params: dict[str, Any]


@dataclass
class _RunState:
    """Request-scoped tool budgets and evidence state."""

    web_search_calls: int = 0
    next_evidence_number: int = 1
    ledger: dict[str, Source] = field(default_factory=dict)
    evidence_id_by_url: dict[str, str] = field(default_factory=dict)
    rag_enabled: bool = True
    web_search_enabled: bool = True
    next_note_number: int = 1
    note_id_by_fingerprint: dict[str, str] = field(default_factory=dict)
    attachment_ids: list[str] = field(default_factory=list)
    next_jd_number: int = 1
    jd_id_by_fingerprint: dict[str, str] = field(default_factory=dict)


@dataclass
class _RoundResult:
    """Accumulated output from one model round."""

    content: str = ""
    reasoning: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class ReactOrchestrator:
    """Runs the model-tool-observation loop and returns the final model text."""

    def __init__(
        self,
        config: LLMConfig | None = None,
        client: OpenAI | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        max_steps: int = MAX_TOOL_ROUNDS,
        max_failures: int = MAX_TOOL_FAILURES,
        max_observation_chars: int = TOOL_OBSERVATION_MAX_CHARS,
    ) -> None:
        """保存模型客户端、工具注册表、工具执行器和最大 ReAct 步数。"""

        self.config = config
        self.client = client
        self.tool_registry = tool_registry or ToolRegistry()
        self.tool_executor = tool_executor or ToolExecutor(self.tool_registry)
        self.max_steps = max_steps
        self.max_failures = max_failures
        self.max_observation_chars = max_observation_chars

    def run(
        self,
        messages: list[ChatCompletionMessageParam],
        force_web_search: bool = False,
        web_search_enabled: bool = True,
        rag_enabled: bool = True,
        force_rag: bool = False,
        attachment_ids: list[str] | None = None,
        model_spec: ModelSpec | None = None,
        execution_context=None,
    ) -> tuple[str, ToolTrace]:
        """Execute one request with an isolated model selection."""

        return self._run(
            messages,
            force_web_search=force_web_search,
            web_search_enabled=web_search_enabled,
            rag_enabled=rag_enabled,
            force_rag=force_rag,
            attachment_ids=attachment_ids,
            model_spec=model_spec,
            execution_context=execution_context,
        )

    def _run(
        self,
        messages: list[ChatCompletionMessageParam],
        force_web_search: bool = False,
        web_search_enabled: bool = True,
        rag_enabled: bool = True,
        force_rag: bool = False,
        attachment_ids: list[str] | None = None,
        model_spec: ModelSpec | None = None,
        execution_context=None,
    ) -> tuple[str, ToolTrace]:
        """执行最多 max_steps 步的 ReAct 工具循环。"""

        working_messages: list[ChatCompletionMessageParam] = [*messages]
        tool_call_traces: list[ToolCallTrace] = []
        run_state = _RunState(
            rag_enabled=rag_enabled,
            web_search_enabled=web_search_enabled,
            attachment_ids=list(attachment_ids or []),
        )
        failure_count = 0
        first_model_round = 1

        if force_rag:
            timings.set_meta("forced", True)
            timings.set_meta("round_number", 0)
            working_messages, forced_trace = self._execute_forced_learning_notes(
                working_messages,
                run_state,
                execution_context=execution_context,
            )
            timings.set_meta("forced", False)
            tool_call_traces.append(forced_trace)
            failure_count += int(not forced_trace.ok)
            first_model_round += 1

        if force_web_search:
            timings.set_meta("forced", True)
            timings.set_meta("round_number", 0)
            working_messages, forced_trace = self._execute_forced_web_search(
                working_messages,
                run_state,
                round_number=first_model_round,
                execution_context=execution_context,
            )
            timings.set_meta("forced", False)
            tool_call_traces.append(forced_trace)
            failure_count += int(not forced_trace.ok)
            first_model_round += 1

        # 工具调用前已经输出的正文也要保留：跨轮可见正文按 "\n\n" 分隔拼接，
        # 与流式路径的 token 拼接保持一致，避免标题与前文粘连。
        visible_parts: list[str] = []
        for round_number in range(first_model_round, self.max_steps + 1):
            timings.bump("react_rounds")
            timings.set_meta("round_number", round_number)
            active_tool_choice = self._resolve_tool_choice(run_state, round_number)
            model_message = self._call_model_with_request_state(
                working_messages,
                tool_choice=active_tool_choice,
                model_spec=model_spec,
                execution_context=execution_context,
                rag_enabled=rag_enabled,
                web_search_enabled=web_search_enabled,
            )
            tool_calls = self._message_tool_calls(model_message)
            round_content = self._message_content(model_message)

            if not tool_calls:
                raw_reply = self._join_visible_parts(
                    visible_parts,
                    round_content,
                )
                if not raw_reply:
                    raise RuntimeError("模型没有返回内容")

                return raw_reply, ToolTrace(
                    used=bool(tool_call_traces),
                    calls=tool_call_traces,
                    ledger=run_state.ledger,
                )

            if round_content:
                visible_parts.append(round_content)

            working_messages, step_traces = self._build_messages_with_tool_results(
                messages=working_messages,
                first_message=model_message,
                tool_calls=tool_calls,
                round_number=round_number,
                run_state=run_state,
                execution_context=execution_context,
            )
            tool_call_traces.extend(step_traces)
            failure_count += sum(1 for trace in step_traces if not trace.ok)

            if failure_count >= self.max_failures:
                break

        timings.set_meta("round_number", None)
        raw_reply = self._join_visible_parts(
            visible_parts,
            self._call_model_for_request(
                working_messages,
                model_spec=model_spec,
            ),
        )
        if not raw_reply:
            raise RuntimeError("模型没有返回内容")

        return raw_reply, ToolTrace(
            used=bool(tool_call_traces),
            calls=tool_call_traces,
            ledger=run_state.ledger,
        )

    @staticmethod
    def _join_visible_parts(
        visible_parts: list[str],
        final_part: str | None,
    ) -> str:
        """按工具轮次边界拼接可见正文，避免前后正文粘连。"""

        parts = [part for part in [*visible_parts, final_part or ""] if part]
        return "\n\n".join(parts)

    def run_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        force_web_search: bool = False,
        web_search_enabled: bool = True,
        rag_enabled: bool = True,
        force_rag: bool = False,
        attachment_ids: list[str] | None = None,
        model_spec: ModelSpec | None = None,
        execution_context=None,
    ) -> Generator[StreamEvent, None, tuple[str, ToolTrace]]:
        """Execute one streaming request with an isolated model selection."""

        return (
            yield from self._run_stream(
                messages,
                force_web_search=force_web_search,
                web_search_enabled=web_search_enabled,
                rag_enabled=rag_enabled,
                force_rag=force_rag,
                attachment_ids=attachment_ids,
                model_spec=model_spec,
                execution_context=execution_context,
            )
        )

    def _run_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        force_web_search: bool = False,
        web_search_enabled: bool = True,
        rag_enabled: bool = True,
        force_rag: bool = False,
        attachment_ids: list[str] | None = None,
        model_spec: ModelSpec | None = None,
        execution_context=None,
    ) -> Generator[StreamEvent, None, tuple[str, ToolTrace]]:
        """Execute the ReAct loop, yielding StreamEvents for progress.

        Yields:
            StreamEvent for tool calls, tool results, and final tokens.

        Returns:
            Tuple of (raw_reply, ToolTrace) — accessible via generator.return_value.
        """

        working_messages: list[ChatCompletionMessageParam] = [*messages]
        tool_call_traces: list[ToolCallTrace] = []
        run_state = _RunState(
            rag_enabled=rag_enabled,
            web_search_enabled=web_search_enabled,
            attachment_ids=list(attachment_ids or []),
        )
        failure_count = 0
        first_model_round = 1

        if force_rag:
            yield StreamEvent(type="tool_call", data={"tool": RAG_TOOL_NAME, "args": {"query": "..."}, "status": "running"})
            timings.set_meta("forced", True)
            timings.set_meta("round_number", 0)
            working_messages, forced_trace = self._execute_forced_learning_notes(
                working_messages,
                run_state,
                execution_context=execution_context,
            )
            timings.set_meta("forced", False)
            tool_call_traces.append(forced_trace)
            failure_count += int(not forced_trace.ok)
            first_model_round += 1
            yield StreamEvent(type="tool_result", data={"tool": RAG_TOOL_NAME, "result": {"ok": forced_trace.ok}})

        if force_web_search:
            yield StreamEvent(type="tool_call", data={"tool": WEB_SEARCH_TOOL_NAME, "args": {"query": "..."}, "status": "running"})
            timings.set_meta("forced", True)
            timings.set_meta("round_number", 0)
            working_messages, forced_trace = self._execute_forced_web_search(
                working_messages,
                run_state,
                round_number=first_model_round,
                execution_context=execution_context,
            )
            timings.set_meta("forced", False)
            tool_call_traces.append(forced_trace)
            failure_count += int(not forced_trace.ok)
            first_model_round += 1
            yield StreamEvent(type="tool_result", data={"tool": WEB_SEARCH_TOOL_NAME, "result": {"ok": forced_trace.ok}})

        visible_parts: list[str] = []
        for round_number in range(first_model_round, self.max_steps + 1):
            timings.bump("react_rounds")
            timings.set_meta("round_number", round_number)
            active_tool_choice = self._resolve_tool_choice(run_state, round_number)
            # 工具调用前已有可见正文时，本轮正文前补两个换行：
            # 分隔符既作为 token 发给前端，也计入最终落库的 answer。
            content_prefix = "\n\n" if visible_parts else ""
            round_result = yield from self._stream_round(
                working_messages,
                tool_choice=active_tool_choice,
                content_prefix=content_prefix,
                model_spec=model_spec,
                execution_context=execution_context,
                rag_enabled=rag_enabled,
                web_search_enabled=web_search_enabled,
            )
            # _stream_round 已把分隔前缀计入 content 并作为 token 发出。
            if round_result.content:
                visible_parts.append(round_result.content)
            tool_calls = round_result.tool_calls

            if not tool_calls:
                raw_reply = "".join(visible_parts)
                if not raw_reply:
                    raise RuntimeError("Model stream returned no content")

                final_trace = ToolTrace(
                    used=bool(tool_call_traces),
                    calls=tool_call_traces,
                    ledger=run_state.ledger,
                )
                return raw_reply, final_trace

            # Yield tool_call events and execute tools
            for tool_call in tool_calls:
                tool_name = self._tool_call_name(tool_call)
                tool_args_str = self._tool_call_arguments(tool_call)
                try:
                    tool_args = json.loads(tool_args_str)
                except json.JSONDecodeError:
                    tool_args = {}
                yield StreamEvent(
                    type="tool_call",
                    data={"tool": tool_name, "args": tool_args, "status": "running"},
                )

            working_messages, step_traces = self._build_messages_with_tool_results(
                messages=working_messages,
                first_message=self._round_result_message(round_result),
                tool_calls=tool_calls,
                round_number=round_number,
                run_state=run_state,
                execution_context=execution_context,
            )
            tool_call_traces.extend(step_traces)
            failure_count += sum(1 for trace in step_traces if not trace.ok)

            # Yield tool_result events
            for trace in step_traces:
                yield StreamEvent(
                    type="tool_result",
                    data={
                        "tool": trace.name,
                        "result": {"ok": trace.ok, "returned_count": trace.returned_count},
                    },
                )

            if failure_count >= self.max_failures:
                break

        # Tool budget was exhausted. Ask for a final streamed answer without tools.
        timings.set_meta("round_number", None)
        content_prefix = "\n\n" if visible_parts else ""
        final_round = yield from self._stream_round(
            working_messages,
            tool_choice="none",
            content_prefix=content_prefix,
            model_spec=model_spec,
            execution_context=execution_context,
            rag_enabled=rag_enabled,
            web_search_enabled=web_search_enabled,
        )
        if final_round.content:
            visible_parts.append(final_round.content)
        raw_reply = "".join(visible_parts)
        if not raw_reply:
            raise RuntimeError("Model stream returned no content")

        final_trace = ToolTrace(
            used=bool(tool_call_traces),
            calls=tool_call_traces,
            ledger=run_state.ledger,
        )
        return raw_reply, final_trace

    def _stream_round(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        tool_choice: str | dict | None = None,
        content_prefix: str = "",
        model_spec: ModelSpec | None = None,
        execution_context=None,
        rag_enabled: bool = True,
        web_search_enabled: bool = True,
    ) -> Generator[StreamEvent, None, _RoundResult]:
        """Make one streamed model call and accumulate its complete round result.

        content_prefix 是上一轮工具调用留下的可见正文与本轮正文之间的分隔符：
        只在本轮真正产出内容时作为 token 发出并计入 content。
        """

        runtime = self._model_runtime(model_spec)
        tools = self._active_tools(
            model_spec=model_spec,
            execution_context=execution_context,
            rag_enabled=rag_enabled,
            web_search_enabled=web_search_enabled,
        )
        active_tool_choice = tool_choice or "auto"
        request_params = dict(runtime.request_params)
        request_params.update(
            {
                "model": runtime.api_model,
                "messages": messages,
                "tools": tools,
                "tool_choice": active_tool_choice,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
        )

        timings.bump("llm_calls")
        if timings.get_meta("model") is None:
            timings.set_meta("model", runtime.trace_model)

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_call_parts: dict[int, dict[str, str]] = {}
        usage = None
        finish_reason = None
        stream = None
        started_at = time.perf_counter()
        stream_error: Exception | None = None

        try:
            with timings.track("llm"):
                stream = runtime.client.chat.completions.create(**request_params)
                for chunk in stream:
                    chunk_usage = self._object_value(chunk, "usage")
                    if chunk_usage is not None:
                        usage = chunk_usage

                    choices = self._object_value(chunk, "choices") or []
                    if not choices:
                        continue

                    choice = choices[0]
                    choice_finish_reason = self._object_value(choice, "finish_reason")
                    if choice_finish_reason:
                        finish_reason = choice_finish_reason
                    delta = self._object_value(choice, "delta")
                    if delta is None:
                        continue

                    content = self._object_value(delta, "content")
                    if content:
                        text = str(content)
                        if content_prefix and not content_parts:
                            content_parts.append(content_prefix)
                            yield StreamEvent(
                                type="token",
                                data={"text": content_prefix},
                            )
                        content_parts.append(text)
                        yield StreamEvent(type="token", data={"text": text})

                    reasoning = self._object_value(delta, "reasoning_content")
                    if reasoning:
                        reasoning_parts.append(str(reasoning))

                    for tool_call in self._object_value(delta, "tool_calls") or []:
                        index = self._object_value(tool_call, "index", 0)
                        try:
                            tool_index = int(index)
                        except (TypeError, ValueError):
                            tool_index = 0
                        slot = tool_call_parts.setdefault(
                            tool_index,
                            {"id": "", "name": "", "arguments": ""},
                        )
                        tool_call_id = self._object_value(tool_call, "id")
                        if tool_call_id:
                            slot["id"] = str(tool_call_id)
                        function = self._object_value(tool_call, "function")
                        function_name = self._object_value(function, "name")
                        if function_name:
                            slot["name"] = str(function_name)
                        function_arguments = self._object_value(function, "arguments")
                        if function_arguments:
                            slot["arguments"] += str(function_arguments)
        except Exception as exc:
            stream_error = exc
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

        stream_cost_ms = int((time.perf_counter() - started_at) * 1000)
        self._record_llm_call(
            usage=usage,
            finish_reason=finish_reason,
            call_type="with_tools",
            cost_ms=stream_cost_ms,
            trace_model=runtime.trace_model,
        )

        if stream_error is not None:
            timings.bump("llm_calls")
            fallback_started_at = time.perf_counter()
            with timings.track("llm"):
                completion = runtime.client.chat.completions.create(
                    model=runtime.api_model,
                    messages=messages,
                    tools=tools,
                    tool_choice=active_tool_choice,
                    **runtime.request_params,
                )
            self._record_llm_call(
                completion=completion,
                call_type="with_tools",
                cost_ms=int((time.perf_counter() - fallback_started_at) * 1000),
                trace_model=runtime.trace_model,
            )
            fallback_result = self._round_result_from_message(
                completion.choices[0].message
            )
            if fallback_result.content:
                if content_prefix and not content_parts:
                    content_parts.append(content_prefix)
                    yield StreamEvent(
                        type="token",
                        data={"text": content_prefix},
                    )
                yield StreamEvent(
                    type="token",
                    data={"text": fallback_result.content},
                )
            return fallback_result

        tool_calls = [
            {
                "id": slot["id"] or f"tool_call_{index}",
                "type": "function",
                "function": {
                    "name": slot["name"],
                    "arguments": slot["arguments"] or "{}",
                },
            }
            for index, slot in sorted(tool_call_parts.items())
        ]
        return _RoundResult(
            content="".join(content_parts),
            reasoning="".join(reasoning_parts),
            tool_calls=tool_calls,
        )

    def _round_result_message(self, result: _RoundResult) -> dict[str, Any]:
        """Convert one accumulated round into an assistant tool-call message."""

        message: dict[str, Any] = {
            "role": "assistant",
            "content": result.content or None,
            "tool_calls": result.tool_calls,
        }
        if result.reasoning:
            message["reasoning_content"] = result.reasoning
        return message

    def _round_result_from_message(self, message) -> _RoundResult:
        """Normalize a non-stream fallback response to the stream result shape."""

        tool_calls = self._message_tool_calls(message)
        return _RoundResult(
            content=self._message_content(message) or "",
            reasoning=self._message_reasoning_content(message) or "",
            tool_calls=[
                self._tool_call_payload(tool_call, index)
                for index, tool_call in enumerate(tool_calls)
            ],
        )

    @staticmethod
    def _object_value(value, name: str, default=None):
        """Read a field from SDK objects and recorded-dict fixtures alike."""

        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    def _execute_forced_web_search(
        self,
        messages: list[ChatCompletionMessageParam],
        run_state: _RunState,
        *,
        round_number: int = 1,
        execution_context=None,
    ) -> tuple[list[ChatCompletionMessageParam], ToolCallTrace]:
        """Execute one user-requested Web Search before normal model routing."""

        arguments = {"query": self._latest_user_message(messages)}
        serialized_arguments = json.dumps(arguments, ensure_ascii=False)
        run_state.web_search_calls += 1
        tool_call_id = "forced_web_search_1"
        tool_result = self.tool_executor.execute(
            WEB_SEARCH_TOOL_NAME,
            serialized_arguments,
            execution_context=execution_context,
            tool_call_id=tool_call_id,
        )
        tool_result = self._prepare_web_search_result(tool_result, run_state)
        working_messages: list[ChatCompletionMessageParam] = [
            *messages,
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": WEB_SEARCH_TOOL_NAME,
                            "arguments": serialized_arguments,
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": self._tool_observation_content(tool_result),
            },
        ]
        trace = self._tool_call_trace(
            round_number=round_number,
            name=WEB_SEARCH_TOOL_NAME,
            arguments=serialized_arguments,
            result=tool_result,
        )
        return working_messages, trace

    def _execute_forced_learning_notes(
        self,
        messages: list[ChatCompletionMessageParam],
        run_state: _RunState,
        *,
        execution_context=None,
    ) -> tuple[list[ChatCompletionMessageParam], ToolCallTrace]:
        """Execute one user-requested learning-note retrieval before model routing."""

        arguments = {"query": self._latest_user_message(messages)}
        serialized_arguments = json.dumps(arguments, ensure_ascii=False)
        tool_result = self.tool_executor.execute(
            RAG_TOOL_NAME,
            serialized_arguments,
            execution_context=execution_context,
            tool_call_id="forced_learning_notes_1",
        )
        tool_result = self._prepare_learning_notes_result(tool_result, run_state)
        tool_call_id = "forced_learning_notes_1"
        working_messages: list[ChatCompletionMessageParam] = [
            *messages,
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": RAG_TOOL_NAME,
                            "arguments": serialized_arguments,
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": self._tool_observation_content(tool_result),
            },
        ]
        trace = self._tool_call_trace(
            round_number=1,
            name=RAG_TOOL_NAME,
            arguments=serialized_arguments,
            result=tool_result,
        )
        return working_messages, trace

    def _latest_user_message(
        self,
        messages: list[ChatCompletionMessageParam],
    ) -> str:
        """Return the current user text used as the forced search query."""

        for message in reversed(messages):
            role = message.get("role") if isinstance(message, dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if role == "user" and isinstance(content, str) and content.strip():
                return content.strip()

        return ""

    def _model_runtime(self, model_spec: ModelSpec | None = None) -> _ModelRuntime:
        """Resolve the active request model without leaking it across requests."""

        spec = model_spec
        if spec is None and self.config is None and self.client is None:
            spec = resolve_model()

        if spec is not None:
            request_params = dict(spec.top_level_params)
            if spec.extra_body:
                request_params["extra_body"] = dict(spec.extra_body)
            return _ModelRuntime(
                client=get_llm_client(spec.provider),
                api_model=spec.api_model,
                trace_model=spec.model_id,
                request_params=request_params,
            )

        if self.config is None or self.client is None:
            raise RuntimeError("legacy model config and client must be provided together")

        return _ModelRuntime(
            client=self.client,
            api_model=self.config.model,
            trace_model=self.config.model,
            request_params={},
        )

    def _active_tools(
        self,
        *,
        model_spec: ModelSpec | None = None,
        execution_context=None,
        rag_enabled: bool = True,
        web_search_enabled: bool = True,
    ) -> list[dict[str, Any]]:
        """Return tools allowed by the explicit model and request switches."""

        spec = model_spec
        if spec is not None and not spec.supports_tools:
            return []

        try:
            tools = self.tool_registry.get_tools_schema(
                execution_context=execution_context,
            )
        except TypeError:
            # Keep lightweight test registries and old integrations compatible.
            tools = self.tool_registry.get_tools_schema()
        if not rag_enabled:
            tools = [
                tool
                for tool in tools
                if _tool_schema_name(tool) != RAG_TOOL_NAME
            ]
        if not web_search_enabled:
            tools = [
                tool
                for tool in tools
                if _tool_schema_name(tool) != WEB_SEARCH_TOOL_NAME
            ]
        # Conversation attachments are already injected as trusted, bounded
        # prompt context.  They are not a vector-search tool anymore.
        tools = [
            tool
            for tool in tools
            if _tool_schema_name(tool) != ATTACHMENT_TOOL_NAME
        ]
        return tools

    def _call_model_with_request_state(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        tool_choice: str | dict | None,
        model_spec: ModelSpec | None,
        execution_context,
        rag_enabled: bool,
        web_search_enabled: bool,
    ):
        """Call a model round with explicit state while keeping test hooks compatible."""

        method = self._call_model_with_tools
        parameters = inspect.signature(method).parameters
        accepts_state = (
            "model_spec" in parameters
            or any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
        )
        if not accepts_state:
            return method(messages)
        return method(
            messages,
            tool_choice=tool_choice,
            model_spec=model_spec,
            execution_context=execution_context,
            rag_enabled=rag_enabled,
            web_search_enabled=web_search_enabled,
        )

    def _call_model_for_request(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        model_spec: ModelSpec | None,
    ) -> str:
        """Call a final model round with explicit state while keeping test hooks compatible."""

        method = self._call_model
        if getattr(method, "__func__", None) is not ReactOrchestrator._call_model:
            return method(messages)
        return method(messages, model_spec=model_spec)

    def _call_model_with_tools(
        self,
        messages: list[ChatCompletionMessageParam],
        tool_choice: str | dict | None = None,
        *,
        model_spec: ModelSpec | None = None,
        execution_context=None,
        rag_enabled: bool = True,
        web_search_enabled: bool = True,
    ):
        """调用模型并提供工具 schema，让模型选择是否请求工具。"""

        if "_call_model" in self.__dict__:
            # 兼容测试：如果测试替换了 _call_model，就沿用纯文本返回路径。
            return {
                "content": self._call_model(messages),
                "tool_calls": [],
            }

        runtime = self._model_runtime(model_spec)
        timings.bump("llm_calls")
        if timings.get_meta("model") is None:
            timings.set_meta("model", runtime.trace_model)

        tools = self._active_tools(
            model_spec=model_spec,
            execution_context=execution_context,
            rag_enabled=rag_enabled,
            web_search_enabled=web_search_enabled,
        )

        active_tool_choice = tool_choice or "auto"
        call_started_at = time.perf_counter()
        with timings.track("llm"):
            completion = runtime.client.chat.completions.create(
                model=runtime.api_model,
                messages=messages,
                tools=tools,
                tool_choice=active_tool_choice,
                **runtime.request_params,
            )
        self._record_llm_call(
            completion=completion,
            call_type="with_tools",
            cost_ms=int((time.perf_counter() - call_started_at) * 1000),
            trace_model=runtime.trace_model,
        )

        return completion.choices[0].message

    def _build_messages_with_tool_results(
        self,
        messages: list[ChatCompletionMessageParam],
        first_message,
        tool_calls: list[Any],
        round_number: int,
        run_state: _RunState,
        execution_context=None,
    ) -> tuple[list[ChatCompletionMessageParam], list[ToolCallTrace]]:
        """把模型 tool call 和工具执行结果追加到下一步模型输入里。"""

        tool_messages: list[dict[str, Any]] = [
            *messages,
            self._assistant_tool_call_message(first_message, tool_calls),
        ]
        traces: list[ToolCallTrace] = []

        for index, tool_call in enumerate(tool_calls):
            tool_name = self._tool_call_name(tool_call)
            tool_arguments = self._tool_call_arguments(tool_call)
            if tool_name == RAG_TOOL_NAME and not run_state.rag_enabled:
                # 关闭模式：即使模型伪造了 RAG 工具调用也不执行，
                # 防止绕过 Schema 移除的限制。
                tool_result = {
                    "ok": False,
                    "error": "tool_disabled",
                    "message": "RAG 检索已关闭，本轮不可用。",
                }
            elif tool_name == WEB_SEARCH_TOOL_NAME and not run_state.web_search_enabled:
                # 关闭模式：即使模型伪造了联网搜索调用也不执行。
                tool_result = {
                    "ok": False,
                    "error": "tool_disabled",
                    "message": "联网搜索已关闭，本轮不可用。",
                }
            elif tool_name == WEB_SEARCH_TOOL_NAME:
                run_state.web_search_calls += 1
                if run_state.web_search_calls > WEB_SEARCH_MAX_CALLS_PER_CHAT:
                    trace_db.save_tool_call(
                        trace_id=timings.get_trace_id(),
                        round_number=timings.get_meta("round_number"),
                        tool_name=WEB_SEARCH_TOOL_NAME,
                        channel="internal",
                        forced=int(bool(timings.get_meta("forced"))),
                        ok=0,
                        error_code="web_search_budget_exceeded",
                        cost_ms=0,
                        args_preview=tool_arguments[:500],
                    )
                    tool_result = {
                        "ok": False,
                        "error": "web_search_budget_exceeded",
                        "message": "web search call budget exceeded",
                    }
                else:
                    tool_result = self.tool_executor.execute(
                        tool_name,
                        tool_arguments,
                        execution_context=execution_context,
                        tool_call_id=self._tool_call_id(tool_call, index),
                    )
                    tool_result = self._prepare_web_search_result(
                        tool_result,
                        run_state,
                    )
            elif tool_name == ATTACHMENT_TOOL_NAME:
                # Attachments are injected before this loop.  Reject stale or
                # hallucinated retrieval calls so Chroma/embeddings are never
                # used by the conversation path.
                tool_result = {
                    "ok": False,
                    "error": "tool_disabled",
                    "message": "会话附件已直接注入上下文，本轮不可检索附件。",
                }
            else:
                tool_result = self.tool_executor.execute(
                    tool_name,
                    tool_arguments,
                    execution_context=execution_context,
                    tool_call_id=self._tool_call_id(tool_call, index),
                )
                if tool_name == RAG_TOOL_NAME:
                    tool_result = self._prepare_learning_notes_result(
                        tool_result,
                        run_state,
                    )
                elif tool_name == JD_TOOL_NAME:
                    tool_result = self._prepare_jd_result(
                        tool_result,
                        run_state,
                    )
            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": self._tool_call_id(tool_call, index),
                    "content": self._tool_observation_content(tool_result),
                }
            )
            traces.append(
                self._tool_call_trace(
                    round_number=round_number,
                    name=tool_name,
                    arguments=tool_arguments,
                    result=tool_result,
                    routing_forced=bool(
                        tool_name == ATTACHMENT_TOOL_NAME
                        and run_state.attachment_ids
                        and round_number == 1
                    ),
                )
            )

        return tool_messages, traces

    def _resolve_tool_choice(
        self,
        run_state: _RunState,
        round_number: int,
    ) -> str | dict:
        """Attachments are prompt context; only ordinary tools route here."""

        return "auto"

    def _prepare_attachment_result(
        self,
        tool_result: dict[str, Any],
        run_state: _RunState,
    ) -> dict[str, Any]:
        """稳定 attachment 结果：分配 ledger 条目并保持失败结果稳定。"""

        if not isinstance(tool_result, dict) or not tool_result.get("ok"):
            return tool_result

        prepared_result = dict(tool_result)
        safe_items: list[dict[str, Any]] = []
        items = tool_result.get("items")

        if isinstance(items, list):
            for item in items:
                prepared_item = self._attachment_item_from_hit(item, run_state)
                if prepared_item is not None:
                    safe_items.append(prepared_item)

        prepared_result["items"] = safe_items
        prepared_result["found"] = bool(safe_items)
        summary = prepared_result.get("summary")
        if isinstance(summary, dict):
            prepared_summary = dict(summary)
            prepared_summary["returned_count"] = len(safe_items)
            prepared_result["summary"] = prepared_summary

        return prepared_result

    def _attachment_item_from_hit(
        self,
        item: Any,
        run_state: _RunState,
    ) -> dict[str, Any] | None:
        """Return one attachment item with a stable evidence_id and ledger entry."""

        if not isinstance(item, dict):
            return None

        evidence_id = item.get("evidence_id")
        title = item.get("title")
        content = item.get("content")
        if (
            not isinstance(evidence_id, str)
            or not evidence_id.strip()
            or not isinstance(title, str)
            or not title.strip()
            or not isinstance(content, str)
            or not content.strip()
        ):
            return None

        if evidence_id not in run_state.ledger:
            run_state.ledger[evidence_id] = Source(
                id=evidence_id,
                title=title,
                url="",
                domain="attachment",
            )

        safe_item = dict(item)
        safe_item["evidence_id"] = evidence_id
        return safe_item

    def _prepare_learning_notes_result(
        self,
        tool_result: dict[str, Any],
        run_state: _RunState,
    ) -> dict[str, Any]:
        """Assign server-owned note IDs and keep failed RAG results stable."""

        if not isinstance(tool_result, dict) or not tool_result.get("ok"):
            return self._stabilize_failed_rag_result(tool_result)

        prepared_result = dict(tool_result)
        safe_items: list[dict[str, Any]] = []
        items = tool_result.get("items")

        if isinstance(items, list):
            for item in items:
                prepared_item = self._note_item_from_hit(item, run_state)
                if prepared_item is not None:
                    safe_items.append(prepared_item)

        prepared_result["items"] = safe_items
        prepared_result["found"] = bool(safe_items)
        summary = prepared_result.get("summary")
        if isinstance(summary, dict):
            prepared_summary = dict(summary)
            prepared_summary["returned_count"] = len(safe_items)
            prepared_result["summary"] = prepared_summary

        return prepared_result

    def _note_item_from_hit(
        self,
        item: Any,
        run_state: _RunState,
    ) -> dict[str, Any] | None:
        """Return one item with a stable, reused note ID and ledger entry."""

        if not isinstance(item, dict):
            return None

        source = item.get("source")
        title_path = item.get("title_path") or item.get("title")
        content = item.get("content")
        if (
            not isinstance(source, str)
            or not source.strip()
            or not isinstance(content, str)
            or not content.strip()
        ):
            return None

        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "source": source,
                    "title_path": str(title_path or ""),
                    "content": content,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        evidence_id = run_state.note_id_by_fingerprint.get(fingerprint)
        if evidence_id is None:
            evidence_id = f"note_{run_state.next_note_number}"
            run_state.next_note_number += 1
            run_state.note_id_by_fingerprint[fingerprint] = evidence_id
            run_state.ledger[evidence_id] = Source(
                id=evidence_id,
                title=_note_source_title(source, title_path),
                url="",
                domain="knowledge_note",
            )

        safe_item = dict(item)
        safe_item["evidence_id"] = evidence_id
        return safe_item

    def _prepare_jd_result(
        self,
        tool_result: dict[str, Any],
        run_state: _RunState,
    ) -> dict[str, Any]:
        """Assign server-owned jd IDs and keep failed JD results stable."""

        if not isinstance(tool_result, dict) or not tool_result.get("ok"):
            return tool_result

        prepared_result = dict(tool_result)
        safe_items: list[dict[str, Any]] = []
        items = tool_result.get("items")

        if isinstance(items, list):
            for item in items:
                prepared_item = self._jd_item_from_record(item, run_state)
                if prepared_item is not None:
                    safe_items.append(prepared_item)

        prepared_result["items"] = safe_items
        prepared_result["found"] = bool(safe_items)
        summary = prepared_result.get("summary")
        if isinstance(summary, dict):
            prepared_summary = dict(summary)
            prepared_summary["returned_count"] = len(safe_items)
            prepared_result["summary"] = prepared_summary

        return prepared_result

    def _jd_item_from_record(
        self,
        item: Any,
        run_state: _RunState,
    ) -> dict[str, Any] | None:
        """Return one JD item with a stable, reused jd ID and ledger entry."""

        if not isinstance(item, dict):
            return None

        jd_id = item.get("jd_id")
        title = item.get("title")
        company = item.get("company")
        source = item.get("source")
        content = item.get("content")
        if (
            not isinstance(jd_id, str)
            or not jd_id.strip()
            or not isinstance(title, str)
            or not title.strip()
            or not isinstance(company, str)
            or not company.strip()
            or not isinstance(source, str)
            or not source.strip()
            or not isinstance(content, str)
            or not content.strip()
        ):
            return None

        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "jd_id": jd_id,
                    "source": source,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        evidence_id = run_state.jd_id_by_fingerprint.get(fingerprint)
        if evidence_id is None:
            evidence_id = f"jd_{run_state.next_jd_number}"
            run_state.next_jd_number += 1
            run_state.jd_id_by_fingerprint[fingerprint] = evidence_id
            run_state.ledger[evidence_id] = Source(
                id=evidence_id,
                title=f"{company} · {title}",
                url=item.get("source_url") or "",
                domain="job_description",
            )

        safe_item = dict(item)
        safe_item["evidence_id"] = evidence_id
        return safe_item

    @staticmethod
    def _stabilize_failed_rag_result(
        tool_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Replace RAG failure details with stable text that leaks nothing."""

        if not isinstance(tool_result, dict):
            return {
                "ok": False,
                "error": "rag_retrieval_failed",
                "message": "本轮知识库检索失败，无法提供本地资料。",
            }

        error = str(tool_result.get("error") or "rag_retrieval_failed")
        stable_message = {
            "index_not_built": "本地知识库索引尚未构建，当前无法执行 RAG 检索。",
            "embedding_failed": "本轮知识库检索失败，无法提供本地资料。",
        }.get(error, "本轮知识库检索失败，无法提供本地资料。")
        return {
            "ok": False,
            "error": error,
            "message": stable_message,
        }

    def _prepare_web_search_result(
        self,
        tool_result: dict[str, Any],
        run_state: _RunState,
    ) -> dict[str, Any]:
        """Filter Web results, assign server-owned IDs, and update the ledger."""

        if not isinstance(tool_result, dict) or not tool_result.get("ok"):
            return tool_result

        prepared_result = dict(tool_result)
        safe_items: list[dict[str, Any]] = []
        items = tool_result.get("items")

        if isinstance(items, list):
            for item in items:
                source = self._source_from_web_item(item, run_state)
                if source is None:
                    continue

                safe_item = dict(item)
                safe_item.update(
                    {
                        "evidence_id": source.id,
                        "title": source.title,
                        "url": source.url,
                        "domain": source.domain,
                    }
                )
                safe_items.append(safe_item)

        prepared_result["items"] = safe_items
        prepared_result["found"] = bool(safe_items)
        summary = prepared_result.get("summary")
        if isinstance(summary, dict):
            prepared_summary = dict(summary)
            prepared_summary["returned_count"] = len(safe_items)
            prepared_result["summary"] = prepared_summary

        return prepared_result

    def _source_from_web_item(
        self,
        item: Any,
        run_state: _RunState,
    ) -> Source | None:
        """Return a ledger source for one safe Web Search item."""

        if not isinstance(item, dict):
            return None

        title = item.get("title")
        url = item.get("url")
        if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
            return None

        normalized = self._normalize_safe_web_url(url)
        if normalized is None:
            return None

        normalized_url, domain = normalized
        evidence_id = run_state.evidence_id_by_url.get(normalized_url)
        if evidence_id is None:
            evidence_id = f"web_{run_state.next_evidence_number}"
            run_state.next_evidence_number += 1
            run_state.evidence_id_by_url[normalized_url] = evidence_id
            run_state.ledger[evidence_id] = Source(
                id=evidence_id,
                title=title.strip(),
                url=normalized_url,
                domain=domain,
            )

        return run_state.ledger[evidence_id]

    def _normalize_safe_web_url(self, url: str) -> tuple[str, str] | None:
        """Normalize an HTTPS URL without changing its path or query semantics."""

        candidate = url.strip()
        if not candidate or any(character.isspace() for character in candidate):
            return None

        try:
            parsed = urlsplit(candidate)
            port = parsed.port
        except ValueError:
            return None

        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None

        domain = parsed.hostname.lower()
        host = f"[{domain}]" if ":" in domain else domain
        netloc = host if port in (None, 443) else f"{host}:{port}"
        normalized_url = urlunsplit(
            ("https", netloc, parsed.path, parsed.query, "")
        )
        return normalized_url, domain

    def _tool_observation_content(self, tool_result: dict[str, Any]) -> str:
        """把工具结果序列化成 observation，并按配置截断超长内容。"""

        serialized = json.dumps(tool_result, ensure_ascii=False)
        if len(serialized) <= self.max_observation_chars:
            return serialized

        return self._truncated_observation(serialized)

    def _truncated_observation(self, serialized: str) -> str:
        """生成带截断标记的 observation 文本，并尽量保持在长度上限内。"""

        max_chars = max(0, self.max_observation_chars)
        if max_chars == 0:
            return ""

        payload: dict[str, Any] = {
            "truncated": True,
            "original_chars": len(serialized),
            "preview": "",
        }
        content = json.dumps(payload, ensure_ascii=False)
        if len(content) > max_chars:
            return content[:max_chars]

        available_preview_chars = max_chars - len(content)
        payload["preview"] = serialized[:available_preview_chars]
        content = json.dumps(payload, ensure_ascii=False)

        while len(content) > max_chars and payload["preview"]:
            payload["preview"] = payload["preview"][:-1]
            content = json.dumps(payload, ensure_ascii=False)

        return content

    def _tool_call_trace(
        self,
        round_number: int,
        name: str,
        arguments: str,
        result: dict[str, Any],
        routing_forced: bool = False,
    ) -> ToolCallTrace:
        """把一次工具执行结果整理成前端可展示的 trace。"""

        summary = result.get("summary") if isinstance(result, dict) else None
        items = result.get("items") if isinstance(result, dict) else None
        top_titles = [
            str(item["title"])
            for item in (items or [])[:3]
            if isinstance(item, dict) and item.get("title")
        ]

        return ToolCallTrace(
            round=round_number,
            name=name,
            arguments=self._trace_arguments(name, arguments),
            ok=bool(result.get("ok")) if isinstance(result, dict) else False,
            returned_count=(
                summary.get("returned_count")
                if isinstance(summary, dict)
                else None
            ),
            top_titles=top_titles,
            result_preview=self._trace_result_preview(name, result, items),
            error=result.get("error") if isinstance(result, dict) else "invalid_result",
            routing_forced=routing_forced,
        )

    def _trace_result_preview(
        self,
        name: str,
        result: dict[str, Any],
        items: Any,
    ) -> list[dict[str, Any]]:
        """根据工具类型选择适合前端调试区展示的结果预览。"""

        if name == "score_jd_skill_fit":
            return self._skill_fit_result_preview(result)
        if name == WEB_SEARCH_TOOL_NAME:
            return self._web_search_result_preview(items)

        return self._tool_result_preview(items)

    def _web_search_result_preview(self, items: Any) -> list[dict[str, Any]]:
        """Expose only lightweight, non-snippet Web Search trace fields."""

        if not isinstance(items, list):
            return []

        preview: list[dict[str, Any]] = []
        for item in items[:3]:
            if not isinstance(item, dict) or not item.get("title"):
                continue

            preview.append(
                {
                    "evidence_id": str(item.get("evidence_id") or ""),
                    "title": str(item["title"]),
                    "domain": str(item.get("domain") or ""),
                    "published_at": item.get("published_at"),
                }
            )

        return preview

    def _skill_fit_result_preview(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        """把技能匹配工具结果压缩成前端可读的调试预览。"""

        if not isinstance(result, dict) or not result.get("ok"):
            return []

        return [
            {
                "target_role": str(result.get("target_role") or ""),
                "fit_score": self._optional_int(result.get("fit_score")),
                "fit_level": str(result.get("fit_level") or ""),
                "top_strengths": self._trace_string_list(
                    result.get("top_strengths")
                ),
                "top_gaps": self._trace_string_list(result.get("top_gaps")),
                "uncertain_skills": self._trace_string_list(
                    result.get("uncertain_skills")
                ),
            }
        ]

    def _tool_result_preview(self, items: Any) -> list[dict[str, Any]]:
        """从通用工具 items 中取前三条安全字段作为调试预览。"""

        if not isinstance(items, list):
            return []

        preview = []
        for item in items[:3]:
            if not isinstance(item, dict) or not item.get("title"):
                continue

            preview.append(
                {
                    "title": str(item["title"]),
                    "match_score": self._optional_int(item.get("match_score")),
                    "matched_fields": self._trace_string_list(
                        item.get("matched_fields")
                    ),
                    "core_skills": self._trace_string_list(item.get("core_skills")),
                    "keywords": self._trace_string_list(item.get("keywords")),
                    "interview_focus": self._trace_string_list(
                        item.get("interview_focus")
                    ),
                    "raw_text_excerpt": str(item.get("raw_text_excerpt") or ""),
                }
            )

        return preview

    def _optional_int(self, value: Any) -> int | None:
        """把可转成整数的值转成 int，无法转换时返回 None。"""

        if isinstance(value, bool):
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _trace_string_list(self, value: Any) -> list[str]:
        """只保留列表里的字符串项，避免 trace 暴露异常结构。"""

        if not isinstance(value, list):
            return []

        return [item for item in value if isinstance(item, str)]

    def _trace_arguments(self, name: str, arguments: str) -> dict[str, Any]:
        """Parse trace arguments while redacting Web Search query text."""

        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}

        if not isinstance(parsed, dict):
            return {}
        if name != WEB_SEARCH_TOOL_NAME:
            return parsed

        trace_arguments = {
            key: parsed[key]
            for key in ("max_results", "freshness_days")
            if key in parsed
        }
        query = parsed.get("query")
        if isinstance(query, str):
            trace_arguments["query_hash"] = hashlib.sha256(
                query.encode("utf-8")
            ).hexdigest()[:12]
            trace_arguments["query_chars"] = len(query)

        return trace_arguments

    def _assistant_tool_call_message(
        self,
        first_message,
        tool_calls: list[Any],
    ) -> dict[str, Any]:
        """把模型请求工具的消息整理成可继续传回模型的 assistant 消息。"""

        message: dict[str, Any] = {
            "role": "assistant",
            "tool_calls": [
                self._tool_call_payload(tool_call, index)
                for index, tool_call in enumerate(tool_calls)
            ],
        }
        content = self._message_content(first_message)
        if content:
            message["content"] = content

        reasoning = self._message_reasoning_content(first_message)
        if reasoning:
            message["reasoning_content"] = reasoning

        return message

    def _message_content(self, message) -> str | None:
        """兼容 dict、字符串和 SDK 消息对象，统一取出模型文本内容。"""

        if isinstance(message, str):
            return message

        if isinstance(message, dict):
            return message.get("content")

        return getattr(message, "content", None)

    def _message_reasoning_content(self, message) -> str | None:
        """Read provider reasoning retained only within a ReAct tool loop."""

        if isinstance(message, dict):
            return message.get("reasoning_content")

        return getattr(message, "reasoning_content", None)

    def _message_tool_calls(self, message) -> list[Any]:
        """兼容 dict 和 SDK 消息对象，统一取出模型请求的工具调用列表。"""

        if isinstance(message, dict):
            return message.get("tool_calls") or []

        return getattr(message, "tool_calls", None) or []

    def _tool_call_payload(self, tool_call, index: int) -> dict[str, Any]:
        """把单个 tool_call 标准化成 OpenAI tool message 需要的 payload。"""

        return {
            "id": self._tool_call_id(tool_call, index),
            "type": "function",
            "function": {
                "name": self._tool_call_name(tool_call),
                "arguments": self._tool_call_arguments(tool_call),
            },
        }

    def _tool_call_id(self, tool_call, index: int) -> str:
        """取出 tool_call id；缺失时用序号生成稳定 fallback id。"""

        if isinstance(tool_call, dict):
            return str(tool_call.get("id") or f"tool_call_{index}")

        return str(getattr(tool_call, "id", None) or f"tool_call_{index}")

    def _tool_call_name(self, tool_call) -> str:
        """从 tool_call.function 中取出工具名称。"""

        function = self._tool_call_function(tool_call)

        if isinstance(function, dict):
            return str(function.get("name") or "")

        return str(getattr(function, "name", "") or "")

    def _tool_call_arguments(self, tool_call) -> str:
        """从 tool_call.function 中取出工具参数 JSON 字符串。"""

        function = self._tool_call_function(tool_call)

        if isinstance(function, dict):
            return str(function.get("arguments") or "{}")

        return str(getattr(function, "arguments", None) or "{}")

    def _tool_call_function(self, tool_call):
        """兼容 dict 和 SDK tool_call 对象，统一取出 function 部分。"""

        if isinstance(tool_call, dict):
            return tool_call.get("function") or {}

        return getattr(tool_call, "function", None)

    def _call_model(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        model_spec: ModelSpec | None = None,
    ) -> str:
        """把 messages 发送给模型，并返回原始文本回复。"""

        runtime = self._model_runtime(model_spec)
        timings.bump("llm_calls")
        if timings.get_meta("model") is None:
            timings.set_meta("model", runtime.trace_model)

        call_started_at = time.perf_counter()
        with timings.track("llm"):
            completion = runtime.client.chat.completions.create(
                model=runtime.api_model,
                messages=messages,
                **runtime.request_params,
            )
        self._record_llm_call(
            completion=completion,
            call_type="final",
            cost_ms=int((time.perf_counter() - call_started_at) * 1000),
            trace_model=runtime.trace_model,
        )
        raw_reply = completion.choices[0].message.content

        if not raw_reply:
            raise RuntimeError("模型没有返回内容")

        return raw_reply

    def _record_llm_call(
        self,
        *,
        call_type: str,
        cost_ms: int,
        completion=None,
        usage=None,
        finish_reason: str | None = None,
        trace_model: str,
    ) -> None:
        """提取 usage / finish_reason 写入 llm_calls，并累加请求级 token 汇总。

        部分第三方 OpenAI 兼容端点不返回 usage，流式默认也不返回；
        usage 可能为 None，取不到就写 None，不抛异常、不写 0。
        """

        if completion is not None:
            usage = getattr(completion, "usage", None)
            if finish_reason is None:
                try:
                    finish_reason = completion.choices[0].finish_reason
                except (AttributeError, IndexError):
                    pass

        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        completion_tokens = (
            getattr(usage, "completion_tokens", None) if usage else None
        )
        total_tokens = getattr(usage, "total_tokens", None) if usage else None
        if prompt_tokens is not None:
            timings.bump("prompt_tokens", prompt_tokens)
        if completion_tokens is not None:
            timings.bump("completion_tokens", completion_tokens)

        trace_db.save_llm_call(
            trace_id=timings.get_trace_id(),
            round_number=timings.get_meta("round_number"),
            call_type=call_type,
            model=trace_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_ms=cost_ms,
            finish_reason=finish_reason,
        )
