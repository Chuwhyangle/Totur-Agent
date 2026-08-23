"""Agent 回复解析器的单元测试。"""

import pytest

from app.schemas.chat import Source, ToolTrace, TutorReply
from app.services.agent.response_parser import (
    REPLY_FORMAT_JSON_V1,
    REPLY_FORMAT_MARKDOWN_V2,
    ResponseParser,
)
from app.services.tutor_agent_service import TutorAgentService


def test_parse_model_reply_passes_markdown_through_verbatim():
    parser = ResponseParser()
    raw = "\n\n  ## 什么是路由\n\n  路由就是把 URL 和 Python 函数绑定起来。\n\n"

    reply = parser.parse_model_reply(raw)

    assert isinstance(reply, TutorReply)
    assert reply.answer == "## 什么是路由\n\n  路由就是把 URL 和 Python 函数绑定起来。"
    assert reply.sources == []


def test_parse_model_reply_keeps_json_code_block_as_plain_body():
    """正文里出现 JSON 代码块时必须原样保留，不能被当作 JSON 解析。"""

    parser = ResponseParser()
    raw = """下面是接口返回示例：

```json
{"answer": "不是模型回复结构", "next_task": "只是示例"}
```

继续解释。"""

    reply = parser.parse_model_reply(raw)

    assert reply.answer == raw
    assert '{"answer": "不是模型回复结构"' in reply.answer


def test_parse_model_reply_does_not_generate_fake_fallback_fields():
    parser = ResponseParser()

    reply = parser.parse_model_reply("普通 Markdown 正文。")

    assert reply.answer == "普通 Markdown 正文。"
    assert reply.model_dump() == {"answer": "普通 Markdown 正文。", "sources": []}


def test_parse_model_reply_rejects_empty_reply():
    parser = ResponseParser()

    with pytest.raises(RuntimeError, match="模型回复为空"):
        parser.parse_model_reply("   ")


def test_parse_stored_reply_reads_legacy_json_v1_answer():
    parser = ResponseParser()

    reply = parser.parse_stored_reply(
        """
        {
          "answer": "历史回答",
          "next_task": "历史任务",
          "exercise": "历史练习",
          "checkpoints": ["历史检查点"]
        }
        """,
        REPLY_FORMAT_JSON_V1,
    )

    assert reply.answer == "历史回答"
    assert reply.sources == []


def test_parse_stored_reply_reads_markdown_v2_body_verbatim():
    parser = ResponseParser()

    raw = "## 历史正文\n\n```json\n{\"a\": 1}\n```"
    reply = parser.parse_stored_reply(raw, REPLY_FORMAT_MARKDOWN_V2)

    assert reply.answer == raw


def test_parse_stored_reply_rejects_unknown_format():
    parser = ResponseParser()

    with pytest.raises(ValueError, match="未知的 reply_format"):
        parser.parse_stored_reply("anything", "sniff_me")


def test_parse_stored_reply_skips_broken_json_v1_without_crashing():
    parser = ResponseParser()

    assert parser.parse_stored_reply("not valid json", REPLY_FORMAT_JSON_V1).answer == ""
    assert parser.parse_stored_reply('{"no_answer": 1}', REPLY_FORMAT_JSON_V1).answer == ""


def test_tutor_agent_service_builds_sources_from_body_in_first_appearance_order():
    service = object.__new__(TutorAgentService)
    reply = TutorReply(
        answer=(
            "先看 [web_2]，再看 [web_1]，重复 [web_2]，伪造 [web_99]，"
            "以及未验证链接 https://attacker.example/path?q=1"
        ),
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

    assert [source.id for source in finalized.sources] == ["web_2", "web_1"]
    assert [source.url for source in finalized.sources] == [
        "https://docs.example.org/two",
        "https://official.example/one",
    ]
    # 去重只作用于 sources 列表；正文中重复的合法引用保持原样
    assert [source.id for source in finalized.sources].count("web_2") == 1
    assert finalized.answer.count("[web_2]") == 2
    assert "[web_1]" in finalized.answer
    assert "[web_99]" not in finalized.answer
    assert "http://" not in finalized.answer
    assert "https://" not in finalized.answer
    assert "[已移除未验证链接]" in finalized.answer
    assert finalized.model_dump() == {
        "answer": finalized.answer,
        "sources": [source.model_dump() for source in finalized.sources],
    }


def test_tutor_agent_service_accepts_attachment_and_web_sources_from_ledger():
    service = object.__new__(TutorAgentService)
    reply = TutorReply(
        answer="Web [web_1], attachment [attachment_1], fake [attachment_999].",
    )
    tool_trace = ToolTrace(
        used=True,
        ledger={
            "web_1": Source(
                id="web_1",
                title="Official docs",
                url="https://official.example/docs",
                domain="official.example",
            ),
            "attachment_1": Source(
                id="attachment_1",
                title="resume.pdf · 第 2 页",
                url="",
                domain="attachment",
            ),
        },
    )

    finalized = service._finalize_reply_sources(reply, tool_trace)

    assert [source.id for source in finalized.sources] == ["web_1", "attachment_1"]
    assert "[attachment_1]" in finalized.answer
    assert "[attachment_999]" not in finalized.answer
    assert "[web_1]" in finalized.answer


def test_tutor_agent_service_accepts_jd_sources_from_ledger():
    service = object.__new__(TutorAgentService)
    reply = TutorReply(
        answer="该岗位要求 [jd_1]，同时参考笔记 [note_1]，伪造 [jd_999]。",
    )
    tool_trace = ToolTrace(
        used=True,
        ledger={
            "jd_1": Source(
                id="jd_1",
                title="示例科技 · RAG 后端工程师",
                url="https://example.com/jobs/1",
                domain="job_description",
            ),
            "note_1": Source(
                id="note_1",
                title="docs/rag.md",
                url="",
                domain="knowledge_note",
            ),
        },
    )

    finalized = service._finalize_reply_sources(reply, tool_trace)

    assert [source.id for source in finalized.sources] == ["jd_1", "note_1"]
    assert "[jd_1]" in finalized.answer
    assert "[note_1]" in finalized.answer
    assert "[jd_999]" not in finalized.answer
    assert "[note_999]" not in finalized.answer


def test_tutor_agent_service_rejects_note_references_when_rag_disabled():
    service = object.__new__(TutorAgentService)
    reply = TutorReply(answer="关闭 RAG 后仍然写了 [note_1]，以及正常的 [web_1]。")
    tool_trace = ToolTrace(
        used=True,
        ledger={
            "note_1": Source(
                id="note_1",
                title="docs/rag.md",
                url="",
                domain="knowledge_note",
            ),
            "web_1": Source(
                id="web_1",
                title="Official",
                url="https://official.example/one",
                domain="official.example",
            ),
        },
    )

    finalized = service._finalize_reply_sources(
        reply,
        tool_trace,
        note_references_allowed=False,
    )

    assert [source.id for source in finalized.sources] == ["web_1"]
    assert "[note_1]" not in finalized.answer
    assert "[web_1]" in finalized.answer
