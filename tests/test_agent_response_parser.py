"""Agent 回复解析器的单元测试。"""

import pytest

from app.schemas.chat import Source, ToolTrace, TutorReply
from app.services.agent.response_parser import ResponseParser
from app.services.tutor_agent_service import TutorAgentService


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


def test_parse_model_reply_parses_source_ids_and_keeps_them_internal():
    parser = ResponseParser()

    reply = parser.parse_model_reply(
        """
        {
          "answer": "Evidence-backed answer [web_1]",
          "next_task": "Read the source",
          "exercise": "Summarize it",
          "checkpoints": ["Verify recency"],
          "source_ids": ["web_1", 2, "web_2"]
        }
        """
    )

    assert reply.source_ids == ["web_1", "web_2"]
    assert reply.sources == []
    assert "source_ids" not in reply.model_dump()


def test_tutor_agent_service_builds_sources_only_from_current_ledger():
    service = object.__new__(TutorAgentService)
    reply = TutorReply(
        answer=(
            "Verified [web_1], fabricated [web_99], and raw "
            "https://attacker.example/path?q=1"
        ),
        next_task="Next",
        exercise="Exercise",
        checkpoints=["Check"],
        source_ids=["web_2", "web_1", "web_2", "web_99"],
        sources=[
            Source(
                id="web_99",
                title="Model-controlled",
                url="https://attacker.example/fake",
                domain="attacker.example",
            )
        ],
    )
    tool_trace = ToolTrace(
        used=True,
        ledger={
            "web_1": Source(
                id="web_1",
                title="Official One",
                url="https://official.example/one",
                domain="official.example",
            ),
            "web_2": Source(
                id="web_2",
                title="Official Two",
                url="https://docs.example.org/two",
                domain="docs.example.org",
            ),
        },
    )

    finalized = service._finalize_reply_sources(reply, tool_trace)

    assert finalized.source_ids == ["web_2", "web_1"]
    assert [source.id for source in finalized.sources] == ["web_2", "web_1"]
    assert [source.url for source in finalized.sources] == [
        "https://docs.example.org/two",
        "https://official.example/one",
    ]
    assert "[web_1]" in finalized.answer
    assert "[web_99]" not in finalized.answer
    assert "http://" not in finalized.answer
    assert "https://" not in finalized.answer
    assert "[\u5df2\u79fb\u9664\u672a\u9a8c\u8bc1\u94fe\u63a5]" in finalized.answer
    assert "source_ids" not in finalized.model_dump()
