"""MCP prompts derived from Tutor Agent personas and teaching flows."""
from __future__ import annotations
from app.services.agent.personas import build_system_prompt, get_persona

def render_persona_prompt(persona_id: str) -> str:
    return build_system_prompt(get_persona(persona_id))

def render_quiz_prompt(topic: str, count: int = 3) -> str:
    safe_count = max(1, min(int(count or 3), 5))
    topic_text = (topic or "").strip() or "当前学习主题"
    return (
        "你是 Tutor Agent 的测验教练。\n"
        f"主题：{topic_text}\n"
        f"先调用 generate_quiz，count={safe_count}，基于本地学习笔记生成题目。\n"
        "一次只问一道题；等待回答后，按 checkpoints 点评，再进入下一题。\n"
        "不得编造笔记来源；检索为空时明确说明。"
    )

def render_interview_prompt(target_role: str) -> str:
    role = (target_role or "").strip() or "目标技术岗位"
    return f"你是 {role} 的模拟面试官。先调用 interview_jd_search 获取依据，必要时调用 score_jd_skill_fit。一次只问一个问题，回答后指出亮点、缺口和追问方向。"
