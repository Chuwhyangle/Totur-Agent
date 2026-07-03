"""应用配置读取层。

这个文件负责：
1. 从环境变量读取模型相关配置。
2. 把散落的 OPENAI_API_KEY、OPENAI_BASE_URL、OPENAI_MODEL 统一收拢。
3. 给 service 层提供一个清楚的配置入口。

新手理解：
你可以把这里看成“后端启动前的参数说明书”。
后面如果要接数据库、缓存、其他模型供应商，也可以继续往这里扩展。
"""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass
class LLMConfig:
    """大模型客户端所需的基础配置。"""

    api_key: str
    base_url: str
    model: str


def load_llm_config() -> LLMConfig:
    """从 .env 读取大模型配置。

    TODO(阶段 4 - 配置任务 1):
    检查环境变量是否都存在。

    TODO(阶段 4 - 配置任务 2):
    如果缺少任何一项，抛出清晰的错误提示。

    TODO(阶段 4 - 配置任务 3):
    把读取结果封装进 LLMConfig 返回。
    """

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "")
    model = os.getenv("OPENAI_MODEL", "")

    if not base_url:
        raise RuntimeError("没有Base URL")
    if not api_key:
        raise RuntimeError("没有 api key")
    if not model:
        raise RuntimeError("没有选择model")

    return LLMConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
