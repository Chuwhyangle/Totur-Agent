# Interview JD Storage Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first JD storage foundation so users can save and list technical interview job descriptions before we design JD-aware tools.

**Architecture:** Add a SQLite-backed `interview_jds` resource following the existing schema/repository/route pattern. Add a small React form panel that posts JD data and lists saved JD records for the current `user_id`.

**Tech Stack:** FastAPI, Pydantic, SQLite, pytest, React, Vite, browser `fetch`.

---

## File Structure

- Modify: `docs/superpowers/specs/2026-07-04-technical-interview-tool-calling-design.md`
  - Adds the JD storage extension section.
- Modify: `app/db/models.py`
  - Adds `INTERVIEW_JDS_TABLE` and `InterviewJDRecord`.
- Modify: `app/db/database.py`
  - Creates `interview_jds` and an index by `user_id`.
- Create: `app/schemas/interview_jds.py`
  - Defines request and response models for JD storage.
- Create: `app/repositories/interview_jd_repository.py`
  - Creates and lists JD records.
- Create: `app/api/routes/interview_jds.py`
  - Adds `POST /interview-jds` and `GET /interview-jds`.
- Modify: `app/main.py`
  - Registers the new router.
- Create: `tests/test_interview_jds.py`
  - Covers database initialization, repository behavior, and API behavior.
- Modify: `frontend/src/api/tutorApi.js`
  - Adds `createInterviewJD` and `getInterviewJDs`.
- Create: `frontend/src/components/InterviewJDPanel.jsx`
  - Adds the first JD form and saved JD list.
- Modify: `frontend/src/App.jsx`
  - Loads JD records and renders the panel.
- Modify: `frontend/src/styles/app.css`
  - Adds responsive JD panel styles.

---

### Task 1: Update Design Doc

**Files:**
- Modify: `docs/superpowers/specs/2026-07-04-technical-interview-tool-calling-design.md`

- [x] **Step 1: Add JD storage extension**

Add a section explaining why user-pasted JD data lives in SQLite, which fields are needed, and why tools come after storage.

- [x] **Step 2: Review for scope**

Confirm this phase does not implement `interview_jd_search`, `jd_project_match`, RAG, MCP, upload parsing, edit, or delete.

---

### Task 2: Backend JD Storage Tests

**Files:**
- Create: `tests/test_interview_jds.py`

- [ ] **Step 1: Write failing tests**

Create tests for:

```python
def test_initialize_database_creates_interview_jds_table(monkeypatch, tmp_path):
    ...

def test_create_and_list_interview_jds(monkeypatch, tmp_path):
    ...

def test_post_interview_jds_creates_record(monkeypatch, tmp_path):
    ...

def test_get_interview_jds_returns_current_user_records(monkeypatch, tmp_path):
    ...

def test_interview_jds_reject_empty_raw_text():
    ...
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_interview_jds.py -q
```

Expected: fail because `app.repositories.interview_jd_repository` or `/interview-jds` does not exist yet.

---

### Task 3: Backend JD Storage Implementation

**Files:**
- Modify: `app/db/models.py`
- Modify: `app/db/database.py`
- Create: `app/schemas/interview_jds.py`
- Create: `app/repositories/interview_jd_repository.py`
- Create: `app/api/routes/interview_jds.py`
- Modify: `app/main.py`

- [ ] **Step 1: Add table model constants**

Add `INTERVIEW_JDS_TABLE = "interview_jds"` and `InterviewJDRecord`.

- [ ] **Step 2: Add SQLite table**

Create `interview_jds` with raw JD text plus JSON columns for extracted sections.

- [ ] **Step 3: Add Pydantic schemas**

Create request and response models. Array fields default to empty lists.

- [ ] **Step 4: Add repository**

Serialize list fields as JSON with `ensure_ascii=False`; deserialize rows back into `InterviewJDRecord`.

- [ ] **Step 5: Add API route**

Expose:

```text
POST /interview-jds
GET /interview-jds?user_id=...
```

- [ ] **Step 6: Verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_interview_jds.py -q
```

Expected: all new JD tests pass.

---

### Task 4: Frontend JD Form Foundation

**Files:**
- Modify: `frontend/src/api/tutorApi.js`
- Create: `frontend/src/components/InterviewJDPanel.jsx`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/styles/app.css`

- [ ] **Step 1: Add API helpers**

Add `createInterviewJD(requestBody)` and `getInterviewJDs(userId, limit = 20)`.

- [ ] **Step 2: Add JD panel component**

The panel should include:

```text
title input
raw_text textarea
core_skills textarea
preferred_skills textarea
keywords textarea
interview_focus textarea
save button
saved JD list
```

Textarea values split by newline or comma into arrays before submit.

- [ ] **Step 3: Wire into App**

Load JD records for the current `user_id`, reset on user switch, and render the panel beside chat.

- [ ] **Step 4: Add styles**

Keep the panel compact and operational; use existing 8px radius and restrained colors.

- [ ] **Step 5: Verify frontend build**

Run:

```powershell
npm run build
```

from `frontend/`.

Expected: Vite build succeeds.

---

### Task 5: Seed First JD Through the Form/API

**Files:**
- No committed runtime database file.

- [ ] **Step 1: Start backend**

Run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

- [ ] **Step 2: Start frontend**

Run:

```powershell
npm run dev -- --host 127.0.0.1
```

from `frontend/`.

- [ ] **Step 3: Save the AI Agent JD**

Use the JD form to save the user-provided AI Agent / LLM application JD for `demo-user`.

- [ ] **Step 4: Confirm API list**

Open or request:

```text
GET http://127.0.0.1:8001/interview-jds?user_id=demo-user
```

Expected: response includes the saved AI Agent JD.

---

### Task 6: Final Verification

**Files:**
- All touched files.

- [ ] **Step 1: Run backend tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_interview_jds.py tests/test_stage2_api.py -q
```

- [ ] **Step 2: Run frontend build**

```powershell
npm run build
```

from `frontend/`.

- [ ] **Step 3: Check git status**

```powershell
git status --short
```

Expected: only intentional source, test, and docs changes.

---

## Self-Review

- Spec coverage: JD storage section maps to Tasks 2-5. Tool design is intentionally deferred.
- Placeholder scan: no `TBD` or unspecified implementation tasks.
- Type consistency: API uses `interview_jds`, schema names use `InterviewJD`, and frontend helpers use the same `/interview-jds` endpoint.
