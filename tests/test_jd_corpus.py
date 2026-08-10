from pathlib import Path

from app.services.jd_corpus import (
    build_jd_parent,
    load_jd_dataset,
    parse_province,
    parse_salary,
)


def _row(**overrides):
    row = {
        "文件": "01-Agent工程师-示例公司.md",
        "相关度": "直接相关",
        "相关度分值": "67",
        "职位": "Agent工程师",
        "招聘主体": "示例公司",
        "薪资": "16k-20k",
        "学历": "本科及以上",
        "招聘人数": "2人",
        "专业": "计算机相关",
        "地区": "湖北省武汉市",
        "更新时间": "08-05 10:00",
        "所属行业": "软件和信息技术服务业",
        "公司性质": "民营企业",
        "公司规模": "100-499人",
        "技术关键词": "Python、Agent、RAG",
        "同模板条数": "1",
        "JD指纹": "abc123def456",
        "详情页": "https://example.com/jobs/1",
    }
    row.update(overrides)
    return row


def _markdown(analysis_text: str = "这段分析不能参与向量化") -> str:
    return f"""# Agent工程师

> 来源：https://example.com/jobs/1

## 职位原文

```text
负责 Agent、RAG 和 Python 服务开发。
要求熟悉 FastAPI。
```

## 结构化字段

| 字段 | 值 |
|---|---|
| 职位名称 | Agent工程师 |
| 学历要求 | 本科及以上 |

## 公司信息

| 字段 | 值 |
|---|---|
| 招聘主体 | 示例公司 |

## 福利标签

五险一金、弹性工作

## 技术关键词

Python、Agent、RAG

## 与 Tutor Agent 项目的对应点

{analysis_text}

## 同模板的其他投放

- 示例分公司
"""


def test_build_jd_parent_creates_two_search_children_without_analysis():
    parent = build_jd_parent(
        category="agent_dev",
        row=_row(),
        source_path="corpus/JD/agent_dev/jobs/01-Agent工程师-示例公司.md",
        markdown=_markdown(),
    )

    assert parent.jd_id == "agent_dev:abc123def456"
    assert parent.fingerprint == "abc123def456"
    assert parent.title == "Agent工程师"
    assert parent.salary_min_k == 16.0
    assert parent.salary_max_k == 20.0
    assert parent.province == "湖北省"
    assert parent.keywords == ("Python", "Agent", "RAG")
    assert [child.child_type for child in parent.children] == [
        "jd_text",
        "job_info",
    ]
    assert [child.child_id for child in parent.children] == [
        "agent_dev:abc123def456:jd_text",
        "agent_dev:abc123def456:job_info",
    ]

    jd_text, job_info = parent.children
    assert "负责 Agent、RAG 和 Python 服务开发" in jd_text.content
    assert "结构化字段" not in jd_text.content
    assert "```" not in jd_text.content
    assert "结构化字段" in job_info.content
    assert "公司信息" in job_info.content
    assert "福利标签" in job_info.content
    assert "招聘人数" in job_info.content
    assert "计算机相关" in job_info.content
    assert "软件和信息技术服务业" in job_info.content
    for child in parent.children:
        assert "技术关键词" not in child.content
        assert "Tutor Agent" not in child.content
        assert "同模板的其他投放" not in child.content
        assert child.index_sha256


def test_analysis_only_change_keeps_child_hashes_but_changes_parent_hash():
    first = build_jd_parent(
        category="agent_dev",
        row=_row(),
        source_path="corpus/JD/agent_dev/jobs/01-Agent工程师-示例公司.md",
        markdown=_markdown("旧分析"),
    )
    second = build_jd_parent(
        category="agent_dev",
        row=_row(),
        source_path="corpus/JD/agent_dev/jobs/01-Agent工程师-示例公司.md",
        markdown=_markdown("新分析"),
    )

    assert first.parent_sha256 != second.parent_sha256
    assert [child.index_sha256 for child in first.children] == [
        child.index_sha256 for child in second.children
    ]


def test_job_info_uses_csv_as_structured_source_and_keeps_markdown_benefits():
    parent = build_jd_parent(
        category="agent_dev",
        row=_row(
            招聘主体="CSV权威公司",
            招聘人数="5人",
            专业="人工智能",
            所属行业="互联网",
            公司性质="国有企业",
            公司规模="1000人以上",
        ),
        source_path="corpus/JD/agent_dev/jobs/example.md",
        markdown=_markdown(),
    )

    job_info = parent.children[1].content
    assert "CSV权威公司" in job_info
    assert "5人" in job_info
    assert "人工智能" in job_info
    assert "互联网" in job_info
    assert "国有企业" in job_info
    assert "1000人以上" in job_info
    assert "五险一金、弹性工作" in job_info
    assert "示例公司" not in job_info


def test_csv_job_info_change_only_changes_job_info_child_hash():
    first = build_jd_parent(
        category="agent_dev",
        row=_row(公司规模="100-499人"),
        source_path="corpus/JD/agent_dev/jobs/example.md",
        markdown=_markdown(),
    )
    second = build_jd_parent(
        category="agent_dev",
        row=_row(公司规模="1000人以上"),
        source_path="corpus/JD/agent_dev/jobs/example.md",
        markdown=_markdown(),
    )

    assert first.children[0].index_sha256 == second.children[0].index_sha256
    assert first.children[1].index_sha256 != second.children[1].index_sha256


def test_load_jd_dataset_reads_csv_and_matching_parent_file(tmp_path):
    jobs = tmp_path / "corpus" / "JD" / "agent_dev" / "jobs"
    jobs.mkdir(parents=True)
    (jobs / _row()["文件"]).write_text(_markdown(), encoding="utf-8")
    csv_path = jobs.parent / "unified.csv"
    headers = list(_row())
    values = [_row()[header] for header in headers]
    csv_path.write_text(
        ",".join(headers) + "\n" + ",".join(values) + "\n",
        encoding="utf-8-sig",
    )

    parents, skipped = load_jd_dataset(
        tmp_path,
        dataset_csvs={"agent_dev": csv_path.relative_to(tmp_path)},
    )

    assert len(parents) == 1
    assert skipped == ()
    assert parents[0].source_path.endswith(_row()["文件"])


def test_salary_and_province_normalization():
    assert parse_salary("0.1k-21k") == (0.1, 21.0)
    assert parse_province("北京市朝阳区") == "北京"
    assert parse_province("全国") == "全国"

    assert parse_province("广西南宁市") == "广西壮族自治区"
    assert parse_province("新疆石河子市") == "新疆维吾尔自治区"
    assert parse_province("内蒙古呼和浩特市") == "内蒙古自治区"


def test_load_jd_dataset_skips_bad_rows_collectively(tmp_path):
    """FR-7: 收集式跳过坏行，不中断整个构建。"""

    jobs = tmp_path / "corpus" / "JD" / "agent_dev" / "jobs"
    jobs.mkdir(parents=True)

    # 好行
    (jobs / _row()["文件"]).write_text(_markdown(), encoding="utf-8")
    # 坏行1：Markdown 缺失
    bad_missing = _row(
        文件="02-缺失文件.md",
        JD指纹="abc123def457",
    )
    # 坏行2：薪资格式不支持（面议）
    bad_salary = _row(
        文件="03-面议薪资.md",
        薪资="面议",
        JD指纹="abc123def458",
    )
    # 坏行3：缺「职位原文」章节
    bad_section = _row(
        文件="04-缺章节.md",
        JD指纹="abc123def459",
    )
    bad_section_md = "# Agent工程师\n\n## 其他\n\n没有职位原文\n"

    rows = [bad_missing, bad_salary, bad_section, _row()]
    headers = list(_row())
    csv_path = jobs.parent / "unified.csv"
    csv_path.write_text(
        ",".join(headers) + "\n"
        + "\n".join(",".join(row[h] for h in headers) for row in rows)
        + "\n",
        encoding="utf-8-sig",
    )
    # 缺文件的行无需写 md；缺章节的行写 md
    (jobs / "04-缺章节.md").write_text(bad_section_md, encoding="utf-8")
    # 面议薪资的行需要有效 md（有职位原文），才会走到薪资解析阶段
    (jobs / "03-面议薪资.md").write_text(_markdown(), encoding="utf-8")

    parents, skipped = load_jd_dataset(
        tmp_path,
        dataset_csvs={"agent_dev": csv_path.relative_to(tmp_path)},
    )

    assert len(parents) == 1
    assert len(skipped) == 3
    reasons = {item.reason.split(":")[0] for item in skipped}
    assert "markdown_not_found" in reasons
    assert "unsupported_salary" in reasons
    assert "missing_section" in reasons


def test_load_jd_dataset_strict_mode_raises_on_first_bad_row(tmp_path):
    """FR-7: strict=True 保留首错即抛的严格行为。"""

    jobs = tmp_path / "corpus" / "JD" / "agent_dev" / "jobs"
    jobs.mkdir(parents=True)
    bad_salary = _row(文件="03-面议薪资.md", 薪资="面议", JD指纹="abc123def458")
    (jobs / "03-面议薪资.md").write_text(_markdown(), encoding="utf-8")
    rows = [bad_salary]
    headers = list(_row())
    csv_path = jobs.parent / "unified.csv"
    csv_path.write_text(
        ",".join(headers) + "\n" + ",".join(bad_salary[h] for h in headers) + "\n",
        encoding="utf-8-sig",
    )

    try:
        load_jd_dataset(
            tmp_path,
            dataset_csvs={"agent_dev": csv_path.relative_to(tmp_path)},
            strict=True,
        )
        assert False, "strict 模式应抛错"
    except ValueError as exc:
        assert "unsupported JD salary" in str(exc)


def test_build_jd_index_survives_skipped_rows(tmp_path, monkeypatch):
    """FR-7: skipped 行不影响 build_jd_index 正常构建。"""

    from app.services.jd_index_builder import build_jd_index

    jobs = tmp_path / "corpus" / "JD" / "agent_dev" / "jobs"
    jobs.mkdir(parents=True)
    (jobs / _row()["文件"]).write_text(_markdown(), encoding="utf-8")
    csv_path = jobs.parent / "unified.csv"
    headers = list(_row())
    values = [_row()[header] for header in headers]
    csv_path.write_text(
        ",".join(headers) + "\n" + ",".join(values) + "\n",
        encoding="utf-8-sig",
    )

    parents, skipped = load_jd_dataset(
        tmp_path,
        dataset_csvs={"agent_dev": csv_path.relative_to(tmp_path)},
    )
    assert len(parents) == 1
    assert skipped == ()

    class FakeStore:
        def count(self):
            return 2

        def rebuild(self, children, embeddings):
            return 2

        def upsert(self, children, embeddings):
            return 0

        def delete(self, ids):
            return 0

    class FakeEmbedding:
        def embed_texts(self, texts):
            return [[0.1] * 8 for _ in texts]

    result = build_jd_index(
        parents=parents,
        repository=FakeStore(),
        embedding_client=FakeEmbedding(),
        embedding_model="fake-model",
        manifest_path=tmp_path / "manifest.json",
        sync_sqlite=lambda *a, **k: 1,
        count_sqlite=lambda: 1,
        full=True,
        dry_run=False,
    )
    assert result.parent_count == 1
    assert result.child_count == 2
