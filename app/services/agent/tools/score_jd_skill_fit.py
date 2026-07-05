"""Calculate deterministic JD skill-fit scores from LLM judgments."""

from __future__ import annotations

from typing import Any


VALID_CONFIDENCE = {"low", "medium", "high"}


def score_jd_skill_fit(
    skills: list[dict[str, Any]],
    target_role: str | None = None,
) -> dict[str, Any]:
    """Score JD fit from per-skill judgments prepared by the model."""

    if not isinstance(skills, list) or not skills:
        return _invalid("skills must be a non-empty list.")

    skill_scores: list[dict[str, Any]] = []
    for skill in skills:
        if not isinstance(skill, dict):
            return _invalid("each skill must include a non-empty name.")

        name = str(skill.get("name") or "").strip()
        if not name:
            return _invalid("each skill must include a non-empty name.")

        jd_importance = _clamp_int(skill.get("jd_importance"), minimum=1, maximum=5)
        user_level = _clamp_int(skill.get("user_level"), minimum=0, maximum=5)
        confidence = _normalize_confidence(skill.get("confidence"))
        weighted_score = jd_importance * user_level
        weighted_max = jd_importance * 5
        gap = 5 - user_level
        weighted_gap = jd_importance * gap

        skill_scores.append(
            {
                "name": name,
                "jd_importance": jd_importance,
                "user_level": user_level,
                "confidence": confidence,
                "weighted_score": weighted_score,
                "weighted_max": weighted_max,
                "gap": gap,
                "weighted_gap": weighted_gap,
                "evidence": str(skill.get("evidence") or ""),
                "reason": str(skill.get("reason") or ""),
                "recommended_action": str(skill.get("recommended_action") or ""),
            }
        )

    fit_score = _fit_score(skill_scores)
    high_importance_gaps = [
        skill
        for skill in skill_scores
        if skill["jd_importance"] >= 4 and skill["user_level"] <= 2
    ]
    uncertain_skills = [
        skill["name"]
        for skill in skill_scores
        if skill["confidence"] in {"low", "medium"}
    ]

    return {
        "ok": True,
        "target_role": str(target_role or ""),
        "fit_score": fit_score,
        "fit_level": _fit_level(fit_score),
        "max_score": 100,
        "skill_scores": skill_scores,
        "top_strengths": _top_strengths(skill_scores),
        "top_gaps": _top_gaps(high_importance_gaps),
        "uncertain_skills": uncertain_skills,
        "summary": {
            "skill_count": len(skill_scores),
            "high_importance_gap_count": len(high_importance_gaps),
            "uncertain_skill_count": len(uncertain_skills),
        },
    }


def _invalid(message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "invalid_arguments",
        "message": message,
    }


def _clamp_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = minimum

    return max(minimum, min(maximum, parsed))


def _normalize_confidence(value: Any) -> str:
    confidence = str(value or "medium").strip().lower()
    if confidence not in VALID_CONFIDENCE:
        return "medium"

    return confidence


def _fit_score(skill_scores: list[dict[str, Any]]) -> int:
    weighted_score = sum(skill["weighted_score"] for skill in skill_scores)
    weighted_max = sum(skill["weighted_max"] for skill in skill_scores)
    if weighted_max <= 0:
        return 0

    return round(weighted_score / weighted_max * 100)


def _fit_level(fit_score: int) -> str:
    if fit_score >= 85:
        return "strong_fit"
    if fit_score >= 70:
        return "good_fit"
    if fit_score >= 40:
        return "partial_fit"

    return "low_fit"


def _top_strengths(skill_scores: list[dict[str, Any]]) -> list[str]:
    strengths = [skill for skill in skill_scores if skill["user_level"] >= 4]
    strengths.sort(
        key=lambda skill: (skill["user_level"], skill["jd_importance"]),
        reverse=True,
    )

    return [skill["name"] for skill in strengths[:3]]


def _top_gaps(high_importance_gaps: list[dict[str, Any]]) -> list[str]:
    high_importance_gaps.sort(
        key=lambda skill: (skill["weighted_gap"], skill["jd_importance"]),
        reverse=True,
    )

    return [skill["name"] for skill in high_importance_gaps[:3]]
