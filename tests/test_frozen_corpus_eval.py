"""FR5.6 frozen-corpus and isolated-evaluation tests."""
from pathlib import Path

from app.services.retrieval_eval import load_eval_cases

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FROZEN_ROOT = PROJECT_ROOT / "tests" / "data" / "corpus"
EVAL_FILE = PROJECT_ROOT / "tests" / "data" / "retrieval_eval.jsonl"
APPROVED_MARKDOWN_FILES = {
    "docs/agent-architecture.md",
    "docs/ai-collaboration-guide.md",
    "docs/api-design.md",
    "docs/data-design.md",
    "docs/frontend-quest-progress.md",
    "docs/main-quest-progress.md",
    "docs/memory-and-multi-turn-plan.md",
    "docs/requirements.md",
    "docs/superpowers/plans/2026-07-05-interview-jd-search-tool.md",
    "docs/superpowers/plans/2026-07-05-interview-jd-storage-foundation.md",
    "docs/superpowers/plans/2026-07-05-score-jd-skill-fit.md",
    "docs/superpowers/specs/2026-06-30-tutor-agent-api-design.md",
    "docs/superpowers/specs/2026-07-04-technical-interview-tool-calling-design.md",
    "docs/superpowers/specs/2026-07-05-score-jd-skill-fit-design.md",
    "docs/superpowers/specs/2026-07-13-v0.5-frozen-corpus-index-manifest-design.md",
    "docs/tools/chat-interview-jd-tool-calling.md",
    "docs/tools/interview-jd-search-tool-spec.md",
    "docs/tools/score-jd-skill-fit-tool-spec.md",
    "docs/training-plan.md",
    "docs/v0.2-retrospective.md",
    "docs/v0.2_Task_list.md",
    "docs/v0.3 RAG设计文档.md",
    "docs/v0.3-0.5 RAG.md",
    "docs/v0.3-rag-progress.md",
    "docs/v0.4-rag-progress.md",
}


def test_frozen_corpus_matches_approved_inventory_and_eval_sources():
    markdown_files = sorted((FROZEN_ROOT / "docs").rglob("*.md"))
    frozen_sources = {
        path.relative_to(FROZEN_ROOT).as_posix() for path in markdown_files
    }
    expected_sources = {
        source
        for case in load_eval_cases(EVAL_FILE)
        for source in case.expected_sources
    }
    assert frozen_sources == APPROVED_MARKDOWN_FILES
    assert expected_sources <= frozen_sources
