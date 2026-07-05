"""Agent prompt 构建器的单元测试。"""

from app.db.models import ConversationRecord
from app.services.agent.context import AgentContext
from app.services.agent.prompt_builder import PromptBuilder
from app.services.agent.response_parser import ResponseParser


def _record(record_id: int, message: str, reply_json: str) -> ConversationRecord:
    return ConversationRecord(
        id=record_id,
        session_id=10,
        user_id="alice",
        message=message,
        reply_json=reply_json,
        created_at=f"2026-07-04T00:00:0{record_id}+00:00",
    )


def _reply_json(answer: str) -> str:
    return f"""
    {{
      "answer": "{answer}",
      "next_task": "下一步任务",
      "exercise": "小练习",
      "checkpoints": ["检查点"]
    }}
    """


def _context(
    current_message: str = "当前问题",
    summary_text: str | None = None,
    recent_history: list[ConversationRecord] | None = None,
) -> AgentContext:
    return AgentContext(
        user_id="alice",
        session_id=10,
        current_message=current_message,
        summary_text=summary_text,
        recent_history=recent_history or [],
    )


def test_build_messages_without_summary_uses_system_and_current_message():
    builder = PromptBuilder(ResponseParser())

    messages = builder.build_messages(_context(current_message="什么是 FastAPI？"))

    assert [message["role"] for message in messages] == ["system", "user"]
    assert "新手友好的后端开发导师" in str(messages[0]["content"])
    assert "interview_jd_search" in str(messages[0]["content"])
    assert "score_jd_skill_fit" in str(messages[0]["content"])
    assert "LLM 先判断，工具只负责算分" in str(messages[0]["content"])
    assert messages[-1]["content"] == "什么是 FastAPI？"


def test_build_messages_adds_summary_before_recent_history():
    builder = PromptBuilder(ResponseParser())
    history = [_record(1, "历史问题", _reply_json("历史回答"))]

    messages = builder.build_messages(
        _context(
            summary_text="较早历史摘要",
            recent_history=history,
            current_message="继续讲",
        )
    )

    contents = [str(message["content"]) for message in messages]
    assert "较早历史摘要" in contents[1]
    assert contents.index(next(content for content in contents if "较早历史摘要" in content)) < contents.index(
        "历史问题"
    )


def test_build_messages_orders_recent_history_from_old_to_new():
    builder = PromptBuilder(ResponseParser())
    recent_history = [
        _record(2, "较新的问题", _reply_json("较新的回答")),
        _record(1, "较旧的问题", _reply_json("较旧的回答")),
    ]

    messages = builder.build_messages(_context(recent_history=recent_history))

    role_and_content = [
        (message["role"], message["content"])
        for message in messages
    ]
    assert role_and_content[1:] == [
        ("user", "较旧的问题"),
        ("assistant", "较旧的回答"),
        ("user", "较新的问题"),
        ("assistant", "较新的回答"),
        ("user", "当前问题"),
    ]


def test_build_messages_always_puts_current_message_last():
    builder = PromptBuilder(ResponseParser())
    history = [_record(1, "历史问题", _reply_json("历史回答"))]

    messages = builder.build_messages(
        _context(
            summary_text="较早历史摘要",
            recent_history=history,
            current_message="最后的问题",
        )
    )

    assert messages[-1] == {
        "role": "user",
        "content": "最后的问题",
    }


def test_build_messages_skips_bad_history_answer_without_crashing():
    builder = PromptBuilder(ResponseParser())
    history = [_record(1, "坏历史问题", "not valid json")]

    messages = builder.build_messages(_context(recent_history=history))

    role_and_content = [
        (message["role"], message["content"])
        for message in messages
    ]
    assert role_and_content[1:] == [
        ("user", "坏历史问题"),
        ("user", "当前问题"),
    ]


def test_build_messages_shows_exact_llm_input_with_summary_and_recent_history():
    builder = PromptBuilder(ResponseParser())
    recent_history = [
        _record(14, "第 14 轮用户问题", _reply_json("第 14 轮导师回答")),
        _record(13, "第 13 轮用户问题", _reply_json("第 13 轮导师回答")),
        _record(12, "第 12 轮用户问题", _reply_json("第 12 轮导师回答")),
        _record(11, "第 11 轮用户问题", _reply_json("第 11 轮导师回答")),
        _record(10, "第 10 轮用户问题", _reply_json("第 10 轮导师回答")),
        _record(9, "第 9 轮用户问题", _reply_json("第 9 轮导师回答")),
    ]

    messages = builder.build_messages(
        _context(
            summary_text="第 1-8 轮摘要：用户在学习 FastAPI 路由和 SQLite 基础。",
            recent_history=recent_history,
            current_message="第 15 轮当前问题",
        )
    )

    role_and_content = [
        (message["role"], message["content"])
        for message in messages
    ]

    assert role_and_content == [
        (
            "system",
            "你是一个新手友好的后端开发导师，也可以作为技术面试训练导师。\n"
            "当用户明确要准备岗位面试、根据 JD 出题、追问、点评或规划复习重点时，"
            "可以调用 interview_jd_search。\n"
            "当已经拿到目标 JD 技能要求，并且用户提供了当前技术栈或项目经历时，"
            "可以调用 score_jd_skill_fit 计算 JD 符合度；LLM 先判断，工具只负责算分。\n"
            "调用 score_jd_skill_fit 前，你要先为每项技能判断 jd_importance、"
            "user_level、confidence、evidence、reason 和 recommended_action。\n"
            "普通概念解释、闲聊、总结对话或与岗位面试无关的问题不需要调用工具。\n"
            "工具返回的 JD 是依据，不要把原文字段机械堆给用户。\n"
            "你必须只返回 JSON，不要返回 Markdown，不要返回解释 JSON 之外的文字。\n"
            "JSON 必须包含四个字段：\n"
            "- answer: 字符串，3 到 6 句话\n"
            "- next_task: 字符串，一个很小的下一步任务\n"
            "- exercise: 字符串，一个小练习\n"
            "- checkpoints: 字符串数组，3 个检查点",
        ),
        (
            "system",
            "以下是这个会话较早历史的摘要。它用于帮助你理解上下文，"
            "但本轮回答仍然要优先回答用户最后的问题。\n"
            "第 1-8 轮摘要：用户在学习 FastAPI 路由和 SQLite 基础。",
        ),
        ("user", "第 9 轮用户问题"),
        ("assistant", "第 9 轮导师回答"),
        ("user", "第 10 轮用户问题"),
        ("assistant", "第 10 轮导师回答"),
        ("user", "第 11 轮用户问题"),
        ("assistant", "第 11 轮导师回答"),
        ("user", "第 12 轮用户问题"),
        ("assistant", "第 12 轮导师回答"),
        ("user", "第 13 轮用户问题"),
        ("assistant", "第 13 轮导师回答"),
        ("user", "第 14 轮用户问题"),
        ("assistant", "第 14 轮导师回答"),
        ("user", "第 15 轮当前问题"),
    ]
