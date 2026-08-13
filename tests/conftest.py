"""pytest 全局 fixture。

埋点函数的 patch 路径必须与 import 风格一致：
`from X import f` 要 patch 使用处；`from X import module` 后调用
`module.f()` 可以 patch 定义处。
"""

import pytest


@pytest.fixture(autouse=True)
def skip_trace_writes(monkeypatch):
    """测试期间不写真实 MySQL，并阻止漏网调用静默污染真实库。"""

    monkeypatch.setattr(
        "app.services.tutor_agent_service.save_trace",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.db.trace_db.save_retrieval_event",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.agent.react_orchestrator.save_llm_call",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.agent.tools.executor.save_tool_call",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.agent.react_orchestrator.save_tool_call",
        lambda *args, **kwargs: None,
    )

    def _forbid_real_db():
        raise RuntimeError("测试期间禁止连接真实 MySQL")

    monkeypatch.setattr(
        "app.db.trace_db.load_db_config",
        _forbid_real_db,
    )
