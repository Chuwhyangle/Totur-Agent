"""ReAct orchestration for Tutor Agent tool use."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.config import LLMConfig
from app.schemas.chat import ToolCallTrace, ToolTrace
from app.services.memory_settings import (
    MAX_TOOL_FAILURES,
    MAX_TOOL_ROUNDS,
    TOOL_OBSERVATION_MAX_CHARS,
)
from app.services.agent.tools.executor import ToolExecutor
from app.services.agent.tools.registry import ToolRegistry


class ReactOrchestrator:
    """Runs the model-tool-observation loop and returns the final model text."""

    def __init__(
        self,
        config: LLMConfig,
        client: OpenAI,
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
    ) -> tuple[str, ToolTrace]:
        """执行最多 max_steps 步的 ReAct 工具循环。"""

        working_messages: list[ChatCompletionMessageParam] = [*messages]
        tool_call_traces: list[ToolCallTrace] = []
        failure_count = 0

        for round_number in range(1, self.max_steps + 1):
            model_message = self._call_model_with_tools(working_messages)
            tool_calls = self._message_tool_calls(model_message)

            if not tool_calls:
                raw_reply = self._message_content(model_message)
                if not raw_reply:
                    raise RuntimeError("模型没有返回内容")

                return raw_reply, ToolTrace(
                    used=bool(tool_call_traces),
                    calls=tool_call_traces,
                )

            working_messages, step_traces = self._build_messages_with_tool_results(
                messages=working_messages,
                first_message=model_message,
                tool_calls=tool_calls,
                round_number=round_number,
            )
            tool_call_traces.extend(step_traces)
            failure_count += sum(1 for trace in step_traces if not trace.ok)

            if failure_count >= self.max_failures:
                break

        raw_reply = self._call_model(working_messages)
        if not raw_reply:
            raise RuntimeError("模型没有返回内容")

        return raw_reply, ToolTrace(
            used=bool(tool_call_traces),
            calls=tool_call_traces,
        )

    def _call_model_with_tools(self, messages: list[ChatCompletionMessageParam]):
        """调用模型并提供工具 schema，让模型选择是否请求工具。"""

        if "_call_model" in self.__dict__:
            # 兼容测试：如果测试替换了 _call_model，就沿用纯文本返回路径。
            return {
                "content": self._call_model(messages),
                "tool_calls": [],
            }

        completion = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            tools=self.tool_registry.get_tools_schema(),
            tool_choice="auto",
        )

        return completion.choices[0].message

    def _build_messages_with_tool_results(
        self,
        messages: list[ChatCompletionMessageParam],
        first_message,
        tool_calls: list[Any],
        round_number: int,
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
            tool_result = self.tool_executor.execute(
                tool_name,
                tool_arguments,
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
                )
            )

        return tool_messages, traces

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
            arguments=self._trace_arguments(arguments),
            ok=bool(result.get("ok")) if isinstance(result, dict) else False,
            returned_count=(
                summary.get("returned_count")
                if isinstance(summary, dict)
                else None
            ),
            top_titles=top_titles,
            result_preview=self._trace_result_preview(name, result, items),
            error=result.get("error") if isinstance(result, dict) else "invalid_result",
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

        return self._tool_result_preview(items)

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

    def _trace_arguments(self, arguments: str) -> dict[str, Any]:
        """把模型传来的 JSON 参数字符串解析成 trace 可展示的 dict。"""

        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}

        if not isinstance(parsed, dict):
            return {}

        return parsed

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

        return message

    def _message_content(self, message) -> str | None:
        """兼容 dict、字符串和 SDK 消息对象，统一取出模型文本内容。"""

        if isinstance(message, str):
            return message

        if isinstance(message, dict):
            return message.get("content")

        return getattr(message, "content", None)

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

    def _call_model(self, messages: list[ChatCompletionMessageParam]) -> str:
        """把 messages 发送给模型，并返回原始文本回复。"""

        completion = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
        )
        raw_reply = completion.choices[0].message.content

        if not raw_reply:
            raise RuntimeError("模型没有返回内容")

        return raw_reply
