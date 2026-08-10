"""Load the public JD corpus into deterministic parent and child documents."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


DEFAULT_JD_DATASET_CSVS: dict[str, Path] = {
    "agent_dev": Path("corpus/JD/agent_dev/unified.csv"),
    "marketing": Path("corpus/JD/marketing/ncss_marketing_jobs_2026-08-04.csv"),
}

CHILD_TYPES = ("jd_text", "job_info")
AUTONOMOUS_REGION_PREFIXES = (
    ("内蒙古", "内蒙古自治区"),
    ("广西", "广西壮族自治区"),
    ("西藏", "西藏自治区"),
    ("宁夏", "宁夏回族自治区"),
    ("新疆", "新疆维吾尔自治区"),
)


FUNCTION_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("新媒体运营", ("新媒体", "小红书", "公众号", "自媒体", "账号运营", "抖音", "视频运营")),
    ("短视频/直播运营", ("短视频", "直播")),
    ("电商运营", ("电商", "跨境", "tiktok", "京东", "淘宝", "店铺", "独立站", "亚马逊")),
    ("内容/文案策划", ("内容", "文案", "编辑", "编导", "脚本", "撰稿")),
    ("市场营销/推广", ("市场", "营销", "推广", "获客", "销售", "业务")),
    ("品牌", ("品牌",)),
    ("活动策划", ("活动",)),
    ("商务/渠道/媒介", ("商务", "渠道", "媒介", "公关", "客户")),
    ("用户/社群/增长", ("用户运营", "社群", "增长", "拉新", "留存", "促活")),
    ("通用运营", ("运营",)),
)


@dataclass(frozen=True)
class JDChildDocument:
    """One vectorized child used to retrieve a complete parent JD."""

    child_id: str
    parent_id: str
    child_type: str
    content: str
    index_sha256: str
    metadata: dict[str, str | float]


@dataclass(frozen=True)
class JDParentDocument:
    """One complete JD plus its normalized structured metadata."""

    jd_id: str
    fingerprint: str
    category: str
    source_path: str
    source_url: str
    title: str
    company: str
    salary_raw: str
    salary_min_k: float
    salary_max_k: float
    education: str
    recruitment_count: str
    major: str
    region: str
    province: str
    source_updated_at: str
    industry: str
    company_type: str
    company_size: str
    relevance: str
    relevance_score: int
    function_category: str
    keywords: tuple[str, ...]
    duplicate_count: int
    row_sha256: str
    parent_sha256: str
    full_markdown: str
    children: tuple[JDChildDocument, JDChildDocument]


@dataclass(frozen=True)
class SkippedJDRow:
    """One JD corpus row skipped during tolerant loading (FR-7)."""

    source_path: str
    reason: str


def load_jd_dataset(
    root: Path,
    *,
    dataset_csvs: Mapping[str, Path] | None = None,
    strict: bool = False,
) -> tuple[tuple[JDParentDocument, ...], tuple[SkippedJDRow, ...]]:
    """Read every configured CSV row and its matching Markdown parent.

    FR-7：改为收集式。单行失败（缺文件、非 UTF-8、缺字段、薪资格式不支持、
    缺「职位原文」、jd_id 重复）不再中断整个构建，而是记录到 skipped。
    strict=True 时保留原严格行为（首错即抛）。
    返回 (parents, skipped)。
    """

    corpus_root = Path(root)
    configured = dataset_csvs or DEFAULT_JD_DATASET_CSVS
    parents: list[JDParentDocument] = []
    skipped: list[SkippedJDRow] = []
    seen_ids: set[str] = set()

    for category, configured_path in configured.items():
        csv_path = Path(configured_path)
        if not csv_path.is_absolute():
            csv_path = corpus_root / csv_path
        if not csv_path.is_file():
            raise ValueError(f"JD CSV not found: {csv_path}")
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            raise ValueError(f"JD CSV is empty: {csv_path}")
        for row in rows:
            filename = str(row.get("文件") or "").strip()
            if not filename:
                _record_skip(skipped, strict, "", "missing_filename", "JD field is required: 文件")
                continue
            markdown_path = csv_path.parent / "jobs" / filename
            if not markdown_path.is_file():
                _record_skip(
                    skipped,
                    strict,
                    filename,
                    "markdown_not_found",
                    f"JD Markdown not found: {markdown_path}",
                )
                continue
            raw = markdown_path.read_bytes()
            try:
                markdown = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                _record_skip(
                    skipped,
                    strict,
                    filename,
                    "not_utf8",
                    f"JD Markdown must be UTF-8: {markdown_path}",
                )
                continue
            source_path = markdown_path.relative_to(corpus_root).as_posix()
            try:
                parent = build_jd_parent(
                    category=category,
                    row=row,
                    source_path=source_path,
                    markdown=markdown,
                )
            except ValueError as exc:
                reason = str(exc)
                code = _reason_code(reason)
                _record_skip(skipped, strict, source_path, code, reason)
                continue
            if parent.jd_id in seen_ids:
                _record_skip(
                    skipped,
                    strict,
                    source_path,
                    "duplicate_jd_id",
                    f"duplicate JD id: {parent.jd_id}",
                )
                continue
            seen_ids.add(parent.jd_id)
            parents.append(parent)

    return tuple(sorted(parents, key=lambda item: item.jd_id)), tuple(skipped)


def _reason_code(reason: str) -> str:
    """Map one skip reason string to a stable short code for manifest tracing."""

    if "unsupported JD salary" in reason:
        return "unsupported_salary"
    if "Markdown section is required" in reason:
        return "missing_section"
    if "JD field is required" in reason:
        return "missing_field"
    return "build_failed"


def _record_skip(
    skipped: list[SkippedJDRow],
    strict: bool,
    source_path: str,
    code: str,
    reason: str,
) -> None:
    """Append a skip record; in strict mode raise instead."""

    if strict:
        raise ValueError(reason)
    skipped.append(SkippedJDRow(source_path=source_path, reason=f"{code}: {reason}"))


def build_jd_parent(
    *,
    category: str,
    row: Mapping[str, Any],
    source_path: str,
    markdown: str,
) -> JDParentDocument:
    """Build one parent and exactly two retrieval children."""

    fingerprint = _required(row, "JD指纹")
    title = _required(row, "职位")
    company = _required(row, "招聘主体")
    salary_raw = _required(row, "薪资")
    education = _required(row, "学历")
    region = _required(row, "地区")
    relevance = _required(row, "相关度")
    salary_min_k, salary_max_k = parse_salary(salary_raw)
    sections = _extract_h2_sections(markdown)
    jd_body = _required_section(sections, "职位原文")
    info_sections = [
        _format_mapping_section(
            "结构化字段",
            (
                ("职位", title),
                ("薪资", salary_raw),
                ("学历", education),
                ("招聘人数", row.get("招聘人数")),
                ("专业", row.get("专业")),
                ("地区", region),
                ("更新时间", row.get("更新时间")),
                ("相关度", relevance),
            ),
        ),
        _format_mapping_section(
            "公司信息",
            (
                ("招聘主体", company),
                ("所属行业", row.get("所属行业")),
                ("公司性质", row.get("公司性质")),
                ("公司规模", row.get("公司规模")),
            ),
        ),
    ]
    benefits = sections.get("福利标签", "").strip()
    if benefits:
        info_sections.append(_format_section("福利标签", benefits))

    parent_id = f"{category}:{fingerprint}"
    province = parse_province(region)
    common_metadata: dict[str, str | float] = {
        "parent_id": parent_id,
        "category": category,
        "source": source_path,
        "title": title,
        "relevance": relevance,
        "education": education,
        "province": province,
        "salary_min_k": salary_min_k,
        "salary_max_k": salary_max_k,
    }
    child_contents = {
        "jd_text": f"# {title}\n\n## 职位原文\n\n{_strip_fences(jd_body)}".strip(),
        "job_info": f"# {title}\n\n" + "\n\n".join(info_sections),
    }
    children = tuple(
        _build_child(
            parent_id=parent_id,
            child_type=child_type,
            content=child_contents[child_type],
            metadata=common_metadata,
        )
        for child_type in CHILD_TYPES
    )
    keywords = tuple(
        normalized
        for item in re.split(r"[,，、/|]+", str(row.get("技术关键词") or ""))
        if (normalized := item.strip())
    )
    return JDParentDocument(
        jd_id=parent_id,
        fingerprint=fingerprint,
        category=category,
        source_path=source_path,
        source_url=str(row.get("详情页") or "").strip(),
        title=title,
        company=company,
        salary_raw=salary_raw,
        salary_min_k=salary_min_k,
        salary_max_k=salary_max_k,
        education=education,
        recruitment_count=str(row.get("招聘人数") or "").strip(),
        major=str(row.get("专业") or "").strip(),
        region=region,
        province=province,
        source_updated_at=str(row.get("更新时间") or "").strip(),
        industry=str(row.get("所属行业") or "").strip(),
        company_type=str(row.get("公司性质") or "").strip(),
        company_size=str(row.get("公司规模") or "").strip(),
        relevance=relevance,
        relevance_score=_parse_int(row.get("相关度分值")),
        function_category=classify_function(category, title),
        keywords=keywords,
        duplicate_count=max(1, _parse_int(row.get("同模板条数"))),
        row_sha256=_sha256_json(dict(row)),
        parent_sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        full_markdown=markdown,
        children=children,  # type: ignore[arg-type]
    )


def parse_salary(value: str) -> tuple[float, float]:
    """Parse the corpus' normalized monthly salary range in k/month."""

    match = re.fullmatch(
        r"\s*([\d.]+)\s*k\s*[-–~至]\s*([\d.]+)\s*k\s*",
        str(value),
        re.IGNORECASE,
    )
    if match is None:
        raise ValueError(f"unsupported JD salary: {value!r}")
    low, high = float(match.group(1)), float(match.group(2))
    return (min(low, high), max(low, high))


def parse_province(value: str) -> str:
    """Normalize a detailed work location to a province or municipality."""

    location = str(value).strip()
    if "全国" in location:
        return "全国"
    head = location.split("、", 1)[0].strip()
    for city in ("北京市", "上海市", "天津市", "重庆市"):
        if head.startswith(city):
            return city[:-1]
    for prefix, province in AUTONOMOUS_REGION_PREFIXES:
        if head.startswith(prefix):
            return province
    match = re.match(r"(.+?省)", head)
    return match.group(1) if match else (head[:3] if head else "未知")


def classify_function(category: str, title: str) -> str:
    """Map one title to the stable first-version function taxonomy."""

    if category == "agent_dev":
        return "Agent/AI 开发"
    normalized = title.lower()
    for name, terms in FUNCTION_RULES:
        if any(term.lower() in normalized for term in terms):
            return name
    return "其他"


def _build_child(
    *,
    parent_id: str,
    child_type: str,
    content: str,
    metadata: Mapping[str, str | float],
) -> JDChildDocument:
    child_metadata = dict(metadata)
    child_metadata["child_type"] = child_type
    return JDChildDocument(
        child_id=f"{parent_id}:{child_type}",
        parent_id=parent_id,
        child_type=child_type,
        content=content,
        index_sha256=_sha256_json(
            {"content": content, "metadata": child_metadata}
        ),
        metadata=child_metadata,
    )


def _extract_h2_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in markdown.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            current = match.group(1)
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def _required_section(sections: Mapping[str, str], name: str) -> str:
    value = sections.get(name, "").strip()
    if not value:
        raise ValueError(f"JD Markdown section is required: {name}")
    return value


def _strip_fences(value: str) -> str:
    return "\n".join(
        line for line in value.splitlines() if not re.match(r"^\s*```", line)
    ).strip()


def _format_section(name: str, value: str) -> str:
    return f"## {name}\n\n{value.strip()}"


def _format_mapping_section(
    name: str,
    fields: tuple[tuple[str, Any], ...],
) -> str:
    lines = [
        f"## {name}",
        "",
        "| 字段 | 值 |",
        "|---|---|",
    ]
    for label, value in fields:
        normalized = _format_table_cell(value)
        if normalized:
            lines.append(f"| {_format_table_cell(label)} | {normalized} |")
    return "\n".join(lines)


def _format_table_cell(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).replace("|", r"\|")


def _required(row: Mapping[str, Any], key: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise ValueError(f"JD field is required: {key}")
    return value


def _parse_int(value: Any) -> int:
    match = re.search(r"-?\d+", str(value or ""))
    return int(match.group()) if match else 0


def _sha256_json(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
