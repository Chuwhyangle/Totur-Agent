"""健康检查接口路由文件。

这个文件负责：
1. 定义 GET /health 接口。
2. 返回服务是否正常运行的简单状态。

新手理解：
/health 不处理聊天、不调用模型、不访问数据库。
它只回答一个问题：后端服务现在还活着吗？
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """健康检查接口。

    用途：
    1. 确认 FastAPI 服务已经启动。
    2. 给你练习第一个 GET 接口。
    3. 后续部署时也可以用它判断服务是否活着。
    """

    return {
        "status": "ok",
        "service": "tutor-agent-api",
    }
