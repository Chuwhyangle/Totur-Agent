"""人工真实模型调用检查脚本。"""

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.clients.llm_client import create_llm_client
from app.config import load_llm_config
from app.db.models import ConversationRecord
from app.services.agent.context import AgentContext
from app.services.agent.prompt_builder import PromptBuilder
from app.services.agent.response_parser import ResponseParser


def _reply_json(answer: str) -> str:
    """生成一条历史导师回复 JSON。"""

    return json.dumps(
        {
            "answer": answer,
            "next_task": "下一步任务",
            "exercise": "小练习",
            "checkpoints": ["检查点"],
        },
        ensure_ascii=False,
    )


def main() -> None:
    """构造真实上下文并调用当前配置的模型。"""

    recent_history = [
        ConversationRecord(
            id=14,
            session_id=10,
            user_id="alice",
            message="第 14 轮用户问题：SQLite 的索引什么时候有用？",
            reply_json=_reply_json(
                "索引在你经常按某个字段查询、排序或关联时有用，但写入会稍微变慢。"
            ),
            created_at="",
        ),
        ConversationRecord(
            id=13,
            session_id=10,
            user_id="alice",
            message="第 13 轮用户问题：那 primary key 是不是自动有索引？",
            reply_json=_reply_json("通常主键会自动建立索引，所以按主键查找会很快。"),
            created_at="",
        ),
        ConversationRecord(
            id=12,
            session_id=10,
            user_id="alice",
            message="第 12 轮用户问题：SQLite 里的表和 Python class 有什么区别？",
            reply_json=_reply_json(
                "表是数据库里存数据的结构，class 是 Python 里描述对象行为和数据的代码结构。"
            ),
            created_at="",
        ),
        ConversationRecord(
            id=11,
            session_id=10,
            user_id="alice",
            message="第 11 轮用户问题：FastAPI route 最终是怎么连到 service 的？",
            reply_json=_reply_json(
                "Route 接收 HTTP 请求并做参数校验，然后调用 service 执行业务流程。"
            ),
            created_at="",
        ),
        ConversationRecord(
            id=10,
            session_id=10,
            user_id="alice",
            message="第 10 轮用户问题：Repository 为什么不要写在 route 里？",
            reply_json=_reply_json(
                "Repository 放在独立层可以隔离数据库细节，让 route 保持只处理 HTTP 输入输出。"
            ),
            created_at="",
        ),
        ConversationRecord(
            id=9,
            session_id=10,
            user_id="alice",
            message="第 9 轮用户问题：什么是 service 层？",
            reply_json=_reply_json(
                "Service 层负责组织业务流程，比如调用模型、保存对话、触发摘要更新。"
            ),
            created_at="",
        ),
    ]

    context = AgentContext(
        user_id="alice",
        session_id=10,
        current_message="第 15 轮当前问题：那我怎么判断一个功能应该放在 route、service 还是 repository？",
        summary_text=(
            "第 1-8 轮摘要：用户在学习 FastAPI 路由、SQLite 基础、"
            "分层结构和对话历史保存。用户容易混淆 route、service、repository 的职责边界。"
        ),
        recent_history=recent_history,
    )

    messages = PromptBuilder(ResponseParser()).build_messages(context)
    config = load_llm_config()
    client = create_llm_client(config)

    print("=== MODEL ===")
    print(config.model)
    print("\n=== LLM_INPUT_MESSAGES ===")
    print(json.dumps(messages, ensure_ascii=False, indent=2))

    completion = client.chat.completions.create(
        model=config.model,
        messages=messages,
    )
    raw_reply = completion.choices[0].message.content

    print("\n=== LLM_RAW_OUTPUT ===")
    print(raw_reply)

    print("\n=== PARSED_REPLY ===")
    parsed = ResponseParser().parse_model_reply(raw_reply or "")
    print(json.dumps(parsed.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
