"""Small script for testing the configured model client."""

import os

from dotenv import load_dotenv
from openai import OpenAI


def load_config():
    """Read OPENAI_API_KEY, OPENAI_BASE_URL, and OPENAI_MODEL from .env."""

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

    return OpenAI(
        api_key=api_key,
        base_url=base_url,
    )


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
    message = ask_model(client, model_name, question)
    print(message)


if __name__ == "__main__":
    main()
