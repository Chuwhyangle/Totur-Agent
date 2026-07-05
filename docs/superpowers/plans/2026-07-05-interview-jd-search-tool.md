# Interview JD Search Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first backend tool foundation: `interview_jd_search`, which searches saved JD records by natural-language query without exposing database ids.

**Architecture:** Add one repository query for all JD records, one focused search tool module, and small `ToolRegistry` / `ToolExecutor` modules under `app/services/agent/tools/`. This phase does not yet modify `/chat` model orchestration; it prepares the callable tool surface and verifies it independently.

**Tech Stack:** FastAPI backend, SQLite, pytest, Python dataclasses/dicts, OpenAI-compatible tool schema.

---

## File Structure

- Modify: `app/repositories/interview_jd_repository.py`
  - Add `list_all_interview_jds(limit: int = 100)`.
- Create: `app/services/agent/tools/__init__.py`
  - Expose tool modules as an importable package.
- Create: `app/services/agent/tools/interview_jd_search.py`
  - Implement `search_interview_jds(query: str, limit: int = 3) -> dict`.
- Create: `app/services/agent/tools/registry.py`
  - Provide OpenAI-compatible schema for `interview_jd_search`.
- Create: `app/services/agent/tools/executor.py`
  - Validate tool name and arguments, execute registered tool, return structured results.
- Create: `tests/test_interview_jd_search.py`
  - Verify search behavior and no database id leakage.
- Create: `tests/test_agent_tools.py`
  - Verify registry schema and executor behavior.

---

### Task 1: JD Search Tests

**Files:**
- Create: `tests/test_interview_jd_search.py`

- [x] **Step 1: Write failing JD search tests**

```python
from app.db import database
from app.repositories.interview_jd_repository import create_interview_jd
from app.services.agent.tools.interview_jd_search import search_interview_jds


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test_tutor_agent.db")


def create_agent_jd():
    return create_interview_jd(
        user_id="demo-user",
        title="Python AI Agent 开发工程师",
        role_family="python_ai_agent_engineer",
        seniority="junior_mid",
        raw_text="负责基于 LLM 的 AI Agent 开发，构建具备工具调用和 RAG 能力的智能应用。",
        responsibilities=["基于 LLM 开发 AI Agent", "封装 Function Calling 工具接口"],
        must_have=["Python 编程能力", "大模型 API 调用经验"],
        core_skills=["Python", "LLM API", "Function Calling", "RAG"],
        preferred_skills=["MCP", "A2A"],
        bonus_skills=["NetOps/AIOps"],
        keywords=["Python", "Agent", "LLM", "Function Calling", "RAG"],
        interview_focus=["Agent 工具调用流程", "RAG 基本架构"],
    )


def create_fullstack_jd():
    return create_interview_jd(
        user_id="demo-user",
        title="AI 全栈开发工程师",
        role_family="ai_fullstack_engineer",
        seniority="graduate",
        raw_text="负责 Java/Python/Vue 的系统服务与 AI 应用开发。",
        responsibilities=["前后端一体化开发", "AI 应用开发"],
        must_have=["算法数据结构", "Web API 设计"],
        core_skills=["Java", "Python", "Vue", "数据库"],
        preferred_skills=["AI 开发工具", "系统架构"],
        bonus_skills=["Cursor", "Claude Code"],
        keywords=["AI 全栈", "Vue", "Java", "Python"],
        interview_focus=["Web 架构", "API 设计", "AI 工具协作"],
    )


def test_search_interview_jds_finds_agent_jd_without_exposing_database_id(
    monkeypatch,
    tmp_path,
):
    use_temp_database(monkeypatch, tmp_path)
    create_fullstack_jd()
    create_agent_jd()

    result = search_interview_jds("Agent 工具调用 RAG 面试", limit=3)

    assert result["ok"] is True
    assert result["summary"]["searched_count"] == 2
    assert result["items"][0]["title"] == "Python AI Agent 开发工程师"
    assert result["items"][0]["match_score"] > 0
    assert "id" not in result["items"][0]
    assert "raw_text_excerpt" in result["items"][0]
    assert {
        "core_skills",
        "keywords",
        "interview_focus",
    }.intersection(result["items"][0]["matched_fields"])


def test_search_interview_jds_respects_limit(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    create_agent_jd()
    create_fullstack_jd()

    result = search_interview_jds("AI Python", limit=1)

    assert result["ok"] is True
    assert result["summary"]["returned_count"] == 1
    assert len(result["items"]) == 1


def test_search_interview_jds_returns_empty_items_for_no_match(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    create_agent_jd()

    result = search_interview_jds("量子通信产品经理", limit=3)

    assert result["ok"] is True
    assert result["items"] == []
    assert result["summary"] == {
        "returned_count": 0,
        "searched_count": 1,
    }
    assert result["message"] == "No interview JD matched the query."


def test_search_interview_jds_rejects_empty_query(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    result = search_interview_jds("   ", limit=3)

    assert result == {
        "ok": False,
        "error": "invalid_arguments",
        "message": "query must be a non-empty string.",
    }
```

- [x] **Step 2: Run JD search tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_interview_jd_search.py -q
```

Expected: FAIL because `app.services.agent.tools.interview_jd_search` does not exist.

---

### Task 2: JD Search Implementation

**Files:**
- Modify: `app/repositories/interview_jd_repository.py`
- Create: `app/services/agent/tools/__init__.py`
- Create: `app/services/agent/tools/interview_jd_search.py`

- [x] **Step 1: Add repository query for all JD records**

Add `list_all_interview_jds(limit: int = 100) -> list[InterviewJDRecord]`, selecting the same columns as `list_interview_jds` but without `WHERE user_id = ?`.

- [x] **Step 2: Implement keyword search**

Implement `search_interview_jds(query: str, limit: int = 3) -> dict` with:

- Empty query returns `ok=false`.
- `limit` is clamped to `1..5`.
- Search all saved JD records via `list_all_interview_jds()`.
- Score fields with these weights:
  - `title`, `role_family`: 4
  - `core_skills`, `keywords`, `interview_focus`: 3
  - `responsibilities`, `must_have`, `preferred_skills`, `bonus_skills`: 2
  - `raw_text`: 1
- Return only records with positive score.
- Sort by `match_score` descending.
- Do not include database `id` in tool output.

- [x] **Step 3: Run JD search tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_interview_jd_search.py -q
```

Expected: PASS.

---

### Task 3: Tool Registry and Executor Tests

**Files:**
- Create: `tests/test_agent_tools.py`

- [x] **Step 1: Write failing registry/executor tests**

```python
from app.db import database
from app.repositories.interview_jd_repository import create_interview_jd
from app.services.agent.tools.executor import ToolExecutor
from app.services.agent.tools.registry import ToolRegistry


def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test_tutor_agent.db")


def test_tool_registry_exposes_interview_jd_search_schema():
    registry = ToolRegistry()

    tools = registry.get_tools_schema()
    tool = tools[0]
    parameters = tool["function"]["parameters"]

    assert tool["type"] == "function"
    assert tool["function"]["name"] == "interview_jd_search"
    assert set(parameters["properties"]) == {"query", "limit"}
    assert parameters["required"] == ["query"]
    assert "id" not in parameters["properties"]


def test_tool_executor_runs_interview_jd_search(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    create_interview_jd(
        user_id="demo-user",
        title="Python AI Agent 开发工程师",
        raw_text="负责 Agent 工具调用和 RAG 应用开发。",
        core_skills=["Function Calling", "RAG"],
        keywords=["Agent", "RAG"],
        interview_focus=["Agent 工具调用"],
    )
    executor = ToolExecutor()

    result = executor.execute(
        "interview_jd_search",
        {"query": "Agent RAG", "limit": 1},
    )

    assert result["ok"] is True
    assert result["items"][0]["title"] == "Python AI Agent 开发工程师"


def test_tool_executor_accepts_json_string_arguments(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    create_interview_jd(
        user_id="demo-user",
        title="AI 全栈开发工程师",
        raw_text="负责 Vue 和 Python AI 应用开发。",
        keywords=["Vue", "Python", "AI 全栈"],
    )
    executor = ToolExecutor()

    result = executor.execute(
        "interview_jd_search",
        '{"query": "Vue 全栈", "limit": 1}',
    )

    assert result["ok"] is True
    assert result["items"][0]["title"] == "AI 全栈开发工程师"


def test_tool_executor_returns_structured_error_for_unknown_tool():
    executor = ToolExecutor()

    result = executor.execute("unknown_tool", {"query": "Agent"})

    assert result == {
        "ok": False,
        "error": "tool_not_found",
        "message": "unknown tool: unknown_tool",
    }


def test_tool_executor_returns_structured_error_for_invalid_arguments():
    executor = ToolExecutor()

    result = executor.execute("interview_jd_search", "{bad json")

    assert result == {
        "ok": False,
        "error": "invalid_arguments",
        "message": "tool arguments must be a JSON object.",
    }
```

- [x] **Step 2: Run registry/executor tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agent_tools.py -q
```

Expected: FAIL because `registry.py` and `executor.py` do not exist.

---

### Task 4: Tool Registry and Executor Implementation

**Files:**
- Create: `app/services/agent/tools/registry.py`
- Create: `app/services/agent/tools/executor.py`

- [x] **Step 1: Implement registry**

`ToolRegistry` should expose:

- `get_tools_schema() -> list[dict]`
- `has_tool(name: str) -> bool`
- `get_tool(name: str) -> Callable | None`

Only `interview_jd_search` is registered.

- [x] **Step 2: Implement executor**

`ToolExecutor.execute(name, arguments)` should:

- Return `tool_not_found` for unknown tools.
- Accept `dict` arguments or JSON object strings.
- Return `invalid_arguments` for malformed JSON, non-object JSON, or non-dict arguments.
- Execute the registered function and return its result.
- Catch unexpected exceptions and return `tool_execution_failed`.

- [x] **Step 3: Run registry/executor tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agent_tools.py -q
```

Expected: PASS.

---

### Task 5: Verification

**Files:**
- No new files.

- [x] **Step 1: Run focused backend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_interview_jds.py tests/test_interview_jd_search.py tests/test_agent_tools.py -q
```

Expected: PASS.

- [x] **Step 2: Run broader backend regression tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_stage2_api.py tests/test_interview_jds.py tests/test_interview_jd_search.py tests/test_agent_tools.py -q
```

Expected: PASS.

- [x] **Step 3: Compile Python files**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall app tests
```

Expected: exit code 0.

---

## Self-Review

- Spec coverage: This plan implements `interview_jd_search`, `ToolRegistry`, and `ToolExecutor`. It intentionally does not yet modify `/chat` orchestration; that remains the next plan after the callable tool surface is tested.
- Placeholder scan: No TBD/TODO placeholders.
- Type consistency: Tool inputs are `query` and `limit`; outputs omit database `id`; executor accepts dict or JSON object string arguments.
