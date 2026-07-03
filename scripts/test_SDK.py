"""阶段 1 的大模型 SDK 练习脚本。

这个文件负责：
1. 从 .env 读取模型配置。
2. 创建 OpenAI-compatible SDK 客户端。
3. 向模型发送一个学习问题。
4. 打印模型回复。

新手理解：
这是“阶段 1：先用脚本跑通模型调用”的练习文件。
它不是 FastAPI 接口，也不是前端页面。

运行方式：
python scripts/test_SDK.py
"""

import os

from dotenv import load_dotenv
from openai import OpenAI


def load_config():
    """Read OPENAI_API_KEY, OPENAI_BASE_URL, and OPENAI_MODEL from .env."""
    # 配置文件
    """把env中的信息加到环境变量中"""
    load_dotenv()

    base_url = os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")
    model_name = os.getenv("OPENAI_MODEL")

    if not base_url:
        raise RuntimeError("没有Base URL")
    if not api_key:
        raise RuntimeError("没有 api key")
    if not model_name:
        raise RuntimeError("没有选择model")

    return api_key, base_url, model_name
    


def create_client(api_key, base_url):
    """Create and return an OpenAI-compatible client."""
    # TODO: Return OpenAI(api_key=..., base_url=...).
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )
    return client


def ask_model(client, model, question):
    """Send one question to the model and return the reply text."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a helpful tutor. Answer clearly in Chinese.",
            },
            {
                "role": "user",
                "content": question,
            },
        ],
    )

    return response.choices[0].message.content


def main():
    question = "Explain what an SDK is in Chinese for a beginner."
    api_key, base_url, model_name = load_config()
    client = create_client(api_key, base_url)
    # TODO 3: Call ask_model(...).
    message = ask_model(client,model_name,question)
    # TODO 4: Print the reply.
    print(message)
    


if __name__ == "__main__":
    main()
