r"""汇总国家大学生就业服务平台营销方向职位分布统计。

读取 exports/ncss_marketing_jobs_*/ 下的去重 CSV，按职能线 / 省份地区 / 薪资区间
聚合统计，输出 SUMMARY.md 报告。

用法：
    .\.venv\Scripts\python.exe scripts\analyze_ncss_marketing.py
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
BJ_TZ = timezone(timedelta(hours=8))

# ---- 职能线分类：按职位名从特化到泛化顺序匹配 ----------------------------
FUNCTION_RULES: list[tuple[str, list[str]]] = [
    ("新媒体运营", ["新媒体", "小红书", "公众号", "自媒体", "账号运营", "抖音", "视频运营", "短视频运营", "新媒体营销"]),
    ("短视频/直播运营", ["短视频", "直播"]),
    ("电商运营", ["电商", "跨境", "tiktok", "tik tok", "京东", "淘宝", "闲鱼", "店铺", "独立站", "速卖通", "亚马逊", "shopee", "阿里巴巴国际站"]),
    ("内容/文案策划", ["内容", "文案", "编辑", "编导", "脚本", "写手", "撰稿"]),
    ("市场营销/推广", ["市场", "营销", "推广", "获客", "销售", "业务"]),
    ("品牌", ["品牌"]),
    ("活动策划", ["活动"]),
    ("商务/渠道/媒介", ["商务", "渠道", "媒介", "公关", "客户", "达播", "联盟"]),
    ("用户/社群/增长", ["用户运营", "社群", "增长", "拉新", "留存", "促活"]),
    ("通用运营", ["运营"]),
    ("其他", []),
]


def classify_function(title: str) -> str:
    t = title.lower()
    for name, terms in FUNCTION_RULES:
        if any(term in t for term in terms):
            return name
    return "其他"


def parse_salary(salary: str) -> tuple[float, float] | None:
    """'6k-11k' / '0.1k-21k' -> (6.0, 11.0)（单位：千元/月）。"""
    m = re.fullmatch(r"\s*([\d.]+)\s*k\s*[-–~至]?\s*([\d.]+)\s*k\s*", salary, re.I)
    if not m:
        return None
    low, high = float(m.group(1)), float(m.group(2))
    return (min(low, high), max(low, high))


def parse_province(locations: str) -> str:
    """'安徽省合肥市瑶海区' -> '安徽省'；'全国' -> '全国'；直辖市 -> 市名。"""
    if "全国" in locations:
        return "全国"
    head = locations.split("、")[0].strip()
    for city in ("北京市", "上海市", "天津市", "重庆市"):
        if head.startswith(city):
            return city[:-1]
    m = re.match(r"(.+?省)", head)
    return m.group(1) if m else (head[:3] if head else "未知")


SALARY_BUCKETS = [
    ("5k 以下", lambda v: v < 5),
    ("5k-8k", lambda v: 5 <= v < 8),
    ("8k-12k", lambda v: 8 <= v < 12),
    ("12k-20k", lambda v: 12 <= v < 20),
    ("20k 以上", lambda v: v >= 20),
]


def bucket_salary(mid: float) -> str:
    for name, pred in SALARY_BUCKETS:
        if pred(mid):
            return name
    return "未知"


def main() -> int:
    out_dirs = sorted(ROOT.glob("exports/ncss_marketing_jobs_*"))
    if not out_dirs:
        print("未找到 exports/ncss_marketing_jobs_* 目录")
        return 1
    out_dir = out_dirs[-1]
    csv_path = next(out_dir.glob("ncss_marketing_jobs_*.csv"))

    rows: list[dict] = []
    with csv_path.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            rows.append(r)
    if not rows:
        print("CSV 为空")
        return 1

    func_count: Counter = Counter()
    func_salary: dict[str, list[float]] = defaultdict(list)
    prov_count: Counter = Counter()
    bucket_count: Counter = Counter()
    degree_count: Counter = Counter()
    city_count: Counter = Counter()
    salary_pairs: list[tuple[float, float]] = []

    for r in rows:
        title = r["职位"]
        func = classify_function(title)
        func_count[func] += 1

        loc = r["地区"] or ""
        prov_count[parse_province(loc)] += 1
        city = loc.split("、")[0].strip()
        if city and city != "全国":
            city_count[city] += 1

        degree_count[r["学历"] or "未知"] += 1

        pair = parse_salary(r["薪资"] or "")
        if pair:
            func_salary[func].append((pair[0] + pair[1]) / 2)
            bucket_count[bucket_salary((pair[0] + pair[1]) / 2)] += 1
            salary_pairs.append(pair)

    total = len(rows)
    parsed_salary = len(salary_pairs)

    lines: list[str] = []
    lines.append("# 运营 / 市场营销岗位分布统计")
    lines.append("")
    lines.append(f"- 数据源：{csv_path.name}（去重后 {total} 份 JD）")
    lines.append(f"- 统计时间：{datetime.now(BJ_TZ):%Y-%m-%d %H:%M}（北京时间）")
    lines.append("")
    lines.append("## 一、职能线分布")
    lines.append("")
    lines.append("| 职能线 | 岗位数 | 占比 | 薪资中位数（k/月） |")
    lines.append("|---|---:|---:|---:|")
    for name, cnt in func_count.most_common():
        mids = func_salary.get(name, [])
        mid = f"{sorted(mids)[len(mids) // 2]:.1f}" if mids else "—"
        lines.append(f"| {name} | {cnt} | {cnt / total * 100:.0f}% | {mid} |")
    lines.append("")

    lines.append("## 二、地区分布（按省份/直辖市）")
    lines.append("")
    lines.append("| 地区 | 岗位数 | 占比 |")
    lines.append("|---|---:|---:|")
    for name, cnt in prov_count.most_common(15):
        lines.append(f"| {name} | {cnt} | {cnt / total * 100:.0f}% |")
    lines.append("")
    lines.append(f"其余省份共 {sum(1 for _, c in prov_count.items() if c == 1)} 个各 1 份。")
    lines.append("")

    lines.append("## 三、城市 TOP 15")
    lines.append("")
    lines.append("| 城市 | 岗位数 |")
    lines.append("|---|---:|")
    for name, cnt in city_count.most_common(15):
        lines.append(f"| {name} | {cnt} |")
    lines.append("")

    lines.append("## 四、薪资分布（按区间中值，样本占比）")
    lines.append("")
    lines.append(f"可解析薪资 {parsed_salary}/{total} 条，其余为面议或格式异常。")
    lines.append("")
    lines.append("| 月薪区间 | 岗位数 | 占比 |")
    lines.append("|---|---:|---:|")
    order = [name for name, _ in SALARY_BUCKETS]
    for name in order:
        cnt = bucket_count.get(name, 0)
        lines.append(f"| {name} | {cnt} | {cnt / parsed_salary * 100:.0f}% |" if parsed_salary else f"| {name} | {cnt} | — |")
    lines.append("")

    if salary_pairs:
        lows = [p[0] for p in salary_pairs]
        highs = [p[1] for p in salary_pairs]
        lows.sort()
        highs.sort()
        lines.append(f"- 最低薪下界中位数：{lows[len(lows) // 2]:.1f}k")
        lines.append(f"- 最高薪上界中位数：{highs[len(highs) // 2]:.1f}k")
        lines.append("")

    lines.append("## 五、学历要求")
    lines.append("")
    lines.append("| 学历 | 岗位数 | 占比 |")
    lines.append("|---|---:|---:|")
    for name, cnt in degree_count.most_common():
        lines.append(f"| {name} | {cnt} | {cnt / total * 100:.0f}% |")
    lines.append("")

    report = "\n".join(lines).rstrip() + "\n"
    report_path = out_dir / "SUMMARY.md"
    report_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\n报告已写入：{report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
