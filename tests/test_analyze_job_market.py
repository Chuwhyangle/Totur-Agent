from app.db.models import PublicJDRecord
from app.services.agent.tools import analyze_job_market as tool_module


class FakeRepository:
    collection_name = "job_descriptions"

    def count(self):
        return 6


def _record(
    jd_id,
    fingerprint,
    category,
    *,
    education="本科及以上",
    salary=(10.0, 20.0),
    province="湖北省",
    function_category="Agent/AI 开发",
    keywords=("Python", "Agent"),
):
    return PublicJDRecord(
        jd_id=jd_id,
        fingerprint=fingerprint,
        category=category,
        source_path=f"corpus/JD/{category}/jobs/{jd_id}.md",
        source_url="https://example.com/jobs/1",
        title="示例职位",
        company="示例公司",
        salary_raw=f"{salary[0]:g}k-{salary[1]:g}k",
        salary_min_k=salary[0],
        salary_max_k=salary[1],
        education=education,
        recruitment_count="1人",
        major="不限",
        region="湖北省武汉市",
        province=province,
        source_updated_at="08-05",
        industry="软件",
        company_type="民营企业",
        company_size="100-499人",
        relevance="直接相关",
        relevance_score=60,
        function_category=function_category,
        keywords=keywords,
        duplicate_count=1,
        row_sha256="a" * 64,
        parent_sha256="b" * 64,
    )


def _records():
    return [
        _record("agent_dev:same", "same", "agent_dev"),
        _record(
            "marketing:same",
            "same",
            "marketing",
            function_category="内容/文案策划",
            keywords=(),
        ),
        _record(
            "marketing:unique",
            "unique",
            "marketing",
            education="专科及以上",
            salary=(6.0, 10.0),
            province="上海",
            function_category="新媒体运营",
            keywords=(),
        ),
    ]


def test_education_metric_deduplicates_by_fingerprint(monkeypatch):
    monkeypatch.setattr(tool_module, "_ensure_ready", lambda: None)
    monkeypatch.setattr(tool_module, "list_public_jds", lambda **kwargs: _records())

    result = tool_module.analyze_job_market("education")

    assert result["ok"] is True
    assert result["sample_count"] == 2
    assert result["record_count"] == 3
    assert result["items"] == [
        {"label": "专科及以上", "count": 1, "percentage": 50.0},
        {"label": "本科及以上", "count": 1, "percentage": 50.0},
    ]


def test_salary_metric_returns_buckets_and_medians(monkeypatch):
    monkeypatch.setattr(tool_module, "_ensure_ready", lambda: None)
    monkeypatch.setattr(tool_module, "list_public_jds", lambda **kwargs: _records())

    result = tool_module.analyze_job_market("salary")

    assert result["sample_count"] == 2
    assert result["statistics"] == {
        "median_min_k": 8.0,
        "median_max_k": 15.0,
        "median_mid_k": 11.5,
    }
    assert sum(item["count"] for item in result["items"]) == 2


def test_marketing_skills_returns_no_structured_data(monkeypatch):
    marketing = [record for record in _records() if record.category == "marketing"]
    monkeypatch.setattr(tool_module, "_ensure_ready", lambda: None)
    monkeypatch.setattr(
        tool_module,
        "list_public_jds",
        lambda **kwargs: marketing,
    )

    result = tool_module.analyze_job_market("skills", direction="marketing")

    assert result["ok"] is True
    assert result["found"] is False
    assert result["sample_count"] == 2
    assert result["items"] == []


def test_analysis_reports_not_ready(monkeypatch):
    def fail():
        raise tool_module.JDIndexNotReadyError("missing manifest")

    monkeypatch.setattr(tool_module, "_ensure_ready", fail)

    result = tool_module.analyze_job_market("region")

    assert result["ok"] is False
    assert result["error"] == "jd_index_not_ready"
