# Agent Doc Hierarchical Chunking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deterministically convert `corpus/Agent_doc/**/*.html` into reviewable hierarchical semantic chunks, JSONL, and a stable Manifest without changing the production RAG path.

**Architecture:** A pure service parses Reveal.js lessons and the course map into typed semantic units, renders normalized structural text, and splits only units whose full embedding text exceeds the configured tokenizer threshold. A standalone CLI loads the Hugging Face tokenizer, validates/deduplicates inputs, then atomically writes deterministic JSONL and Manifest outputs.

**Tech Stack:** Python 3.14, BeautifulSoup (`html.parser`), Hugging Face Transformers fast tokenizer, pytest.

---

### Task 1: Parse hierarchical HTML into semantic units

**Files:**
- Create: `app/services/agent_doc_chunker.py`
- Create: `tests/test_agent_doc_chunker.py`
- Modify: `requirements.txt`

- [x] Add failing tests for ordered `content-slide` parsing, `h2/h3` inheritance, continuation slides, boundaries, decoration removal, and paragraph/list/table/code preservation.
- [x] Run `\.\.venv\Scripts\python.exe -m pytest tests\test_agent_doc_chunker.py -q` and confirm collection or assertion failure.
- [x] Add parser dataclasses, normalization helpers, Reveal.js parsing, knowledge-map parsing, QA/topic/article/trend classification, and overview-unit construction.
- [x] Re-run the focused tests until the parsing group passes.

### Task 2: Implement tokenizer-aware hierarchical splitting and records

**Files:**
- Modify: `app/services/agent_doc_chunker.py`
- Modify: `tests/test_agent_doc_chunker.py`

- [x] Add failing tests for the 1024-token hard threshold, 500-700 soft target, structure/sentence/clause/token-window priority, header budget, overlap restrictions, stable IDs, hashes, and child metadata.
- [x] Run the focused tests and confirm the new assertions fail.
- [x] Implement injected tokenizer protocol, embedding-header rendering, structure-aware splitting, fast-tokenizer offset fallback, child-record generation, and record validation.
- [x] Re-run the focused tests until the splitting and record groups pass.

### Task 3: Build deterministic JSONL and Manifest atomically

**Files:**
- Create: `scripts/build_agent_doc_chunks.py`
- Modify: `tests/test_agent_doc_chunker.py`

- [x] Add failing CLI tests for scanning, duplicate-content rejection, tokenizer-load failure, deterministic sorting/fingerprint, and preservation of old outputs on failure.
- [x] Run the focused tests and confirm the CLI assertions fail.
- [x] Implement CLI arguments, `EMBEDDING_MODEL` default lookup, Hugging Face tokenizer adapter and resolved revision metadata, source hashing, canonical serialization, Manifest fingerprinting, validation, reports, and two-file atomic replacement with rollback.
- [x] Re-run the focused tests until all CLI tests pass.

### Task 4: Verify against the real corpus

**Files:**
- Generate: `corpus/Agent_doc/processed/agent_doc_chunks.jsonl`
- Generate: `corpus/Agent_doc/processed/agent_doc_manifest.json`

- [x] Run `\.\.venv\Scripts\python.exe scripts\build_agent_doc_chunks.py`.
- [x] Confirm 11 unique HTML files, one course overview, ten lesson overviews, no empty chunks, POSIX relative sources, and all embedding counts at or below 1024.
- [x] Run the build a second time and confirm identical JSONL SHA-256 and Manifest fingerprint.
- [x] Run `\.\.venv\Scripts\python.exe -m pytest tests -q` and record the final result.
- [x] Re-read the design acceptance list and report any unmet item explicitly.

## Verification result

- Focused suite: `26 passed`.
- Real corpus: 11 HTML files, 431 chunks, maximum embedding length 1005 tokens, stable JSONL SHA-256 and Manifest fingerprint across consecutive builds.
- Full backend suite: `645 passed, 3 failed, 5 xfailed`; the three failures are pre-existing journal persona/tool registry expectation mismatches outside this plan's write scope.
