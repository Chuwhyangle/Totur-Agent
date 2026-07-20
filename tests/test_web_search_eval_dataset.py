"""Web Search 路由评测集的静态质量门禁。"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path


DATASET_PATH = Path("tests/data/web_search_eval.jsonl")
EXPECTED_ROUTE_COUNTS = {
    "web": 10,
    "none": 10,
    "local": 10,
    "local_then_web": 10,
}


def _load_cases() -> list[dict]:
    return [
        json.loads(line)
        for line in DATASET_PATH.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def test_web_search_eval_dataset_has_balanced_route_coverage():
    cases = _load_cases()

    assert len(cases) == 40
    assert len({case["id"] for case in cases}) == 40
    assert Counter(case["expected_route"] for case in cases) == EXPECTED_ROUTE_COUNTS


def test_web_search_eval_dataset_marks_freshness_consistently():
    cases = _load_cases()

    for case in cases:
        assert case["question"].strip()
        assert case["notes"].strip()
        if case["expected_route"] in {"web", "local_then_web"}:
            assert case["requires_freshness"] is True
        else:
            assert case["requires_freshness"] is False
