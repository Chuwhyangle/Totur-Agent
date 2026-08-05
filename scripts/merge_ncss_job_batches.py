r"""合并 NCSS Agent 岗位的多批抓取结果为一个统一数据集。

按 JD 正文指纹（CSV 的 JD指纹 列）去重；同一指纹出现在多批时，按批次优先级
取代表：宽松版（最新最全）> 严格新版 > 严格旧版。输出 unified.csv、
jobs/*.md 和 README.md 到统一目录。

用法：
    .\.venv\Scripts\python.exe scripts\merge_ncss_job_batches.py
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
BJ_TZ = timezone(timedelta(hours=8))

# 批次目录 -> (优先级, 来源标注)，优先级数字越小越优先
BATCHES: list[tuple[str, int, str]] = [
    ("ncss_agent_jobs_loose_2026-08-04", 0, "宽松版 2026-08-04"),
    ("ncss_agent_jobs_2026-08-04", 1, "严格版 2026-08-04"),
    ("ncss_agent_jobs_2026-07-31", 2, "严格版 2026-07-31"),
]

REPLACE_CHARS = re.compile(r"[\\/:*?\"<>|\r\n\t]")


def safe_filename(text: str, limit: int = 48) -> str:
    cleaned = REPLACE_CHARS.sub("", text).strip().replace(" ", "")
    cleaned = cleaned.strip(".")
    return cleaned[:limit] or "job"


def main() -> int:
    exports = ROOT / "exports"
    found: dict[str, dict] = {}  # 指纹 -> 记录(含 source, file_path, 序号)
    by_source: Counter = Counter()

    for dirname, priority, label in BATCHES:
        batch_dir = exports / dirname
        csv_path = next(batch_dir.glob("*.csv"), None)
        if csv_path is None:
            print(f"[warn] 未找到 {dirname}/ 下的 CSV，跳过")
            continue
        with csv_path.open(encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            fingerprint = r.get("JD指纹", "")
            if not fingerprint:
                continue
            existing = found.get(fingerprint)
            if existing is not None and existing["priority"] <= priority:
                continue
            found[fingerprint] = {
                **r,
                "source": label,
                "priority": priority,
                "batch_dir": batch_dir,
                "file_name": r.get("文件", ""),
            }
            by_source[label] += 1

    print(f"合并去重后总数：{len(found)} 份\n")
    print("来源分布：")
    for label, cnt in by_source.most_common():
        print(f"  - {label}: {cnt}")

    today = f"{datetime.now(BJ_TZ):%Y-%m-%d}"
    out_dir = exports / f"ncss_agent_unified_{today}"
    jobs_dir = out_dir / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    records = sorted(found.values(), key=lambda rec: int(rec.get("序号", 0)))
    unified_rows: list[dict] = []
    copied = 0
    missing = 0
    for i, rec in enumerate(records, 1):
        new_name = f"{i:02d}-{safe_filename(rec['职位'], 30)}-{safe_filename(rec['招聘主体'], 26)}.md"
        src = Path(rec["batch_dir"]) / "jobs" / rec["file_name"]
        dst = jobs_dir / new_name
        if src.exists():
            dst.write_bytes(src.read_bytes())
            copied += 1
        else:
            missing += 1
        row = dict(rec)
        row["序号"] = str(i)
        row["文件"] = new_name
        row["来源批次"] = rec["source"]
        row.pop("priority", None)
        row.pop("source", None)
        unified_rows.append(row)

    csv_path = out_dir / "unified.csv"
    fieldnames = [
        "序号", "文件", "来源批次", "相关度", "相关度分值", "职位", "招聘主体", "薪资", "学历",
        "招聘人数", "专业", "地区", "更新时间", "所属行业", "公司性质", "公司规模",
        "技术关键词", "同模板条数", "JD指纹", "详情页",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in unified_rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    rel_count: Counter = Counter()
    for rec in records:
        rel_count[rec["相关度"]] += 1
    src_count: Counter = Counter(rec["source"] for rec in records)

    lines = [
        "# 国家大学生就业服务平台：Agent 开发相关职位（统一数据集）",
        "",
        f"- 合并日期：{today}",
        f"- 总份数：{len(records)}（按 JD 正文指纹去重）",
        f"- md 文件复制：成功 {copied}，缺失 {missing}",
        "",
        "## 来源分布",
        "",
        "| 来源 | 份数 |",
        "|---|---:|",
    ]
    for label, cnt in src_count.most_common():
        lines.append(f"| {label} | {cnt} |")
    lines += [
        "",
        "## 相关度分布",
        "",
        "| 相关度 | 份数 |",
        "|---|---:|",
    ]
    for name in ["直接相关", "较相关", "相邻岗位"]:
        if rel_count.get(name):
            lines.append(f"| {name} | {rel_count[name]} |")
    lines += [
        "",
        "## 合并口径",
        "",
        "1. 以 JD 正文指纹（去掉空白和标点后的 SHA1 前 12 位）去重；",
        "2. 同一指纹出现在多批时，取批次优先级：宽松版 08-04 > 严格版 08-04 > 严格版 07-31；",
        "3. 每份 JD 一个 md 文件，正文为详情页原文，未做改写；",
        "4. 旧批次独有、新批次未再搜到的 JD（可能已下架）保留并标注来源批次。",
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    print(f"\n完成：{out_dir}")
    print(f"  - unified.csv（{len(unified_rows)} 行，含来源批次）")
    print(f"  - jobs/ 共 {copied} 个 md（缺失 {missing}）")
    print(f"  - README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
