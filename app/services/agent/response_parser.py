"""解析当前和历史 Tutor Agent 回复。"""

import json

from app.schemas.chat import TutorReply


class ResponseParser:
    """把模型回复和已保存回复转换成 TutorReply 需要的结构。"""

    def parse_model_reply(self, raw_reply: str) -> TutorReply:
        """把模型原始文本解析成结构化导师回复。"""

        cleaned_reply = raw_reply.strip()
        if not cleaned_reply:
            raise RuntimeError("模型回复为空，无法生成导师回复")

        if cleaned_reply.startswith("```json"):
            cleaned_reply = cleaned_reply.removeprefix("```json").removesuffix("```").strip()
        elif cleaned_reply.startswith("```"):
            cleaned_reply = cleaned_reply.removeprefix("```").removesuffix("```").strip()

        try:
            data = json.loads(cleaned_reply)
            if not isinstance(data, dict):
                raise TypeError("model reply must be a JSON object")

            raw_source_ids = data.get("source_ids", [])
            data["source_ids"] = (
                [item for item in raw_source_ids if isinstance(item, str)]
                if isinstance(raw_source_ids, list)
                else []
            )
            return TutorReply.model_validate(data)
        except (json.JSONDecodeError, ValueError, TypeError):
            return TutorReply(
                answer=cleaned_reply,
                next_task="请把这个问题再具体问一次，或者换一个更小的学习点继续追问。",
                exercise="用一句话写下你刚才最想弄懂的概念。",
                checkpoints=[
                    "系统没有因为模型格式不规范而崩溃",
                    "返回结果仍然包含固定字段",
                    "你知道 fallback 是用来兜底异常输出的",
                ],
            )

    def parse_history_answer(self, reply_json: str) -> str | None:
        """返回适合作为历史上下文的已保存导师回答。"""

        try:
            reply_data = json.loads(reply_json)
        except (json.JSONDecodeError, TypeError):
            return None

        answer = reply_data.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return None

        return answer
