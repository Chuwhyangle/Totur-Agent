"""pytest 全局 fixture。"""

import pytest


@pytest.fixture(autouse=True)
def skip_trace_writes(monkeypatch):
    """测试期间不写真实 MySQL：把埋点函数换成空操作。

    tutor_agent_service 用的是 from-import（`from app.db.trace_db import
    save_trace`），名字已经绑定在 service 模块里，所以要 patch 的是
    service 模块上的 save_trace，而不是 trace_db 模块里的定义。
    """

    monkeypatch.setattr(
        "app.services.tutor_agent_service.save_trace",
        lambda *args, **kwargs: None,
    )
