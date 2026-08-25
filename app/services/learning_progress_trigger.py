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
_PROGRESS_TERMS = ("学习进度", "学习情况", "学习状态")
_ACTION_TERMS = ("更新", "同步", "记录", "评估")
_INTENT_PREFIXES = (
    "更新",
    "同步",
    "记录",
    "评估",
    "请",
    "请帮我",
    "帮我",
    "能不能帮我",
    "我要",
    "我想",
    "现在",
)
_NORMALIZED_COMMANDS = {re.sub(r"\s+", "", item) for item in _EXPLICIT_COMMANDS}


def is_progress_update_request(message: str) -> bool:
    """Return whether a message is an explicit progress-update request.

    Deliberately use a small allow-list instead of an LLM classifier so ordinary
    teaching turns never gain write permission by accident. The structured
    ChatRequest.action remains the primary trigger for the frontend button.
    """

    if not isinstance(message, str):
        return False
    normalized = re.sub(r"\s+", "", message.strip())
    normalized = normalized.rstrip("，。！？,.!?")
    if normalized in _NORMALIZED_COMMANDS:
        return True

    has_progress_term = any(term in normalized for term in _PROGRESS_TERMS)
    has_action_term = any(term in normalized for term in _ACTION_TERMS)
    has_intent_prefix = normalized.startswith(_INTENT_PREFIXES)
    return has_progress_term and has_action_term and has_intent_prefix
