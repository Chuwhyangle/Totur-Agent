# JD 技能匹配评分工具设计

## 1. 背景

当前 Tutor Agent 已经有 `interview_jd_search` 工具，可以把已保存的技术岗位 JD 检索出来，提供岗位职责、核心技能、关键词和面试重点。

用户查完岗位要求后的自然下一步不是直接进入模拟面试，而是先回答：

- 这个岗位要求哪些技术栈？
- 我自己已经会哪些？
- 哪些技能只是听过、做过 demo，还是已经能独立落地？
- 我的项目经历和 JD 的符合程度大概是多少？
- 哪些短板最值得优先补？

这些判断涉及自然语言理解、项目经验映射和语义推理，完全程序化会非常脆。因此第二个工具不负责判断用户会不会某项技能，而是接收 LLM 已经做出的结构化判断，负责校验、加权计算和稳定输出。

## 2. 工具定位

工具名：

```text
score_jd_skill_fit
```

一句话定位：

```text
基于 LLM 给出的逐项技能判断，计算用户与目标 JD 的加权符合度，并返回每项技能掌握程度、优势、短板和不确定项。
```

核心边界：

```text
LLM 判断，工具算分。
```

LLM 负责：

- 阅读 JD 搜索结果。
- 阅读用户自述技能栈和项目经历。
- 判断每项技能对 JD 的重要程度。
- 判断用户对每项技能的掌握程度。
- 给出证据、风险和补足建议。

工具负责：

- 校验输入结构。
- 把 `jd_importance` 限制在 1 到 5。
- 把 `user_level` 限制在 0 到 5。
- 按固定公式计算总符合度。
- 按加权缺口提取最大短板。
- 按掌握程度和重要性提取优势项。
- 按 `confidence` 提取不确定项。
- 返回稳定结构，方便测试、前端调试和后续保存技能画像。

## 3. 非目标

第一版不做：

- 不直接解析用户自然语言。
- 不调用 LLM。
- 不读取 SQLite。
- 不检索 JD。
- 不保存长期技能画像。
- 不生成完整学习计划。
- 不判断用户回答某道面试题的质量。
- 不替代 `interview_jd_search`。
- 不实现 ReAct 循环本身。

## 4. 使用流程

推荐对话流程：

```text
用户：我想看看 AI Agent 岗位需要哪些技能。
Agent：调用 interview_jd_search。
Agent：总结 JD 技能要求，并询问用户当前技术栈和项目经历。
用户：我会 Python、FastAPI、React，做过 Tutor Agent，RAG 看过一点。
Agent：根据 JD + 用户自述，自己给每项技能生成结构化评分。
Agent：调用 score_jd_skill_fit。
工具：计算 JD 符合度、逐项加权分、优势、短板、不确定项。
Agent：基于工具结果解释分数，并给出补足建议。
```

## 5. 评分等级

`jd_importance` 表示技能对目标 JD 的重要程度：

```text
1 = 加分项
2 = 次要要求
3 = 常规要求
4 = 重要要求
5 = 核心要求
```

`user_level` 表示用户当前掌握程度：

```text
0 = 没接触或明确不会
1 = 听过或看过概念
2 = 跟教程做过，不能独立解释完整链路
3 = 能独立做基础功能，能解释主要流程
4 = 有项目实践，能排错和解释取舍
5 = 能设计方案、优化、应对深入追问
```

`confidence` 表示 LLM 对该项判断的信心：

```text
low
medium
high
```

## 6. 输入结构

```json
{
  "target_role": "AI Agent / LLM 应用开发",
  "skills": [
    {
      "name": "RAG",
      "jd_importance": 5,
      "user_level": 1,
      "confidence": "high",
      "evidence": "用户说 RAG 看过一点，但没完整做过。",
      "reason": "RAG 是 JD 核心要求，但用户缺少完整实践。",
      "recommended_action": "做一个最小 RAG 闭环，覆盖 chunk、embedding、检索、生成。"
    }
  ]
}
```

字段要求：

- `target_role`：可选字符串，用于 trace 和最终解释。
- `skills`：必填数组，至少一项。
- `name`：必填非空字符串。
- `jd_importance`：必填数字或可解析数字，工具归一化到 1-5。
- `user_level`：必填数字或可解析数字，工具归一化到 0-5。
- `confidence`：可选，非法值归一化为 `medium`。
- `evidence`：可选字符串。
- `reason`：可选字符串。
- `recommended_action`：可选字符串。

## 7. 计算规则

单项分：

```text
weighted_score = jd_importance * user_level
weighted_max = jd_importance * 5
gap = 5 - user_level
weighted_gap = jd_importance * gap
```

总符合度：

```text
fit_score = round(sum(weighted_score) / sum(weighted_max) * 100)
```

等级：

```text
0-39   = low_fit
40-69  = partial_fit
70-84  = good_fit
85-100 = strong_fit
```

优势项：

```text
user_level >= 4
```

重点短板：

```text
jd_importance >= 4 且 user_level <= 2
```

不确定项：

```text
confidence 为 low 或 medium
```

排序：

- `top_strengths` 按 `user_level` 降序，再按 `jd_importance` 降序。
- `top_gaps` 按 `weighted_gap` 降序，再按 `jd_importance` 降序。
- `uncertain_skills` 保持技能原始顺序。

## 8. 输出结构

成功：

```json
{
  "ok": true,
  "target_role": "AI Agent / LLM 应用开发",
  "fit_score": 56,
  "fit_level": "partial_fit",
  "max_score": 100,
  "skill_scores": [
    {
      "name": "RAG",
      "jd_importance": 5,
      "user_level": 1,
      "confidence": "high",
      "weighted_score": 5,
      "weighted_max": 25,
      "gap": 4,
      "weighted_gap": 20,
      "evidence": "用户说 RAG 看过一点，但没完整做过。",
      "reason": "RAG 是 JD 核心要求，但用户缺少完整实践。",
      "recommended_action": "做一个最小 RAG 闭环。"
    }
  ],
  "top_strengths": ["Python", "FastAPI"],
  "top_gaps": ["RAG", "Vector Database"],
  "uncertain_skills": ["LLM API", "Function Calling"],
  "summary": {
    "skill_count": 7,
    "high_importance_gap_count": 2,
    "uncertain_skill_count": 2
  }
}
```

错误：

```json
{
  "ok": false,
  "error": "invalid_arguments",
  "message": "skills must be a non-empty list."
}
```

## 9. Agent 使用规则

Agent 不应该把这个工具当作语义判断器。调用前必须先自己阅读 JD、用户技能自述和项目经历，然后构造逐项技能评分。

推荐行为：

- 先调用 `interview_jd_search` 获取岗位要求。
- 向用户询问当前技术栈和项目经历。
- 由 LLM 判断每项技能的 `jd_importance`、`user_level`、`confidence`、`evidence` 和 `recommended_action`。
- 调用 `score_jd_skill_fit` 计算总分和排序。
- 最终回复中说明分数只是面试准备参考，不是招聘结论。
- 对 `confidence=low/medium` 的技能，优先给出深度测试问题，而不是直接判定用户不会。

禁止行为：

- 不要让工具直接处理大段自然语言。
- 不要伪造用户没有提供过的项目证据。
- 不要把 `fit_score` 表达成真实招聘通过概率。
- 不要只给总分而不解释关键短板。

## 10. 前端调试展示

`tool_trace.calls[].result_preview` 第一版应支持技能匹配工具的轻量预览：

```json
{
  "target_role": "AI Agent / LLM 应用开发",
  "fit_score": 56,
  "fit_level": "partial_fit",
  "top_strengths": ["Python", "FastAPI"],
  "top_gaps": ["RAG", "Vector Database"],
  "uncertain_skills": ["LLM API", "Function Calling"]
}
```

这样前端 debug 区可以看见 Agent 不是随口说 56%，而是工具按固定公式计算出来的。

## 11. 验收标准

- `ToolRegistry.get_tools_schema()` 同时暴露 `interview_jd_search` 和 `score_jd_skill_fit`。
- `score_jd_skill_fit` schema 只要求 `skills`，允许传 `target_role`。
- `score_jd_skill_fit` 对合法技能数组返回 `ok=true`。
- 工具按固定公式计算 `fit_score`。
- 工具把越界分数归一化到合法范围。
- 工具拒绝空 `skills`。
- 工具拒绝没有有效 `name` 的技能项。
- `ToolExecutor` 可以执行 `score_jd_skill_fit`。
- `/chat` 的 `tool_trace` 可以展示技能匹配工具的轻量预览。
- 现有 JD 搜索工具行为不变。

