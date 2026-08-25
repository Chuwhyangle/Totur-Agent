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
    return normalized in {re.sub(r"\s+", "", item) for item in _EXPLICIT_COMMANDS}
