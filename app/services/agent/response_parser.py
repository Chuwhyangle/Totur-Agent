"""解析当前模型回复与历史保存回复。"""

import json

from app.schemas.chat import TutorReply

REPLY_FORMAT_JSON_V1 = "json_v1"
REPLY_FORMAT_MARKDOWN_V2 = "markdown_v2"


class ResponseParser:
    """当前回复按 Markdown 透传；历史回复按 reply_format 显式分发。"""

    def parse_model_reply(self, raw_reply: str) -> TutorReply:
        """把模型原始 Markdown 文本包装成导师回复。

        不再尝试解析 JSON：模型输出就是最终正文，包含 JSON 代码块时
        也保持原样渲染，不做任何格式嗅探。
        """

        cleaned_reply = raw_reply.strip()
        if not cleaned_reply:
            raise RuntimeError("模型回复为空，无法生成导师回复")

        return TutorReply(answer=cleaned_reply)

    def parse_stored_reply(self, reply_raw: str, reply_format: str) -> TutorReply:
        """按保存时记录的 reply_format 解析历史回复。

        显式分发，不猜测格式：
        - markdown_v2：reply_raw 就是 Markdown 正文
        - json_v1：旧五字段 JSON，从中提取 answer
        - 未知 format：直接报错，让问题看得见
        """

        if reply_format == REPLY_FORMAT_MARKDOWN_V2:
            return TutorReply(answer=reply_raw)

        if reply_format == REPLY_FORMAT_JSON_V1:
            try:
                data = json.loads(reply_raw)
            except (json.JSONDecodeError, TypeError):
                # 旧库里偶然存在的坏记录：跳过 answer，不让会话读取崩溃。
                return TutorReply(answer="")
            if not isinstance(data, dict):
                return TutorReply(answer="")
            answer = data.get("answer")
            return TutorReply(answer=answer if isinstance(answer, str) else "")

        raise ValueError(f"未知的 reply_format: {reply_format}")
