"""识别用户是否明确请求更新学习进度。"""

import re


_EXPLICIT_COMMANDS = {
    "/更新进度",
    "/更新学习进度",
    "更新学习进度",
    "帮我更新一下学习进度",
    "帮我去更新一下学习进度",
    "同步一下我的学习进度",
    "同步学习进度",
}
_PROGRESS_TERMS = (
    "学习进度",
    "学习情况",
    "学习状态",
    "掌握情况",
    "学习记录",
    "进度记录",
    "学习成果",
)
_ACTION_TERMS = ("更新", "同步", "记录", "评估", "整理", "保存", "写入", "加入")
_NORMALIZED_COMMANDS = {re.sub(r"\s+", "", item) for item in _EXPLICIT_COMMANDS}


def is_progress_update_request(message: str) -> bool:
    """Return whether a message is an explicit progress-update request.

    Use deterministic keyword matching instead of an LLM classifier. The
    structured ChatRequest.action remains the primary trigger for the button,
    while ordinary-language requests can also enable the tool.
    """

    if not isinstance(message, str):
        return False
    normalized = re.sub(r"\s+", "", message.strip())
    normalized = normalized.rstrip("，。！？,.!?")
    if normalized in _NORMALIZED_COMMANDS:
        return True

    has_progress_term = any(term in normalized for term in _PROGRESS_TERMS)
    has_action_term = any(term in normalized for term in _ACTION_TERMS)
    # Natural-language requests often place the intent after the subject,
    # e.g. “把最近学习情况更新到记录里”。 Presence of both terms is enough
    # to enable the progress tool; accidental-call hardening can be added later.
    return has_progress_term and has_action_term
