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
            "Update the user's SQL learning progress only after the user explicitly "
            "requested a progress update. Use evidence from the current conversation "
            "and existing progress; do not invent changes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "updates": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 5,
                    "description": "At most five evidence-based SQL topic updates.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": "SQL topic, such as JOIN or GROUP BY.",
                            },
                            "level": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 3,
                                "description": (
                                    "0 not started, 1 initial understanding, "
                                    "2 basic exercises, 3 basically mastered."
                                ),
                            },
                            "status": {
                                "type": "string",
                                "enum": [
                                    "not_started",
                                    "learning",
                                    "needs_practice",
                                    "mastered",
                                ],
                            },
                            "evidence": {
                                "type": "string",
                                "description": "Concrete evidence from the user's learning.",
                            },
                            "next_step": {
                                "type": "string",
                                "description": "One practical next learning step.",
                            },
                            "confidence": {
                                "type": "string",
                                "enum": ["low", "medium", "high"],
                                "default": "medium",
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

    if not execution_context.progress_update_requested:
        return {
            "ok": False,
            "error": "progress_update_not_requested",
            "message": "Progress updates require an explicit user request.",
        }
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
