# Score JD Skill Fit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `score_jd_skill_fit`, a deterministic scoring and validation tool that computes JD fit from LLM-provided per-skill judgments.

**Architecture:** Keep semantic judgment in the LLM and deterministic scoring in a small Python tool. Register the tool through the existing `ToolRegistry` and execute it through the existing `ToolExecutor`; extend chat trace preview so frontend debug output can show score summaries.

**Tech Stack:** Python, FastAPI service layer, existing Tutor Agent tool registry/executor, pytest.

---

## File Structure

- Create `app/services/agent/tools/score_jd_skill_fit.py`: pure scoring function and small normalization helpers.
- Modify `app/services/agent/tools/registry.py`: add OpenAI-compatible schema and register the callable.
- Modify `app/services/tutor_agent_service.py`: extend tool trace preview for non-JD tool results.
- Modify `tests/test_agent_tools.py`: add unit tests for schema exposure, executor execution, score formula, clamping, and invalid inputs.
- Modify `tests/test_stage2_api.py`: add chat trace test for `score_jd_skill_fit`.
- Create `docs/tools/score-jd-skill-fit-tool-spec.md`: operational tool spec aligned with the design.

## Task 1: Failing Tool Tests

**Files:**
- Modify: `tests/test_agent_tools.py`

- [ ] **Step 1: Add tests for schema, scoring, clamping, and invalid inputs**

Add tests that import `score_jd_skill_fit` and assert:

```python
def test_tool_registry_exposes_score_jd_skill_fit_schema():
    registry = ToolRegistry()
    names = [tool["function"]["name"] for tool in registry.get_tools_schema()]
    assert names == ["interview_jd_search", "score_jd_skill_fit"]


def test_score_jd_skill_fit_calculates_weighted_fit_score():
    result = score_jd_skill_fit(
        target_role="AI Agent / LLM 应用开发",
        skills=[
            {
                "name": "Python",
                "jd_importance": 5,
                "user_level": 4,
                "confidence": "high",
                "evidence": "做过 FastAPI 后端。",
            },
            {
                "name": "RAG",
                "jd_importance": 5,
                "user_level": 1,
                "confidence": "high",
            },
            {
                "name": "Function Calling",
                "jd_importance": 4,
                "user_level": 3,
                "confidence": "medium",
            },
        ],
    )
    assert result["ok"] is True
    assert result["fit_score"] == 53
    assert result["fit_level"] == "partial_fit"
    assert result["top_strengths"] == ["Python"]
    assert result["top_gaps"] == ["RAG"]
    assert result["uncertain_skills"] == ["Function Calling"]
```

- [ ] **Step 2: Run tests to verify RED**

Run: `pytest tests/test_agent_tools.py -q`

Expected: fail because `app.services.agent.tools.score_jd_skill_fit` does not exist or the registry does not expose the new tool.

## Task 2: Minimal Tool Implementation

**Files:**
- Create: `app/services/agent/tools/score_jd_skill_fit.py`
- Modify: `app/services/agent/tools/registry.py`

- [ ] **Step 1: Implement `score_jd_skill_fit`**

Create a pure function:

```python
def score_jd_skill_fit(
    skills: list[dict[str, Any]],
    target_role: str | None = None,
) -> dict[str, Any]:
    ...
```

It validates non-empty `skills`, normalizes numeric fields, computes weighted scores, and returns `ok=true` with `fit_score`, `fit_level`, `skill_scores`, `top_strengths`, `top_gaps`, `uncertain_skills`, and `summary`.

- [ ] **Step 2: Register schema and callable**

Modify `ToolRegistry` so `get_tools_schema()` returns both tools in this order:

```python
[
    deepcopy(INTERVIEW_JD_SEARCH_SCHEMA),
    deepcopy(SCORE_JD_SKILL_FIT_SCHEMA),
]
```

- [ ] **Step 3: Run tests to verify GREEN**

Run: `pytest tests/test_agent_tools.py -q`

Expected: pass.

## Task 3: Executor and Trace Coverage

**Files:**
- Modify: `tests/test_agent_tools.py`
- Modify: `tests/test_stage2_api.py`
- Modify: `app/services/tutor_agent_service.py`

- [ ] **Step 1: Add executor test**

Add a test that calls:

```python
ToolExecutor().execute(
    "score_jd_skill_fit",
    {
        "target_role": "AI Agent",
        "skills": [
            {"name": "Python", "jd_importance": 5, "user_level": 4},
            {"name": "RAG", "jd_importance": 5, "user_level": 1},
        ],
    },
)
```

Assert `ok=true`, `fit_score == 50`, and `top_gaps == ["RAG"]`.

- [ ] **Step 2: Add chat trace test**

In `tests/test_stage2_api.py`, add a fake first model response that tool-calls `score_jd_skill_fit`, a fake final model JSON reply, and assert the response `tool_trace.calls[0].result_preview` contains `target_role`, `fit_score`, `fit_level`, `top_strengths`, `top_gaps`, and `uncertain_skills`.

- [ ] **Step 3: Run trace tests to verify RED**

Run: `pytest tests/test_stage2_api.py::test_chat_traces_score_jd_skill_fit_preview -q`

Expected: fail because trace preview does not yet handle skill-fit result summaries.

- [ ] **Step 4: Extend trace preview**

Modify `TutorAgentService._tool_call_trace` so JD search results still use the existing item preview, and `score_jd_skill_fit` results use a summary preview list with one object:

```python
[
    {
        "target_role": result.get("target_role") or "",
        "fit_score": result.get("fit_score"),
        "fit_level": result.get("fit_level"),
        "top_strengths": result.get("top_strengths") or [],
        "top_gaps": result.get("top_gaps") or [],
        "uncertain_skills": result.get("uncertain_skills") or [],
    }
]
```

- [ ] **Step 5: Run trace tests to verify GREEN**

Run: `pytest tests/test_stage2_api.py::test_chat_traces_score_jd_skill_fit_preview -q`

Expected: pass.

## Task 4: Documentation

**Files:**
- Create: `docs/tools/score-jd-skill-fit-tool-spec.md`
- Modify: `docs/tools/chat-interview-jd-tool-calling.md`
- Modify: `docs/main-quest-progress.md`

- [ ] **Step 1: Write tool spec**

Document the tool name, scope, input schema, scoring formula, output shape, error behavior, and Agent usage rule: LLM judges, tool scores.

- [ ] **Step 2: Update tool-calling docs**

Add a short section explaining that the next ReAct direction has two tools:

```text
interview_jd_search = 找岗位要求
score_jd_skill_fit = 对 LLM 给出的技能评分做确定性计算
```

- [ ] **Step 3: Update progress docs**

Record that the second tool has been designed and implemented as a deterministic scoring helper, not a semantic parser.

## Task 5: Verification

**Files:**
- No file edits.

- [ ] **Step 1: Run focused tests**

Run: `pytest tests/test_agent_tools.py tests/test_stage2_api.py::test_chat_traces_score_jd_skill_fit_preview -q`

Expected: pass.

- [ ] **Step 2: Run full backend test suite**

Run: `pytest -q`

Expected: pass.

- [ ] **Step 3: Review git diff**

Run: `git diff --stat`

Expected: changes limited to tool implementation, tests, and docs.

