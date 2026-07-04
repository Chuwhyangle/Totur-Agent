"""Agent 回复解析器的单元测试。"""

import pytest

from app.schemas.chat import TutorReply
from app.services.agent.response_parser import ResponseParser


def test_parse_model_reply_accepts_valid_json():
    parser = ResponseParser()

    reply = parser.parse_model_reply(
        """
        {
          "answer": "解析后的回答",
          "next_task": "解析后的任务",
          "exercise": "解析后的练习",
          "checkpoints": ["第一项", "第二项", "第三项"]
        }
        """
    )

    assert isinstance(reply, TutorReply)
    assert reply.answer == "解析后的回答"
    assert reply.next_task == "解析后的任务"
    assert reply.exercise == "解析后的练习"
    assert reply.checkpoints == ["第一项", "第二项", "第三项"]


def test_parse_model_reply_cleans_markdown_json_fence():
    parser = ResponseParser()

    reply = parser.parse_model_reply(
        """
        ```json
        {
          "answer": "代码块里的回答",
          "next_task": "代码块里的任务",
          "exercise": "代码块里的练习",
          "checkpoints": ["代码块检查点"]
        }
        ```
        """
    )

    assert reply.answer == "代码块里的回答"


def test_parse_model_reply_falls_back_for_non_json_text():
    parser = ResponseParser()

    reply = parser.parse_model_reply("这不是 JSON。")

    assert reply.answer == "这不是 JSON。"
    assert isinstance(reply.next_task, str)
    assert isinstance(reply.exercise, str)
    assert len(reply.checkpoints) == 3


def test_parse_model_reply_rejects_empty_reply():
    parser = ResponseParser()

    with pytest.raises(RuntimeError, match="模型回复为空"):
        parser.parse_model_reply("   ")


def test_parse_history_answer_extracts_answer():
    parser = ResponseParser()

    answer = parser.parse_history_answer(
        """
        {
          "answer": "历史回答",
          "next_task": "历史任务",
          "exercise": "历史练习",
          "checkpoints": ["历史检查点"]
        }
        """
    )

    assert answer == "历史回答"


def test_parse_history_answer_returns_none_for_bad_json():
    parser = ResponseParser()

    assert parser.parse_history_answer("not valid json") is None
