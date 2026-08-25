"""学习进度的业务规则。"""

import re

from app.db.models import (
    LearningProgressRecord,
    LearningProgressSource,
    LearningProgressStatus,
)
from app.repositories.learning_progress_repository import (
    delete_learning_progress,
    get_learning_progress,
    list_learning_progress,
    upsert_learning_progress,
)

MAX_USER_ID_LENGTH = 64
MAX_SUBJECT_LENGTH = 64
MAX_TOPIC_LENGTH = 120
MAX_EVIDENCE_LENGTH = 2000
MAX_NEXT_STEP_LENGTH = 500


class InvalidLearningProgressError(ValueError):
    """学习进度字段不符合业务规则。"""


class LearningProgressService:
    """提供手动记录和 Agent 未来共用的学习进度服务。"""

    def list_for_user(
        self,
        *,
        user_id: str,
        subject: str = "sql",
        limit: int = 100,
    ) -> list[LearningProgressRecord]:
        normalized_user_id = _normalize_required(
            user_id, "user_id", MAX_USER_ID_LENGTH
        )
        normalized_subject = _normalize_subject(subject)
        if limit < 1 or limit > 100:
            raise InvalidLearningProgressError("limit must be between 1 and 100")
        return list_learning_progress(
            user_id=normalized_user_id,
            subject=normalized_subject,
            limit=limit,
        )

    def delete_manual(
        self,
        *,
        progress_id: int,
        user_id: str,
        subject: str,
    ) -> bool:
        """删除用户手动维护的一条记录。"""

        if not isinstance(progress_id, int) or isinstance(progress_id, bool) or progress_id < 1:
            raise InvalidLearningProgressError("progress_id must be a positive integer")
        normalized_user_id = _normalize_required(
            user_id, "user_id", MAX_USER_ID_LENGTH
        )
        normalized_subject = _normalize_subject(subject)
        return delete_learning_progress(
            progress_id=progress_id,
            user_id=normalized_user_id,
            subject=normalized_subject,
        )

    def save_manual(
        self,
        *,
        user_id: str,
        subject: str,
        topic: str,
        level: int,
        status: LearningProgressStatus | str,
        evidence: str | None,
        next_step: str | None,
    ) -> LearningProgressRecord:
        """保存用户手动维护的记录。"""

        return self._save(
            user_id=user_id,
            subject=subject,
            topic=topic,
            level=level,
            status=status,
            evidence=evidence,
            next_step=next_step,
            source=LearningProgressSource.MANUAL,
        )

    def save_agent(
        self,
        *,
        user_id: str,
        subject: str,
        topic: str,
        level: int,
        status: LearningProgressStatus | str,
        evidence: str | None,
        next_step: str | None,
    ) -> LearningProgressRecord:
        """保存 Agent 根据证据形成的记录，供后续工具调用。"""

        return self._save(
            user_id=user_id,
            subject=subject,
            topic=topic,
            level=level,
            status=status,
            evidence=evidence,
            next_step=next_step,
            source=LearningProgressSource.AGENT,
        )

    def _save(
        self,
        *,
        user_id: str,
        subject: str,
        topic: str,
        level: int,
        status: LearningProgressStatus | str,
        evidence: str | None,
        next_step: str | None,
        source: LearningProgressSource,
    ) -> LearningProgressRecord:
        normalized_user_id = _normalize_required(
            user_id, "user_id", MAX_USER_ID_LENGTH
        )
        normalized_subject = _normalize_subject(subject)
        normalized_topic = _normalize_required(topic, "topic", MAX_TOPIC_LENGTH)
        if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 3:
            raise InvalidLearningProgressError("level must be an integer between 0 and 3")

        try:
            normalized_status = LearningProgressStatus(status)
        except ValueError as exc:
            raise InvalidLearningProgressError(
                "status must be one of: not_started, learning, needs_practice, mastered"
            ) from exc

        if source is LearningProgressSource.AGENT:
            existing = get_learning_progress(
                user_id=normalized_user_id,
                subject=normalized_subject,
                topic=normalized_topic,
            )
            if existing is not None and level < existing.level:
                # One failed exercise should not erase a previously established
                # level. Keep the level and mark the topic for practice instead.
                level = existing.level
                if normalized_status is not LearningProgressStatus.MASTERED:
                    normalized_status = LearningProgressStatus.NEEDS_PRACTICE

        return upsert_learning_progress(
            user_id=normalized_user_id,
            subject=normalized_subject,
            topic=normalized_topic,
            level=level,
            status=normalized_status,
            evidence=_normalize_optional(evidence, "evidence", MAX_EVIDENCE_LENGTH),
            next_step=_normalize_optional(next_step, "next_step", MAX_NEXT_STEP_LENGTH),
            source=source,
        )


def _normalize_subject(value: str) -> str:
    normalized = _normalize_required(value, "subject", MAX_SUBJECT_LENGTH)
    return normalized.lower()


def _normalize_required(value: str, field_name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise InvalidLearningProgressError(f"{field_name} must be a string")
    normalized = re.sub(r"\s+", " ", value.strip())
    if not normalized:
        raise InvalidLearningProgressError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise InvalidLearningProgressError(
            f"{field_name} must be at most {max_length} characters"
        )
    return normalized


def _normalize_optional(
    value: str | None,
    field_name: str,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    return _normalize_required(value, field_name, max_length)
