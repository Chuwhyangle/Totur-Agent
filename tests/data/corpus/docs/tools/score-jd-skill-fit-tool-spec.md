# Tool Spec: score_jd_skill_fit

## 1. 工具定位

`score_jd_skill_fit` 是 Tutor Agent 的第二个工具。它用于根据 LLM 已经整理好的逐项技能判断，计算用户与目标 JD 的加权符合程度。

这个工具不负责理解自然语言，也不负责判断用户是否真的掌握某项技能。语义判断由 LLM 完成，工具只负责校验、归一化、加权计算和稳定输出。

核心原则：

```text
LLM 判断，工具算分。
```

## 2. 目标

- 根据逐项技能评分计算 JD 总符合度。
- 返回每项技能的加权分、满分、缺口和加权缺口。
- 提取优势技能、重点短板和不确定技能。
- 为前端 debug trace 提供稳定结构。
- 为后续 ReAct 多工具循环提供第二个确定性工具。

## 3. 非目标

- 不读取 JD 数据库。
- 不检索岗位信息。
- 不解析用户自然语言。
- 不调用 LLM。
- 不生成完整学习计划。
- 不保存技能画像。
- 不评价某一道面试回答。

## 4. 工具接口

工具名：

```text
score_jd_skill_fit
```

工具描述：

```text
Calculate a weighted JD skill fit score from LLM-provided per-skill judgments.
```

Python 调用边界：

```python
def score_jd_skill_fit(skills: list[dict[str, Any]], target_role: str | None = None) -> dict[str, Any]:
    ...
```

## 5. 参数

`target_role`

- 可选。
- 字符串。
- 用于标记当前评分针对的岗位方向。

`skills`

- 必填。
- 非空数组。
- 每一项代表 LLM 对一个技能的结构化判断。

技能项字段：

- `name`：必填，非空字符串。
- `jd_importance`：必填，1-5，表示技能对 JD 的重要程度。
- `user_level`：必填，0-5，表示用户当前掌握程度。
- `confidence`：可选，`low`、`medium` 或 `high`。
- `evidence`：可选，LLM 判断依据。
- `reason`：可选，评分原因。
- `recommended_action`：可选，补足建议原材料。

## 6. 评分规则

工具会把 `jd_importance` 归一化到 1-5，把 `user_level` 归一化到 0-5。

```text
weighted_score = jd_importance * user_level
weighted_max = jd_importance * 5
gap = 5 - user_level
weighted_gap = jd_importance * gap
fit_score = round(sum(weighted_score) / sum(weighted_max) * 100)
```

等级：

```text
0-39   low_fit
40-69  partial_fit
70-84  good_fit
85-100 strong_fit
```

## 7. 成功返回

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
      "evidence": "用户说 RAG 看过一点。",
      "reason": "RAG 是 JD 核心要求。",
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

## 8. 错误返回

空 `skills`：

```json
{
  "ok": false,
  "error": "invalid_arguments",
  "message": "skills must be a non-empty list."
}
```

技能项缺少有效名称：

```json
{
  "ok": false,
  "error": "invalid_arguments",
  "message": "each skill must include a non-empty name."
}
```

## 9. Agent 使用规则

Agent 应该先用 `interview_jd_search` 查岗位要求，再询问用户当前技术栈和项目经历。

当 Agent 具备这两类信息后，由 LLM 自己推理每项技能的：

- `jd_importance`
- `user_level`
- `confidence`
- `evidence`
- `reason`
- `recommended_action`

然后调用 `score_jd_skill_fit` 计算总分。

最终回复时，Agent 应该说明：

- 总分是面试准备参考，不是招聘通过概率。
- 高分技能可以包装成优势。
- 高重要度低掌握度技能应优先补。
- 不确定技能应该通过深度问题继续测试。

