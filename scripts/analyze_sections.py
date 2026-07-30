"""按当前分块器的标题切分逻辑，统计每个标题章节的字符长度分布。

忠实复刻 app/services/knowledge_chunker.py 的 HEADING_PATTERN 与章节累积逻辑
(逐行匹配 ^#{1,3}，命中即 flush 上一节)，不做任何滑窗兜底，只量"切之前的章节原文长度"。

用法（项目根目录下）：
    .venv\\Scripts\\python.exe scripts\\analyze_sections.py
结果会打印到终端，并把明细写到 section_length_stats.csv。
"""
from __future__ import annotations

import csv
import re
import statistics
import sys
from pathlib import Path

HEADING_PATTERN = re.compile(r"^(#{1,3})\s+(.+?)\s*$")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOTS = {
    "docs": PROJECT_ROOT / "docs",
    "self-llm": PROJECT_ROOT / "corpus" / "self-llm" / "docs",
}


def iter_sections(text: str):
    """复刻 chunk_markdown 的章节累积：逐行扫描，命中标题 flush 上一节。返回 (title_path, content)。"""
    title_stack: list[str] = []
    section_lines: list[str] = []
    section_title_path = ""
    out = []
    for line in text.splitlines():
        m = HEADING_PATTERN.match(line)
        if m:
            if section_lines:
                out.append((section_title_path, "\n".join(section_lines).strip()))
            level = len(m.group(1))
            title = m.group(2).strip()
            title_stack = title_stack[: level - 1]
            title_stack.append(title)
            section_title_path = " > ".join(title_stack)
            section_lines = [line.strip()]
        else:
            section_lines.append(line.rstrip())
    if section_lines:
        out.append((section_title_path, "\n".join(section_lines).strip()))
    return out


def section_body(content: str) -> str:
    """复刻 _section_body：有标题行则排除首行标题。"""
    lines = content.splitlines()
    if lines and HEADING_PATTERN.match(lines[0]):
        return "\n".join(lines[1:]).strip()
    return content.strip()


def cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    return cjk / len(text)


def estimate_tokens(text: str) -> int:
    """粗估 token：CJK 按每字 ~1.4 token，其余按每 4 字符 1 token。"""
    if not text:
        return 0
    r = cjk_ratio(text)
    cjk_chars = int(len(text) * r)
    other_chars = len(text) - cjk_chars
    return int(cjk_chars * 1.4 + other_chars / 4)


def percentile(data, p):
    if not data:
        return 0
    s = sorted(data)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def fmt(n):
    return f"{n:,.0f}"


def main():
    rows = []
    per_corpus = {"docs": [], "self-llm": []}

    for label, root in CORPUS_ROOTS.items():
        if not root.is_dir():
            print(f"[skip] {label}: {root} not found", file=sys.stderr)
            continue
        files = sorted(root.rglob("*.md"))
        for fp in files:
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                print(f"[err] {fp}: {exc}", file=sys.stderr)
                continue
            rel = fp.relative_to(PROJECT_ROOT)
            for title_path, content in iter_sections(text):
                body = section_body(content)
                if not body:
                    continue  # 空章节不入索引
                total = len(content)
                bodylen = len(body)
                r = cjk_ratio(content)
                tok = estimate_tokens(content)
                rows.append((label, str(rel), title_path or "(无标题前导)", total, bodylen, r, tok))
                per_corpus[label].append(total)

    out_csv = PROJECT_ROOT / "section_length_stats.csv"
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["corpus", "source", "title_path", "total_chars", "body_chars", "cjk_ratio", "est_tokens"])
        for r in rows:
            w.writerow(r)
    print(f"[csv] {out_csv}  rows={len(rows)}")

    def report(name, data):
        if not data:
            print(f"\n=== {name} === (无数据)")
            return
        thresholds = [512, 700, 1000, 1500, 2000, 3000, 4096]
        print(f"\n=== {name} ===")
        print(f"  章节数 N = {fmt(len(data))}")
        print(f"  字符  min={fmt(min(data))} max={fmt(max(data))} mean={fmt(statistics.mean(data))} median={fmt(statistics.median(data))}")
        print(f"  百分位  p75={fmt(percentile(data,.75))} p90={fmt(percentile(data,.9))} p95={fmt(percentile(data,.95))} p99={fmt(percentile(data,.99))}")
        print("  超阈值分布:")
        for t in thresholds:
            over = sum(1 for x in data if x > t)
            print(f"    > {t:>5} 字符: {fmt(over):>5} 段  ({over/len(data)*100:.1f}%)")
        buckets = [(0,256),(256,512),(513,700),(701,1000),(1001,1500),(1501,2048),(2049,3072),(3073,4096),(4097,10**9)]
        print("  区间分布:")
        for lo, hi in buckets:
            n = sum(1 for x in data if lo <= x <= hi)
            hi_s = fmt(hi) if hi < 10**8 else "INF"
            print(f"    {fmt(lo):>5}-{hi_s:>6}: {fmt(n):>5} 段  ({n/len(data)*100:.1f}%)")

    all_data = [r[3] for r in rows]
    report("全部语料 (docs + self-llm)", all_data)
    report("docs/ (项目自有文档)", per_corpus["docs"])
    report("corpus/self-llm (外部教程)", per_corpus["self-llm"])

    toks = [r[6] for r in rows]
    print("\n=== token 估算（全部，CJK×1.4 + 非CJK/4）===")
    print(f"  N={fmt(len(toks))} min={fmt(min(toks))} max={fmt(max(toks))} mean={fmt(statistics.mean(toks))} median={fmt(statistics.median(toks))}")
    for t in [128, 256, 384, 512, 700, 1000, 1500]:
        over = sum(1 for x in toks if x > t)
        print(f"  > {t:>5} token: {fmt(over):>5} 段  ({over/len(toks)*100:.1f}%)")

    rows_sorted = sorted(rows, key=lambda r: r[3], reverse=True)
    print("\n=== 最长 20 段 ===")
    print(f"  {'corpus':<8} {'总字符':>7} {'体字符':>7} {'CJK%':>5} {'估token':>7} source / title")
    for r in rows_sorted[:20]:
        print(f"  {r[0]:<8} {fmt(r[3]):>7} {fmt(r[4]):>7} {r[5]*100:>4.0f}% {fmt(r[6]):>7} {r[1]} :: {r[2][:60]}")


if __name__ == "__main__":
    main()
