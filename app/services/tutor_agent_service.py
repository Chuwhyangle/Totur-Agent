"""Tutor Agent 聊天业务服务。"""

from collections.abc import Callable, Generator
import re
import time

from openai import OpenAI
from app.db import trace_db
from app.db.models import DEFAULT_SESSION_TITLE
from app.repositories.session_repository import (
    get_or_create_default_session,
    get_session,
    make_title_from_message,
    update_session_title,
)
from app.config import LLMConfig
from app.schemas.chat import ChatRequest, ChatResponse, Source, ToolTrace, TutorReply
from app.services.agent.memory_manager import MemoryManager
from app.services.agent.model_registry import resolve_model
from app.services.agent.personas import (
    DEFAULT_PERSONA_ID,
    get_persona,
)
from app.services.agent.prompt_builder import PromptBuilder
from app.services.agent.react_orchestrator import ReactOrchestrator, StreamEvent
from app.services.agent.response_parser import ResponseParser
from app.services.agent.tools.executor import ToolExecutor
from app.services.agent.tools.registry import ToolRegistry
from app.services.documents.attachment_retrieval_service import (
    AttachmentRetrievalFailedError,
    AttachmentRetrievalService,
)
from app.repositories.interview_jd_repository import list_all_interview_jds
from app.services.private_jd_context import format_private_jd_context
from app.services.rag_seed_context import retrieve_seed_knowledge_context
from app.services.rag_settings import ENABLE_RAG_SEED_CONTEXT
from app.services.summary_service import SummaryService
from app.services import timings


_CITATION_PATTERN = re.compile(r"\[(web|attachment|note|jd)_(\d+)\]")
_RAW_HTTP_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_UNVERIFIED_LINK_REPLACEMENT = "[已移除未验证链接]"


class ChatSessionNotFoundError(Exception):
    """聊天请求指定的 session_id 不存在，或不属于当前 user_id。"""


class SessionPersonaMismatchError(Exception):
    """聊天请求试图用不同 persona_id 切换一个已绑定会话。"""

    def __init__(
        self,
        session_id: int,
        session_persona_id: str,
        request_persona_id: str,
    ) -> None:
        """保存冲突双方，方便 API 返回可读错误。"""

        self.session_id = session_id
        self.session_persona_id = session_persona_id
        self.request_persona_id = request_persona_id
        super().__init__(
            f"session {session_id} is bound to {session_persona_id}, "
            f"not {request_persona_id}"
        )


class TutorAgentService:
    """编排聊天流程：构建 prompt、调用模型、解析回复并保存历史。"""

    def __init__(
        self,
        config: LLMConfig | None = None,
        client: OpenAI | None = None,
        summary_service: SummaryService | None = None,
        response_parser: ResponseParser | None = None,
        prompt_builder: PromptBuilder | None = None,
        memory_manager: MemoryManager | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        react_orchestrator: ReactOrchestrator | None = None,
        seed_context_enabled: bool = ENABLE_RAG_SEED_CONTEXT,
        seed_context_provider: Callable[[str], str | None] | None = None,
        attachment_retrieval_service: AttachmentRetrievalService | None = None,
        attachment_context_max_chars: int | None = None,
    ) -> None:
        """初始化模型配置、模型客户端和 Agent 辅助组件。"""

        self.summary_service = summary_service or SummaryService(
            config=config,
            client=client,
        )
        self.response_parser = response_parser or ResponseParser()
        self.prompt_builder = prompt_builder or PromptBuilder(self.response_parser)
        self.memory_manager = memory_manager or MemoryManager(self.summary_service)
        self.tool_registry = tool_registry or ToolRegistry()
        self.tool_executor = tool_executor or ToolExecutor(self.tool_registry)
        self.react_orchestrator = react_orchestrator or ReactOrchestrator(
            config=config,
            client=client,
            tool_registry=self.tool_registry,
            tool_executor=self.tool_executor,
        )
        self.seed_context_enabled = seed_context_enabled
        self.seed_context_provider = seed_context_provider or retrieve_seed_knowledge_context
        # Keep attachment dependencies lazy so ordinary chat never opens Chroma or
        # initializes an embedding client.
        self.attachment_retrieval_service = attachment_retrieval_service
        self.attachment_context_max_chars = attachment_context_max_chars

    def chat(self, request: ChatRequest) -> ChatResponse:
        """处理一次聊天请求。"""

        model_spec = resolve_model(request.model_id)
        started_at = time.perf_counter()
        trace_id = timings.start_request()
        timings.set_meta("model", model_spec.model_id)
        status = "OK"
        session_id = None
        persona_id = None

        trace_db.start_trace(
            trace_id=trace_id,
            user_id=request.user_id,
            session_id=request.session_id,
            persona_id=request.persona_id,
            question=request.message,
        )

        try:
            user_id = request.user_id
            message = request.message
            session = self._resolve_session(
                user_id=user_id,
                session_id=request.session_id,
                request_persona_id=request.persona_id,
            )
            session_id = session.id
            persona_id = session.persona_id
            persona = get_persona(session.persona_id)

            # 先准备模型上下文；具体怎么读历史和摘要交给 MemoryManager。
            context = self.memory_manager.load_context(
                user_id=user_id,
                session_id=session.id,
                current_message=message,
            )
            if self.seed_context_enabled:
                context.seed_knowledge_context = self.seed_context_provider(message)

            private_jd_records = list_all_interview_jds()
            context.private_jd_context = format_private_jd_context(private_jd_records)

            # FR-3: 附件不再预注入上下文，改为工具化 + tool_choice 强制。
            # 通过 executor 默认参数注入权限上下文（不进 schema）。
            if request.attachment_ids:
                self._set_attachment_tool_defaults(
                    user_id=user_id,
                    session_id=session.id,
                    attachment_ids=request.attachment_ids,
                    subject=session.subject,
                )
            else:
                set_defaults = getattr(self.tool_executor, "set_default_tool_kwargs", None)
                if callable(set_defaults):
                    set_defaults({"search_learning_notes": {"subject": session.subject}})

            if not context.recent_history and session.title == DEFAULT_SESSION_TITLE:
                # 新会话第一条消息发出后，用这条消息生成一个更自然的会话标题。
                update_session_title(session.id, make_title_from_message(message))

            messages = self.prompt_builder.build_messages(context, persona=persona)
            raw_reply, tool_trace = self.react_orchestrator.run(
                messages,
                force_web_search=request.force_web_search,
                web_search_enabled=request.web_search_enabled,
                rag_enabled=request.rag_enabled,
                force_rag=request.force_rag,
                attachment_ids=request.attachment_ids,
                model_spec=model_spec,
            )
            # The model can only select source IDs; public Source objects always come
            # from the server-side Web/attachment ledgers (attachments now flow
            # through the search_attachments tool, which populates the ledger).
            reply = self.response_parser.parse_model_reply(raw_reply)
            reply = self._finalize_reply_sources(
                reply,
                tool_trace,
                note_references_allowed=request.rag_enabled,
            )

            # 模型回复已经结构化后，再统一保存本轮对话并尝试推进摘要。
            self.memory_manager.save_turn_and_update_summary(
                user_id=user_id,
                session_id=session.id,
                message=message,
                reply=reply,
            )

            return ChatResponse(
                user_id=user_id,
                session_id=session.id,
                message=message,
                model_id=model_spec.model_id,
                reply=reply,
                tool_trace=tool_trace,
            )
        except Exception:
            status = "ERROR"
            raise
        finally:
            total_ms = int((time.perf_counter() - started_at) * 1000)
            trace_db.finish_trace(
                user_id=request.user_id,
                total_ms=total_ms,
                retrieval_ms=timings.get("retrieval"),
                llm_ms=timings.get("llm"),
                status=status,
                trace_id=trace_id,
                session_id=session_id,
                persona_id=persona_id,
                model=timings.get_meta("model"),
                react_rounds=timings.count("react_rounds") or 0,
                llm_calls=timings.count("llm_calls") or 0,
                tool_calls=timings.count("tool_calls") or 0,
                tool_failures=timings.count("tool_failures") or 0,
                embed_ms=timings.get("embed"),
                search_ms=timings.get("search"),
                rerank_ms=timings.get("rerank"),
                tool_other_ms=timings.get("tool_other"),
                prompt_tokens=timings.count("prompt_tokens"),
                completion_tokens=timings.count("completion_tokens"),
            )

    def chat_stream(self, request: ChatRequest) -> Generator[dict, None, None]:
        """Process a chat request with SSE streaming.

        Yields dicts that map to SSE events:
            {"event": "token", "data": {...}}
            {"event": "tool_call", "data": {...}}
            {"event": "tool_result", "data": {...}}
            {"event": "done", "data": {...}}
            {"event": "error", "data": {...}}
        """

        model_spec = resolve_model(request.model_id)
        started_at = time.perf_counter()
        trace_id = timings.start_request()
        timings.set_meta("model", model_spec.model_id)
        status = "ERROR"
        session_id = None
        persona_id = None
        user_id = request.user_id
        message = request.message

        trace_db.start_trace(
            trace_id=trace_id,
            user_id=user_id,
            session_id=request.session_id,
            persona_id=request.persona_id,
            question=message,
        )

        try:
            session = self._resolve_session(
                user_id=user_id,
                session_id=request.session_id,
                request_persona_id=request.persona_id,
            )
            session_id = session.id
            persona_id = session.persona_id
            persona = get_persona(session.persona_id)

            context = self.memory_manager.load_context(
                user_id=user_id,
                session_id=session.id,
                current_message=message,
            )
            if self.seed_context_enabled:
                context.seed_knowledge_context = self.seed_context_provider(message)

            private_jd_records = list_all_interview_jds()
            context.private_jd_context = format_private_jd_context(private_jd_records)

            # FR-3: 附件工具化，权限参数经 executor 注入。
            if request.attachment_ids:
                self._set_attachment_tool_defaults(
                    user_id=user_id,
                    session_id=session.id,
                    attachment_ids=request.attachment_ids,
                    subject=session.subject,
                )
            else:
                set_defaults = getattr(self.tool_executor, "set_default_tool_kwargs", None)
                if callable(set_defaults):
                    set_defaults({"search_learning_notes": {"subject": session.subject}})

            if not context.recent_history and session.title == DEFAULT_SESSION_TITLE:
                update_session_title(session.id, make_title_from_message(message))

            messages = self.prompt_builder.build_messages(context, persona=persona)
            tool_trace: ToolTrace | None = None

            stream_gen = self.react_orchestrator.run_stream(
                messages,
                force_web_search=request.force_web_search,
                web_search_enabled=request.web_search_enabled,
                rag_enabled=request.rag_enabled,
                force_rag=request.force_rag,
                attachment_ids=request.attachment_ids,
                model_spec=model_spec,
            )
            while True:
                try:
                    event = next(stream_gen)
                except StopIteration as stop:
                    raw_reply, tool_trace = stop.value
                    break
                except Exception as exc:
                    status = "ERROR"
                    yield {"event": "error", "data": {"message": str(exc)}}
                    return

                if event.type == "token":
                    yield {"event": "token", "data": event.data}
                elif event.type in ("tool_call", "tool_result"):
                    yield {"event": event.type, "data": event.data}

            if tool_trace is None:
                status = "ERROR"
                yield {"event": "error", "data": {"message": "No response from agent"}}
                return

            reply = self.response_parser.parse_model_reply(raw_reply)
            reply = self._finalize_reply_sources(
                reply,
                tool_trace,
                note_references_allowed=request.rag_enabled,
            )

            self.memory_manager.save_turn_and_update_summary(
                user_id=user_id,
                session_id=session.id,
                message=message,
                reply=reply,
            )

            status = "OK"
            yield {
                "event": "done",
                "data": {
                    "full_response": reply.answer,
                    "reply": reply.model_dump(),
                    "session_id": session.id,
                    "model_id": model_spec.model_id,
                    "sources": [s.model_dump() for s in reply.sources],
                },
            }
        except GeneratorExit:
            if status != "OK":
                status = "CANCELLED"
            raise
        except Exception as exc:
            status = "ERROR"
            yield {"event": "error", "data": {"message": str(exc)}}
        finally:
            trace_db.finish_trace(
                trace_id=trace_id,
                user_id=user_id,
                session_id=session_id,
                persona_id=persona_id,
                model=timings.get_meta("model"),
                total_ms=int((time.perf_counter() - started_at) * 1000),
                retrieval_ms=timings.get("retrieval"),
                llm_ms=timings.get("llm"),
                status=status,
                react_rounds=timings.count("react_rounds") or 0,
                llm_calls=timings.count("llm_calls") or 0,
                tool_calls=timings.count("tool_calls") or 0,
                tool_failures=timings.count("tool_failures") or 0,
                embed_ms=timings.get("embed"),
                search_ms=timings.get("search"),
                rerank_ms=timings.get("rerank"),
                tool_other_ms=timings.get("tool_other"),
                prompt_tokens=timings.count("prompt_tokens"),
                completion_tokens=timings.count("completion_tokens"),
            )

    def _finalize_reply_sources(
        self,
        reply: TutorReply,
        tool_trace: ToolTrace,
        note_references_allowed: bool = True,
    ) -> TutorReply:
        """Build public sources from this run ledger and sanitize citations."""

        ledger = tool_trace.ledger

        def is_acceptable(evidence_id: str) -> bool:
            if evidence_id.startswith("note_") and not note_references_allowed:
                return False
            return evidence_id in ledger

        accepted_source_ids: list[str] = []
        sources: list[Source] = []
        seen_ids: set[str] = set()

        for evidence_id in reply.source_ids:
            if evidence_id in seen_ids:
                continue

            if not is_acceptable(evidence_id):
                continue

            ledger_source = ledger[evidence_id]
            seen_ids.add(evidence_id)
            accepted_source_ids.append(evidence_id)
            sources.append(
                Source(
                    id=evidence_id,
                    title=ledger_source.title,
                    url=ledger_source.url,
                    domain=ledger_source.domain,
                )
            )

        valid_ids = {
            evidence_id
            for evidence_id in ledger
            if not evidence_id.startswith("note_") or note_references_allowed
        }
        reply.answer = _CITATION_PATTERN.sub(
            lambda match: (
                match.group(0)
                if f"{match.group(1)}_{match.group(2)}" in valid_ids
                else ""
            ),
            reply.answer,
        )
        reply.answer = _RAW_HTTP_URL_PATTERN.sub(
            _UNVERIFIED_LINK_REPLACEMENT,
            reply.answer,
        )
        reply.source_ids = accepted_source_ids
        reply.sources = sources
        return reply

    def _get_attachment_retrieval_service(self) -> AttachmentRetrievalService:
        """Create attachment retrieval dependencies only when IDs are selected."""

        if self.attachment_retrieval_service is None:
            try:
                self.attachment_retrieval_service = AttachmentRetrievalService()
            except Exception as exc:
                raise AttachmentRetrievalFailedError from exc
        return self.attachment_retrieval_service

    def _set_attachment_tool_defaults(
        self,
        *,
        user_id: str,
        session_id: int,
        attachment_ids: list[str],
        subject: str | None = None,
    ) -> None:
        """FR-3: 把附件权限上下文注入 search_attachments 工具的默认参数。

        user_id/session_id/attachment_ids 不进工具 schema，
        由执行器从请求上下文注入，权限参数绝不暴露给 LLM。
        同时保留 search_learning_notes 的 subject 默认参数（覆盖式 API）。
        """

        set_defaults = getattr(self.tool_executor, "set_default_tool_kwargs", None)
        if not callable(set_defaults):
            return
        defaults: dict[str, dict[str, Any]] = {}
        if subject:
            defaults["search_learning_notes"] = {"subject": subject}
        defaults["search_attachments"] = {
            "user_id": user_id,
            "session_id": session_id,
            "attachment_ids": attachment_ids,
            "attachment_retrieval_service": self._get_attachment_retrieval_service(),
        }
        set_defaults(defaults)

    def _resolve_session(
        self,
        user_id: str,
        session_id: int | None,
        request_persona_id: str | None = None,
    ):
        """确定这次聊天要写入哪个会话。"""

        request_persona = (
            get_persona(request_persona_id) if request_persona_id is not None else None
        )
        if session_id is None:
            # 兼容旧版前端：不传 session_id 时仍然使用默认会话，但默认会话按 persona 隔离。
            return get_or_create_default_session(
                user_id,
                persona_id=request_persona.persona_id
                if request_persona is not None
                else DEFAULT_PERSONA_ID,
            )

        session = get_session(session_id)
        if session is None or session.user_id != user_id:
            raise ChatSessionNotFoundError

        if (
            request_persona is not None
            and request_persona.persona_id != session.persona_id
        ):
            raise SessionPersonaMismatchError(
                session_id=session.id,
                session_persona_id=session.persona_id,
                request_persona_id=request_persona.persona_id,
            )

        return session
