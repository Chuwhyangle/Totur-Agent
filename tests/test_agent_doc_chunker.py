from __future__ import annotations

from app.services.agent_doc_chunker import parse_agent_doc_html


COURSE = "Agent 求职面试全攻略"
SOURCE = "corpus/Agent_doc/course/04-理论面试.html"


def reveal_html(*slides: str, title: str = "04 · 理论面试", subtitle: str = "高频考点") -> str:
    rendered = "\n".join(
        f'<section class="content-slide"><div class="slide-content-wrapper">{slide}</div></section>'
        for slide in slides
    )
    return f"""
    <html>
      <head><title>{title}</title><style>.hidden {{ display:none }}</style></head>
      <body>
        <section class="title-slide">
          <h1 class="main-title">{title}</h1>
          <div class="main-subtitle">{subtitle}</div>
          <div class="scroll-hint"><p>按 Space 键</p></div>
        </section>
        <div class="reveal"><div class="slides"><section>{rendered}</section></div></div>
        <script>window.noise = true</script>
      </body>
    </html>
    """


def test_reveal_parser_keeps_order_hierarchy_and_continuation_slides():
    document = parse_agent_doc_html(
        reveal_html(
            "<h2>Agent 核心</h2>",
            "<h3>Q8【中级】ReAct 模式的核心思想？</h3><p>问题页答案。</p>",
            "<p>这是续页说明。</p>",
            "<h3>Q9【中级】Plan-Execute 何时使用？</h3><p>下一题答案。</p>",
            "<h2>RAG 专项</h2><p>章节导言。</p>",
            "<p>导言续页。</p>",
        ),
        source=SOURCE,
        course_title=COURSE,
    )

    assert document.lesson_title == "04 · 理论面试"
    assert document.subtitle == "高频考点"
    assert document.section_titles == ("Agent 核心", "RAG 专项")

    details = [unit for unit in document.units if unit.chunk_type in {"qa", "topic", "article", "trend"}]
    assert [(unit.chunk_type, unit.title_path) for unit in details] == [
        ("qa", ("Agent 核心", "Q8【中级】ReAct 模式的核心思想？")),
        ("qa", ("Agent 核心", "Q9【中级】Plan-Execute 何时使用？")),
        ("article", ("RAG 专项",)),
    ]
    assert details[0].content == "问题页答案。\n\n这是续页说明。"
    assert (details[0].slide_start, details[0].slide_end) == (2, 3)
    assert details[1].content == "下一题答案。"
    assert (details[1].slide_start, details[1].slide_end) == (4, 4)
    assert details[2].content == "章节导言。\n\n导言续页。"
    assert (details[2].slide_start, details[2].slide_end) == (5, 6)


def test_short_complete_question_is_not_merged_with_next_question():
    document = parse_agent_doc_html(
        reveal_html(
            "<h2>LLM 基础</h2>",
            "<h3>Q1：什么是 Token？</h3><p>最小单元。</p>",
            "<h3>Q2：为什么按 Token 计费？</h3><p>因为计算量相关。</p>",
        ),
        source=SOURCE,
        course_title=COURSE,
    )

    qa_units = [unit for unit in document.units if unit.chunk_type == "qa"]
    assert len(qa_units) == 2
    assert [unit.content for unit in qa_units] == ["最小单元。", "因为计算量相关。"]
    assert qa_units[0].parent_key != qa_units[1].parent_key


def test_intro_content_is_kept_and_blank_or_decorative_slides_are_filtered():
    document = parse_agent_doc_html(
        reveal_html(
            "<div class='mac-header'>窗口按钮</div><div class='chapter-badge'>Chapter</div>",
            "<p>讲次导言。</p><div class='scroll-hint'>导航提示</div>",
            "<section></section>",
            "<h2>总结</h2><p>最终建议。</p>",
        ),
        source=SOURCE,
        course_title=COURSE,
    )

    details = [unit for unit in document.units if unit.chunk_type in {"article", "trend"}]
    assert [unit.content for unit in details] == ["讲次导言。", "最终建议。"]
    assert details[0].title_path == ()
    combined = "\n".join(unit.content for unit in document.units)
    assert "窗口按钮" not in combined
    assert "Chapter" not in combined
    assert "导航提示" not in combined
    assert "window.noise" not in combined


def test_parser_preserves_paragraph_list_table_code_and_image_alt():
    document = parse_agent_doc_html(
        reveal_html(
            """
            <h2>工程实践</h2>
            <h3>代码示例</h3>
            <p>先给结论 <a href="https://example.com">查看资料</a>。</p>
            <ol><li>第一步</li><li>第二步</li></ol>
            <table><thead><tr><th>方案</th><th>特点</th></tr></thead>
              <tbody><tr><td>ReAct</td><td>边想边做</td></tr></tbody></table>
            <div class="mac-window"><div class="mac-header">python</div>
              <pre><code class="language-python">def run():\n    return 1\n</code></pre>
            </div>
            <img src="diagram.png" alt="Agent 流程图">
            """
        ),
        source=SOURCE,
        course_title=COURSE,
    )

    unit = next(unit for unit in document.units if unit.chunk_type == "topic")
    assert "先给结论 查看资料。" in unit.content
    assert "https://example.com" not in unit.content
    assert "1. 第一步\n2. 第二步" in unit.content
    assert "| 方案 | 特点 |" in unit.content
    assert "| --- | --- |" in unit.content
    assert "| ReAct | 边想边做 |" in unit.content
    assert "```python\ndef run():\n    return 1\n```" in unit.content
    assert "Agent 流程图" in unit.content
    assert unit.contains_code is True


def test_multiple_questions_create_section_overview_and_lesson_overview():
    document = parse_agent_doc_html(
        reveal_html(
            "<h2>Agent 核心</h2>",
            "<h3>Q1：Agent 是什么？</h3><p>答案一。</p>",
            "<h3>Q2：ReAct 是什么？</h3><p>答案二。</p>",
        ),
        source=SOURCE,
        course_title=COURSE,
    )

    assert document.units[0].chunk_type == "lesson_overview"
    assert "高频考点" in document.units[0].content
    assert "- Agent 核心" in document.units[0].content
    overview = next(unit for unit in document.units if unit.chunk_type == "section_overview")
    assert overview.title_path == ("Agent 核心",)
    assert overview.content == "本章覆盖：\n- Q1：Agent 是什么？\n- Q2：ReAct 是什么？"


def test_topic_and_trend_classification_extracts_explicit_years_only():
    document = parse_agent_doc_html(
        reveal_html(
            "<h2>行业观察</h2>",
            "<h3>项目案例</h3><p>这是一个普通案例。</p>",
            "<h3>2025-2026 最新进展</h3><p>Agent 趋势持续演进。</p>",
        ),
        source=SOURCE,
        course_title=COURSE,
    )

    details = [unit for unit in document.units if unit.chunk_type in {"topic", "trend"}]
    assert details[0].chunk_type == "topic"
    assert details[0].time_tags == ()
    assert details[1].chunk_type == "trend"
    assert details[1].time_tags == (2025, 2026)


def test_course_map_cards_generate_course_overview():
    html = """
    <html><head><title>Agent 求职指南 · 课程主页</title></head><body>
      <div class="hero"><h1>Agent 求职指南</h1></div>
      <a class="course-card">
        <span class="lesson-no">第 01 讲</span>
        <h3 class="lesson-title">求职全景</h3>
        <p class="lesson-desc">建立岗位认知</p>
        <ul class="lesson-points"><li>岗位地图</li><li>能力模型</li></ul>
        <div class="card-foot">点击学习</div>
      </a>
      <a class="course-card">
        <span class="lesson-no">第 02 讲</span>
        <h3 class="lesson-title">项目打造</h3>
        <p class="lesson-desc">做出可写进简历的项目</p>
        <ul class="lesson-points"><li>选题</li></ul>
      </a>
    </body></html>
    """

    document = parse_agent_doc_html(
        html,
        source="corpus/Agent_doc/course/知识地图.html",
        course_title=COURSE,
    )

    assert document.kind == "course_map"
    assert len(document.units) == 1
    overview = document.units[0]
    assert overview.chunk_type == "course_overview"
    assert "第 01 讲 · 求职全景" in overview.content
    assert "简介：建立岗位认知" in overview.content
    assert "- 岗位地图" in overview.content
    assert "第 02 讲 · 项目打造" in overview.content
    assert "点击学习" not in overview.content

import hashlib
from dataclasses import replace

import pytest

from app.services.agent_doc_chunker import (
    ChunkingConfig,
    ChunkingError,
    ContentBlock,
    SemanticUnit,
    build_chunk_records,
    validate_chunk_records,
)


class CharacterTokenizer:
    """Predictable fast-tokenizer stand-in: one Unicode code point per token."""

    def count(self, text: str) -> int:
        return len(text)

    def offsets(self, text: str) -> tuple[tuple[int, int], ...]:
        return tuple((index, index + 1) for index in range(len(text)))


def make_unit(
    blocks: tuple[ContentBlock, ...],
    *,
    chunk_type: str = "topic",
    title_path: tuple[str, ...] = ("S", "T"),
    question: str | None = None,
) -> SemanticUnit:
    return SemanticUnit(
        source="corpus/Agent_doc/x.html",
        course="C",
        lesson="L",
        title_path=title_path,
        question=question,
        chunk_type=chunk_type,
        blocks=blocks,
        slide_start=2,
        slide_end=3,
        unit_index=4,
    )


def test_complete_semantic_unit_below_hard_threshold_ignores_soft_target():
    unit = make_unit((ContentBlock(kind="paragraph", text="字" * 600),))
    config = ChunkingConfig(
        split_threshold_tokens=1024,
        target_min_tokens=100,
        target_max_tokens=200,
        fallback_overlap_tokens=20,
    )

    records = build_chunk_records([unit], CharacterTokenizer(), config)

    assert len(records) == 1
    assert records[0]["split_method"] == "none"
    assert records[0]["part_index"] == 0
    assert records[0]["part_count"] == 1
    assert records[0]["content"] == "字" * 600


def test_overlong_unit_splits_at_structural_blocks_and_repeats_headers():
    unit = make_unit(
        tuple(ContentBlock(kind="paragraph", text=letter * 28) for letter in "甲乙丙丁")
    )
    config = ChunkingConfig(100, 45, 65, 8)

    records = build_chunk_records([unit], CharacterTokenizer(), config)

    assert len(records) >= 2
    assert {record["parent_id"] for record in records} == {
        "corpus/Agent_doc/x.html#unit-004"
    }
    assert [record["part_index"] for record in records] == list(range(len(records)))
    assert {record["part_count"] for record in records} == {len(records)}
    assert all(record["split_method"] == "structure" for record in records)
    assert all(record["overlap_tokens"] == 0 for record in records)
    assert all("课程：C\n讲次：L\n章节：S\n专题：T" in record["embedding_text"] for record in records)
    assert all(record["embedding_token_count"] <= 100 for record in records)


def test_overlong_paragraph_prefers_sentence_then_clause_boundaries():
    sentence_unit = make_unit(
        (ContentBlock(kind="paragraph", text="第一句内容很完整。第二句内容也完整。第三句继续说明。第四句结束。"),)
    )
    clause_unit = replace(
        sentence_unit,
        unit_index=5,
        blocks=(ContentBlock(kind="paragraph", text="甲" * 15 + "，" + "乙" * 15 + "，" + "丙" * 15),),
    )
    config = ChunkingConfig(45, 28, 35, 5)

    sentence_records = build_chunk_records([sentence_unit], CharacterTokenizer(), config)
    clause_records = build_chunk_records([clause_unit], CharacterTokenizer(), config)

    assert len(sentence_records) > 1
    assert {record["split_method"] for record in sentence_records} == {"sentence"}
    assert "".join(record["content"] for record in sentence_records) == sentence_unit.content
    assert len(clause_records) > 1
    assert {record["split_method"] for record in clause_records} == {"clause"}
    assert "".join(record["content"] for record in clause_records) == clause_unit.content


def test_unbreakable_text_uses_offset_token_window_with_overlap_only_there():
    unit = make_unit((ContentBlock(kind="paragraph", text="X" * 180),))
    config = ChunkingConfig(70, 35, 50, 7)

    records = build_chunk_records([unit], CharacterTokenizer(), config)

    assert len(records) > 2
    assert {record["split_method"] for record in records} == {"token_window"}
    assert records[0]["overlap_tokens"] == 0
    assert all(record["overlap_tokens"] == 7 for record in records[1:])
    assert all(record["embedding_token_count"] <= 70 for record in records)
    assert records[0]["content"].endswith(records[1]["content"][:7])


def test_table_splitting_repeats_header_and_keeps_rows_in_order():
    header = ("列一", "列二")
    rows = tuple((f"项目{index}", "值" * 18) for index in range(1, 7))
    text = "\n".join(
        [
            "| 列一 | 列二 |",
            "| --- | --- |",
            *(f"| {left} | {right} |" for left, right in rows),
        ]
    )
    unit = make_unit(
        (ContentBlock(kind="table", text=text, table_header=header, table_rows=rows),)
    )
    config = ChunkingConfig(95, 45, 65, 5)

    records = build_chunk_records([unit], CharacterTokenizer(), config)

    assert len(records) > 1
    assert all(record["content"].startswith("| 列一 | 列二 |\n| --- | --- |") for record in records)
    observed = "\n".join(record["content"] for record in records)
    positions = [observed.index(f"项目{index}") for index in range(1, 7)]
    assert positions == sorted(positions)
    assert all(record["split_method"] == "structure" for record in records)


def test_code_splitting_preserves_lines_and_uses_no_overlap_when_natural():
    code = "```python\n" + "\n\n".join(
        f"def task_{index}():\n    return '{'x' * 15}'" for index in range(5)
    ) + "\n```"
    unit = make_unit((ContentBlock(kind="code", text=code, language="python"),))
    config = ChunkingConfig(100, 45, 68, 8)

    records = build_chunk_records([unit], CharacterTokenizer(), config)

    assert len(records) > 1
    assert all(record["content"].startswith("```python\n") for record in records)
    assert all(record["content"].endswith("\n```") for record in records)
    assert all(record["overlap_tokens"] == 0 for record in records)
    assert all(record["split_method"] == "structure" for record in records)
    assert all("    return" in record["content"] for record in records)


def test_record_schema_counts_hashes_question_and_validation_are_exact():
    unit = make_unit(
        (ContentBlock(kind="paragraph", text="ReAct = Reasoning + Acting。"),),
        chunk_type="qa",
        question="Q8：ReAct 是什么？",
        title_path=("Agent 核心", "Q8：ReAct 是什么？"),
    )

    record = build_chunk_records(
        [unit], CharacterTokenizer(), ChunkingConfig()
    )[0]

    assert record["schema_version"] == 1
    assert record["chunk_id"] == "corpus/Agent_doc/x.html#unit-004#part-00"
    assert record["question"] == "Q8：ReAct 是什么？"
    assert record["title_path"] == ["Agent 核心", "Q8：ReAct 是什么？"]
    assert record["content_token_count"] == len(record["content"])
    assert record["embedding_token_count"] == len(record["embedding_text"])
    assert record["content_sha256"] == "sha256:" + hashlib.sha256(
        record["content"].encode("utf-8")
    ).hexdigest()
    validate_chunk_records([record], CharacterTokenizer(), ChunkingConfig())


def test_header_that_exceeds_hard_threshold_fails_instead_of_truncating():
    unit = make_unit(
        (ContentBlock(kind="paragraph", text="正文"),),
        title_path=("章节" * 30, "专题" * 30),
    )

    with pytest.raises(ChunkingError, match="title context"):
        build_chunk_records(
            [unit],
            CharacterTokenizer(),
            ChunkingConfig(60, 25, 40, 5),
        )


def test_invalid_chunking_configuration_is_rejected():
    with pytest.raises(ChunkingError, match="target token range"):
        ChunkingConfig(100, 80, 60, 10)
    with pytest.raises(ChunkingError, match="overlap"):
        ChunkingConfig(100, 20, 40, 40)



import json
from pathlib import Path

from scripts import build_agent_doc_chunks


def write_cli_corpus(root: Path) -> Path:
    source_dir = root / "corpus" / "Agent_doc" / "Agent 求职面试全攻略（10讲171页）"
    source_dir.mkdir(parents=True)
    (source_dir / "知识地图.html").write_text(
        """
        <html><body><div class="hero"><h1>Agent 求职指南</h1></div>
        <a class="course-card"><span class="lesson-no">第 04 讲</span>
        <h3 class="lesson-title">理论面试</h3><p class="lesson-desc">覆盖核心知识</p>
        <ul class="lesson-points"><li>Agent 核心</li></ul></a></body></html>
        """,
        encoding="utf-8",
    )
    (source_dir / "04-理论面试.html").write_text(
        reveal_html(
            "<h2>Agent 核心</h2>",
            "<h3>Q8：ReAct 是什么？</h3><p>Reasoning + Acting。</p>",
        ),
        encoding="utf-8",
    )
    return root / "corpus" / "Agent_doc"


def fake_loaded_tokenizer(model: str = "fake/tokenizer"):
    return build_agent_doc_chunks.LoadedTokenizer(
        tokenizer=CharacterTokenizer(),
        model=model,
        revision="abc123",
        library="transformers",
        library_version="5.14.1",
        add_special_tokens=True,
    )


def test_cli_builds_sorted_jsonl_and_stable_manifest(tmp_path, monkeypatch, capsys):
    write_cli_corpus(tmp_path)
    monkeypatch.setattr(build_agent_doc_chunks, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        build_agent_doc_chunks,
        "load_tokenizer",
        lambda model, revision=None: fake_loaded_tokenizer(model),
    )
    args = [
        "--source-dir",
        "corpus/Agent_doc",
        "--output-dir",
        "corpus/Agent_doc/processed",
        "--tokenizer-model",
        "fake/tokenizer",
    ]

    assert build_agent_doc_chunks.main(args) == 0

    output_dir = tmp_path / "corpus" / "Agent_doc" / "processed"
    jsonl_path = output_dir / "agent_doc_chunks.jsonl"
    manifest_path = output_dir / "agent_doc_manifest.json"
    first_jsonl = jsonl_path.read_bytes()
    first_manifest = manifest_path.read_bytes()
    records = [json.loads(line) for line in first_jsonl.decode("utf-8").splitlines()]
    manifest = json.loads(first_manifest)

    assert manifest["schema_version"] == 1
    assert manifest["source_root"] == "corpus/Agent_doc"
    assert manifest["source_file_count"] == 2
    assert manifest["chunk_count"] == len(records)
    assert manifest["chunk_counts_by_type"]["course_overview"] == 1
    assert manifest["chunk_counts_by_type"]["lesson_overview"] == 1
    assert manifest["tokenizer"] == {
        "model": "fake/tokenizer",
        "revision": "abc123",
        "library": "transformers",
        "library_version": "5.14.1",
        "add_special_tokens": True,
    }
    assert len(manifest["files"]) == 2
    assert all("\\" not in item["source"] for item in manifest["files"])
    assert records == sorted(
        records,
        key=lambda item: (item["source"], item["unit_index"], item["part_index"]),
    )
    assert manifest["output_sha256"] == "sha256:" + hashlib.sha256(first_jsonl).hexdigest()

    assert build_agent_doc_chunks.main(args) == 0
    assert jsonl_path.read_bytes() == first_jsonl
    assert manifest_path.read_bytes() == first_manifest
    assert "source_files=2" in capsys.readouterr().out


def test_cli_rejects_duplicate_html_content(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "corpus" / "Agent_doc"
    source_dir.mkdir(parents=True)
    duplicate = reveal_html("<h2>A</h2><p>same</p>")
    (source_dir / "a.html").write_text(duplicate, encoding="utf-8")
    (source_dir / "b.html").write_text(duplicate, encoding="utf-8")
    monkeypatch.setattr(build_agent_doc_chunks, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        build_agent_doc_chunks,
        "load_tokenizer",
        lambda model, revision=None: fake_loaded_tokenizer(model),
    )

    assert build_agent_doc_chunks.main(["--tokenizer-model", "fake"]) == 1

    captured = capsys.readouterr()
    assert "duplicate HTML content" in captured.err
    assert "a.html" in captured.err and "b.html" in captured.err
    assert not (source_dir / "processed" / "agent_doc_chunks.jsonl").exists()


def test_cli_tokenizer_load_failure_is_explicit_and_has_no_fallback(
    tmp_path, monkeypatch, capsys
):
    write_cli_corpus(tmp_path)
    monkeypatch.setattr(build_agent_doc_chunks, "PROJECT_ROOT", tmp_path)

    def fail_load(model, revision=None):
        raise build_agent_doc_chunks.AgentDocBuildError("cannot load matching tokenizer")

    monkeypatch.setattr(build_agent_doc_chunks, "load_tokenizer", fail_load)

    assert build_agent_doc_chunks.main(["--tokenizer-model", "missing/model"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot load matching tokenizer" in captured.err
    assert "Traceback" not in captured.err


def test_cli_failure_does_not_overwrite_existing_outputs(tmp_path, monkeypatch):
    source_dir = tmp_path / "corpus" / "Agent_doc"
    output_dir = source_dir / "processed"
    source_dir.mkdir(parents=True)
    output_dir.mkdir()
    duplicate = reveal_html("<h2>A</h2><p>same</p>")
    (source_dir / "a.html").write_text(duplicate, encoding="utf-8")
    (source_dir / "b.html").write_text(duplicate, encoding="utf-8")
    jsonl_path = output_dir / "agent_doc_chunks.jsonl"
    manifest_path = output_dir / "agent_doc_manifest.json"
    jsonl_path.write_text("old-jsonl", encoding="utf-8")
    manifest_path.write_text("old-manifest", encoding="utf-8")
    monkeypatch.setattr(build_agent_doc_chunks, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        build_agent_doc_chunks,
        "load_tokenizer",
        lambda model, revision=None: fake_loaded_tokenizer(model),
    )

    assert build_agent_doc_chunks.main(["--tokenizer-model", "fake"]) == 1
    assert jsonl_path.read_text(encoding="utf-8") == "old-jsonl"
    assert manifest_path.read_text(encoding="utf-8") == "old-manifest"


def test_atomic_pair_write_rolls_back_if_second_replace_fails(tmp_path, monkeypatch):
    jsonl_path = tmp_path / "agent_doc_chunks.jsonl"
    manifest_path = tmp_path / "agent_doc_manifest.json"
    jsonl_path.write_bytes(b"old-jsonl")
    manifest_path.write_bytes(b"old-manifest")
    real_replace = build_agent_doc_chunks.os.replace
    replacement_count = 0

    def flaky_replace(source, destination):
        nonlocal replacement_count
        destination = Path(destination)
        if destination in {jsonl_path, manifest_path} and Path(source).suffix == ".tmp":
            replacement_count += 1
            if replacement_count == 2:
                raise OSError("second replace failed")
        return real_replace(source, destination)

    monkeypatch.setattr(build_agent_doc_chunks.os, "replace", flaky_replace)

    with pytest.raises(build_agent_doc_chunks.AgentDocBuildError, match="atomic output"):
        build_agent_doc_chunks.atomic_write_outputs(
            jsonl_path=jsonl_path,
            jsonl_bytes=b"new-jsonl",
            manifest_path=manifest_path,
            manifest_bytes=b"new-manifest",
        )

    assert jsonl_path.read_bytes() == b"old-jsonl"
    assert manifest_path.read_bytes() == b"old-manifest"


def test_cli_uses_embedding_model_environment_default(tmp_path, monkeypatch):
    write_cli_corpus(tmp_path)
    monkeypatch.setattr(build_agent_doc_chunks, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("EMBEDDING_MODEL", "env/tokenizer")
    calls = {}

    def capture(model, revision=None):
        calls["model"] = model
        calls["revision"] = revision
        return fake_loaded_tokenizer(model)

    monkeypatch.setattr(build_agent_doc_chunks, "load_tokenizer", capture)

    assert build_agent_doc_chunks.main([]) == 0
    assert calls == {"model": "env/tokenizer", "revision": None}


def test_tokenizer_revision_resolves_from_huggingface_snapshot_path(tmp_path, monkeypatch):
    commit = "1d8ad4ca9b3dd8059ad90a75d4983776a23d44af"
    cached = tmp_path / "models--Qwen--Qwen3" / "snapshots" / commit / "tokenizer_config.json"
    cached.parent.mkdir(parents=True)
    cached.write_text("{}", encoding="utf-8")

    class TokenizerWithoutCommit:
        init_kwargs = {}

    monkeypatch.setattr(
        "huggingface_hub.try_to_load_from_cache",
        lambda repo_id, filename, revision: str(cached),
    )

    assert build_agent_doc_chunks.resolve_tokenizer_revision(
        "Qwen/Qwen3-Embedding-8B",
        None,
        TokenizerWithoutCommit(),
    ) == commit


def test_overlong_list_splits_between_items_without_overlap():
    items = tuple(f"事项{index}" + "值" * 16 for index in range(1, 7))
    text = "\n".join(f"- {item}" for item in items)
    unit = make_unit((ContentBlock(kind="list", text=text, items=items),))

    records = build_chunk_records(
        [unit],
        CharacterTokenizer(),
        ChunkingConfig(90, 40, 60, 6),
    )

    assert len(records) > 1
    assert all(record["split_method"] == "structure" for record in records)
    assert all(record["overlap_tokens"] == 0 for record in records)
    observed = "\n".join(record["content"] for record in records)
    positions = [observed.index(f"事项{index}") for index in range(1, 7)]
    assert positions == sorted(positions)


def test_course_overview_refuses_to_split_inside_one_course_card():
    unit = SemanticUnit(
        source="corpus/Agent_doc/map.html",
        course="C",
        lesson=None,
        title_path=(),
        question=None,
        chunk_type="course_overview",
        blocks=(ContentBlock(kind="card", text="一句。" * 40),),
        slide_start=None,
        slide_end=None,
        unit_index=0,
    )

    with pytest.raises(ChunkingError, match="course card"):
        build_chunk_records(
            [unit],
            CharacterTokenizer(),
            ChunkingConfig(70, 30, 50, 5),
        )


def test_single_overlong_code_line_uses_token_window_not_clause_splitting():
    code = "```python\nvalue = " + ("word " * 45).rstrip() + "\n```"
    unit = make_unit((ContentBlock(kind="code", text=code, language="python"),))

    records = build_chunk_records(
        [unit],
        CharacterTokenizer(),
        ChunkingConfig(80, 35, 58, 6),
    )

    assert len(records) > 1
    assert {record["split_method"] for record in records} == {"token_window"}
    assert records[0]["overlap_tokens"] == 0
    assert all(record["overlap_tokens"] == 6 for record in records[1:])
    assert all(record["content"].startswith("```python\n") for record in records)
    assert all(record["content"].endswith("\n```") for record in records)
