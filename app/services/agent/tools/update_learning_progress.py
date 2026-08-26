"""Explicitly update the user's SQL learning progress."""

from typing import Any

from app.repositories.learning_progress_repository import get_learning_progress
from app.services.agent.workspace.context import AgentExecutionContext
from app.services.learning_progress_service import LearningProgressService


TOOL_NAME = "update_learning_progress"

SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "只在用户明确要求更新学习进度时调用。这个工具写入 SQL 学习进度，"
            "不是 save_journal_entry，不能用来保存学习日志。请根据已有进度、"
            "当前会话摘要和最近对话，提交 1 到 5 个有证据的 updates。"
            "每个 update 必须包含 topic、level、status、evidence；"
            "level 映射为 0=未接触、1=初步理解、2=可以完成基础练习、"
            "3=基本掌握。示例："
            '{"updates":[{"topic":"窗口函数","level":1,'
            '"status":"learning","evidence":"能解释 OVER，但尚未完成练习",'
            '"next_step":"完成 ROW_NUMBER 练习","confidence":"medium"}]}。'
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "updates": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 5,
                    "description": "最多提交 5 个有证据的知识点更新。不要提交学习日志全文；日志请使用 save_journal_entry。",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": "知识点名称，例如 JOIN、GROUP BY、窗口函数；不要填写整段总结。",
                            },
                            "level": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 3,
                                "description": "只能填写 0、1、2、3：0 未接触；1 初步理解；2 可以完成基础练习；3 基本掌握。",
                            },
                            "status": {
                                "type": "string",
                                "enum": [
                                    "not_started",
                                    "learning",
                                    "needs_practice",
                                    "mastered",
                                ],
                                "description": "not_started=未接触；learning=正在学习；needs_practice=需要巩固；mastered=基本掌握。",
                            },
                            "evidence": {
                                "type": "string",
                                "description": "必须是具体学习证据，例如做题结果、用户自述或反复出现的错误；不能写空泛结论。",
                            },
                            "next_step": {
                                "type": "string",
                                "description": "一个明确、可执行的下一步练习；没有时可以省略。",
                            },
                            "confidence": {
                                "type": "string",
                                "enum": ["low", "medium", "high"],
                                "default": "medium",
                                "description": "判断可信度；low 会被跳过，medium/high 才会写入。",
                            },
                        },
                        "required": ["topic", "level", "status", "evidence"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["updates"],
            "additionalProperties": False,
        },
    },
}



def update_learning_progress(
    updates: list[dict[str, Any]],
    *,
    execution_context: AgentExecutionContext,
    tool_call_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Persist explicit, evidence-based SQL progress updates."""

    if not isinstance(updates, list) or not 1 <= len(updates) <= 5:
        return {
            "ok": False,
            "error": "invalid_arguments",
            "message": "updates must contain between 1 and 5 items.",
        }

    service = LearningProgressService()
    updated: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    seen_topics: set[str] = set()

    for item in updates:
        if not isinstance(item, dict):
            return _invalid("each update must be an object")
        topic = str(item.get("topic") or "").strip()
        if not topic:
            return _invalid("each update must include a topic")
        topic_key = " ".join(topic.split()).lower()
        if topic_key in seen_topics:
            return _invalid("updates must not contain duplicate topics")
        seen_topics.add(topic_key)

        confidence = str(item.get("confidence") or "medium").strip().lower()
        if confidence == "low":
            skipped.append({"topic": topic, "reason": "low_confidence"})
            continue

        evidence = item.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            return _invalid(f"{topic} requires non-empty evidence")

        try:
            level = int(item.get("level"))
        except (TypeError, ValueError):
            return _invalid(f"{topic} level must be an integer between 0 and 3")
        status = item.get("status")
        previous = get_learning_progress(
            user_id=execution_context.user_id,
            subject="sql",
            topic=" ".join(topic.split()),
        )
        record = service.save_agent(
            user_id=execution_context.user_id,
            subject="sql",
            topic=topic,
            level=level,
            status=status,
            evidence=evidence,
            next_step=item.get("next_step"),
        )
        updated.append(
            {
                "topic": record.topic,
                "previous_level": previous.level if previous else None,
                "current_level": record.level,
                "status": record.status.value,
                "source": record.source.value,
            }
        )

    return {
        "ok": True,
        "updated": updated,
        "skipped": skipped,
        "message": "SQL learning progress updated.",
    }



def _invalid(message: str) -> dict[str, Any]:
    return {"ok": False, "error": "invalid_arguments", "message": message}
