# self-llm 外部语料导入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从固定的 `self-llm` Git commit 导出全部 Markdown，规范化 Windows 不可 checkout 的路径，生成可复用语料快照，并让正式 RAG 索引与原 `docs/` 共用一个 Collection。

**Architecture:** Git CLI 负责 partial bare clone、commit/tree/blob 读取；`external_corpus_importer.py` 接收已解析条目，完成路径消歧、Manifest 和 staging 原子替换。索引 builder 接受多个相对 `corpus_root` 的源目录，统一排序后分块和 embedding；旧单目录调用保持兼容。

**Tech Stack:** Python 3.14、pytest、标准库 `subprocess/pathlib/shutil/hashlib/json/unicodedata`、现有 Chroma/Embedding/Manifest 服务、PowerShell。

---

## 文件边界

- Create: `app/services/external_corpus_importer.py` — 路径规范化、纯导入、Manifest、staging/备份替换。
- Create: `scripts/import_self_llm_corpus.py` — partial bare clone、fetch、commit/tree/blob CLI。
- Create: `tests/test_external_corpus_importer.py` — 导入逻辑测试。
- Create: `tests/test_import_self_llm_corpus.py` — CLI 编排测试。
- Modify: `app/services/knowledge_index_builder.py` — 多源支持，保留旧 `source_dir`。
- Modify: `tests/test_knowledge_index_builder.py` — 多源排序和单源兼容测试。
- Modify: `scripts/build_knowledge_index.py`、`app/services/rag_settings.py` — 正式联合索引配置。
- Modify: `.gitignore` — 忽略 `/external/`。
- Generated and committed: `corpus/self-llm/LICENSE`、`corpus/self-llm/corpus_manifest.json`、`corpus/self-llm/docs/**/*.md`。
- Local and ignored: `external/self-llm.git/`。

## 固定接口和约束

- 上游 URL：`https://github.com/datawhalechina/self-llm.git`；commit：`42c1bff4334f4c21c33e5791f29e9cdca5d47c61`；许可证：`Apache-2.0`。
- `normalize_git_path(original_path) -> str` 返回带 `docs/` 前缀的 POSIX 路径；NFC、原始 `\` 视作分隔符、控制字符和 `< > : " | ? *` 替换为 `_`、尾随空格/点删除、Windows 保留名加 `_`。
- `build_path_mapping(original_paths) -> dict[str, str]` 先按原始路径排序，以 Unicode `casefold()` 检测冲突；冲突在扩展名前加 `--` 和原始路径 SHA-256 前 8 位。
- `import_corpus(...) -> ImportResult` 接收 `GitTreeEntry(original_path, content)` 和许可证 bytes；Manifest 字段为 `original_path`、`normalized_path`、`content_sha256`、`byte_count`，文件哈希使用 `sha256:<hex>`。
- fingerprint 只由 URL、commit、license 及按规范路径排序的稳定文件字段组成，不包含时间和本机绝对路径。
- 导入前所有 Git/UTF-8/写入错误都不得替换现有 `corpus/self-llm/`；staging、目标、备份解析路径必须位于项目 `corpus/` 下。
- `build_knowledge_index` 新增 `source_dirs: Iterable[Path] | None = None`；传 `source_dir=Path("docs")` 的历史调用不变；两者同时传入或源目录为空时报 `ValueError`。

---

### Task 1：路径规范化和稳定消歧

**Files:**
- Create: `tests/test_external_corpus_importer.py`
- Create: `app/services/external_corpus_importer.py`

- [ ] **Step 1：写 RED 测试**

```python
import pytest
from app.services.external_corpus_importer import build_path_mapping, normalize_git_path


def test_normalize_git_path_handles_backslash_invalid_suffix_and_reserved_name():
    assert normalize_git_path(
        r"models_ascend/qwen3.5\3.6/CON.md"
    ) == "docs/models_ascend/qwen3.5/3.6/_CON.md"
    assert normalize_git_path("folder/hello. /readme.md") == "docs/folder/hello/readme.md"


def test_normalize_git_path_rejects_absolute_and_parent_paths():
    for value in ("/root.md", r"C:\root.md", "../root.md", "a/../../root.md", ""):
        with pytest.raises(ValueError):
            normalize_git_path(value)


def test_mapping_disambiguates_casefold_collision_deterministically():
    paths = ["docs/Readme.md", "docs/readme.md"]
    first = build_path_mapping(paths)
    second = build_path_mapping(list(reversed(paths)))
    assert first == second
    assert len(set(first.values())) == 2
    assert all("--" in value for value in first.values())
```

- [ ] **Step 2：确认 RED**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& E:\AI Project\Totur-Agent\.venv\Scripts\python.exe -m pytest tests/test_external_corpus_importer.py -q -p no:cacheprovider --basetemp=E:\AI Project\Totur-Agent\.test-tmp\self-llm-task1-red
```

Expected：因模块不存在而 FAIL，而不是测试收集错误。

- [ ] **Step 3：最小实现**

在 `external_corpus_importer.py` 实现上述函数：先 NFC，再把 `\` 换成 `/`；拒绝空值、前导 `/`、盘符绝对路径以及 `.`/`..`；逐组件替换非法字符、清理尾随空格/点、把空组件变 `_`；保留名判断忽略扩展名。`build_path_mapping` 对排序后的原始路径分组，冲突项在 suffix 前加 `--{sha256(original.encode("utf-8")).hexdigest()[:8]}`，最后验证 `casefold()` 后没有重复。

- [ ] **Step 4：确认 GREEN**

```powershell
& E:\AI Project\Totur-Agent\.venv\Scripts\python.exe -m pytest tests/test_external_corpus_importer.py -q -p no:cacheprovider --basetemp=E:\AI Project\Totur-Agent\.test-tmp\self-llm-task1-green
```

Expected：3 passed。

- [ ] **Step 5：提交**

```powershell
git add app/services/external_corpus_importer.py tests/test_external_corpus_importer.py
git commit -m "feat: normalize imported corpus paths"
```

### Task 2：Markdown 过滤、Manifest 和原子 staging 导入

**Files:**
- Modify: `tests/test_external_corpus_importer.py`
- Modify: `app/services/external_corpus_importer.py`

- [ ] **Step 1：写 RED 测试**

```python
import pytest
from app.services.external_corpus_importer import GitTreeEntry, import_corpus


def test_import_exports_only_markdown_and_writes_manifest(tmp_path):
    result = import_corpus(
        project_root=tmp_path, commit_sha="a" * 40,
        repository_url="https://github.com/datawhalechina/self-llm.git",
        license_name="Apache-2.0", license_bytes=b"Apache License",
        entries=[
            GitTreeEntry("README.md", b"# readme\n"),
            GitTreeEntry(r"models_ascend/qwen3.5\3.6/guide.md", b"guide\n"),
            GitTreeEntry("image.png", b"png"), GitTreeEntry("script.py", b"print(1)"),
            GitTreeEntry("book.ipynb", b"{}"), GitTreeEntry("dataset.json", b"{}"),
        ],
    )
    docs = sorted((tmp_path / "corpus/self-llm/docs").rglob("*.md"))
    assert len(docs) == 2
    assert (tmp_path / "corpus/self-llm/docs/models_ascend/qwen3.5/3.6/guide.md").read_bytes() == b"guide\n"
    assert result.manifest["markdown_file_count"] == 2
    assert result.manifest["files"][0] == {
        "original_path": "README.md", "normalized_path": "docs/README.md",
        "content_sha256": "sha256:" + __import__("hashlib").sha256(b"# readme\n").hexdigest(),
        "byte_count": 9,
    }


def test_invalid_utf8_does_not_replace_existing_target(tmp_path):
    target = tmp_path / "corpus/self-llm/docs/old.md"
    target.parent.mkdir(parents=True); target.write_bytes(b"old")
    with pytest.raises(UnicodeDecodeError):
        import_corpus(
            project_root=tmp_path, commit_sha="b" * 40, repository_url="url",
            license_name="Apache-2.0", license_bytes=b"license",
            entries=[GitTreeEntry("bad.md", b"\xff")],
        )
    assert target.read_bytes() == b"old"


def test_same_input_has_same_fingerprint(tmp_path):
    kwargs = dict(
        commit_sha="c" * 40, repository_url="url", license_name="Apache-2.0",
        license_bytes=b"license", entries=[GitTreeEntry("b.md", b"b"), GitTreeEntry("a.md", b"a")],
    )
    assert import_corpus(project_root=tmp_path / "one", **kwargs).manifest["fingerprint"] == \
        import_corpus(project_root=tmp_path / "two", **kwargs).manifest["fingerprint"]
```

另加以下原子替换失败测试：

```python
def test_replace_failure_restores_existing_target_and_removes_staging(tmp_path, monkeypatch):
    import shutil
    target = tmp_path / "corpus/self-llm"
    old = target / "docs/old.md"
    old.parent.mkdir(parents=True); old.write_bytes(b"old")
    real_move = shutil.move
    calls = []
    def fail_second_move(source, destination):
        calls.append((source, destination))
        if len(calls) == 2:
            raise OSError("replace failed")
        return real_move(source, destination)
    monkeypatch.setattr(shutil, "move", fail_second_move)
    with pytest.raises(OSError, match="replace failed"):
        import_corpus(
            project_root=tmp_path, commit_sha="e" * 40, repository_url="url",
            license_name="Apache-2.0", license_bytes=b"license",
            entries=[GitTreeEntry("new.md", b"new")],
        )
    assert old.read_bytes() == b"old"
    assert not list((tmp_path / "corpus").glob(".self-llm-staging-*"))
```

- [ ] **Step 2：确认 RED**

```powershell
& E:\AI Project\Totur-Agent\.venv\Scripts\python.exe -m pytest tests/test_external_corpus_importer.py -q -p no:cacheprovider --basetemp=E:\AI Project\Totur-Agent\.test-tmp\self-llm-task2-red
```

Expected：因 `GitTreeEntry`/`import_corpus` 未实现而 FAIL。

- [ ] **Step 3：最小实现**

实现不可变 `GitTreeEntry`、`ImportResult` 和 `import_corpus`：只导出后缀 `.md` 的条目；先全部 UTF-8 decode，再创建 `corpus/.self-llm-staging-<uuid>`；写 `docs/`、根 `LICENSE` 和 JSON Manifest。fingerprint 使用 `json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))` 的 UTF-8 SHA-256。用 `Path.resolve()`/`relative_to()`验证边界；按“旧目标→备份、staging→目标、成功删备份、异常恢复备份”替换，异常先删除 staging，不触及旧目标。

- [ ] **Step 4：确认 GREEN**

```powershell
& E:\AI Project\Totur-Agent\.venv\Scripts\python.exe -m pytest tests/test_external_corpus_importer.py -q -p no:cacheprovider --basetemp=E:\AI Project\Totur-Agent\.test-tmp\self-llm-task2-green
```

Expected：7 passed。

- [ ] **Step 5：提交**

```powershell
git add app/services/external_corpus_importer.py tests/test_external_corpus_importer.py
git commit -m "feat: import self-llm markdown snapshot atomically"
```

### Task 3：Git partial bare clone CLI

**Files:**
- Create: `scripts/import_self_llm_corpus.py`
- Create: `tests/test_import_self_llm_corpus.py`

- [ ] **Step 1：写 RED 测试**

```python
import importlib


def test_cli_fetches_ref_resolves_commit_and_imports_tree(tmp_path, monkeypatch, capsys):
    cli = importlib.import_module("scripts.import_self_llm_corpus")
    calls = []
    monkeypatch.setattr(cli, "run_git", lambda repo, *args: calls.append((repo, args)) or b"x")
    monkeypatch.setattr(cli, "resolve_commit", lambda repo, ref: "d" * 40)
    monkeypatch.setattr(cli, "read_tree_entries", lambda repo, commit: [])`n    monkeypatch.setattr(cli, "read_license", lambda repo, commit: b"license")
    monkeypatch.setattr(cli, "read_blob", lambda repo, sha: b"license")
    monkeypatch.setattr(cli, "import_corpus", lambda **kwargs: type("R", (), {"manifest": {"markdown_file_count": 0, "commit_sha": "d" * 40}})())
    assert cli.main(["--project-root", str(tmp_path), "--ref", "refs/heads/main"]) == 0
    assert any("fetch" in args for _, args in calls)
    assert "commit=" + "d" * 40 in capsys.readouterr().out


def test_cli_returns_nonzero_when_git_fails(tmp_path, monkeypatch):
    cli = importlib.import_module("scripts.import_self_llm_corpus")
    monkeypatch.setattr(cli, "ensure_repository", lambda *args: (_ for _ in ()).throw(RuntimeError("git down")))
    assert cli.main(["--project-root", str(tmp_path), "--ref", "main"]) == 1
```

- [ ] **Step 2：确认 RED**

```powershell
& E:\AI Project\Totur-Agent\.venv\Scripts\python.exe -m pytest tests/test_import_self_llm_corpus.py -q -p no:cacheprovider --basetemp=E:\AI Project\Totur-Agent\.test-tmp\self-llm-task3-red
```

Expected：CLI 模块或函数不存在而 FAIL。

- [ ] **Step 3：最小实现**

固定默认 URL、ref 和 `external/self-llm.git`。不存在时运行 `git clone --bare --filter=blob:none --no-checkout URL path`，存在时运行 `git fetch --filter=blob:none origin ref`；`resolve_commit` 用 `git rev-parse --verify ref^{commit}`；`read_tree_entries` 用 `git ls-tree -r -z --full-tree commit` 解析 `mode type sha<TAB>path`，只保留 `blob` 且后缀 `.md`，同时找到根 `LICENSE`；`read_blob` 用 `git cat-file blob sha`。捕获 `RuntimeError/OSError/UnicodeError/ValueError` 返回 1，成功打印 commit、数量和 Manifest 路径。

- [ ] **Step 4：确认 GREEN**

```powershell
& E:\AI Project\Totur-Agent\.venv\Scripts\python.exe -m pytest tests/test_import_self_llm_corpus.py -q -p no:cacheprovider --basetemp=E:\AI Project\Totur-Agent\.test-tmp\self-llm-task3-green
```

Expected：2 passed。

- [ ] **Step 5：提交**

```powershell
git add scripts/import_self_llm_corpus.py tests/test_import_self_llm_corpus.py
git commit -m "feat: add self-llm corpus import CLI"
```

### Task 4：多源联合索引

**Files:**
- Modify: `tests/test_knowledge_index_builder.py`
- Modify: `app/services/knowledge_index_builder.py`

- [ ] **Step 1：写 RED 测试**

```python
def test_multiple_source_dirs_are_globally_sorted_and_rebuilt_together(tmp_path):
    write_corpus_file(tmp_path, "docs/local.md", "local")
    write_corpus_file(tmp_path, "corpus/self-llm/docs/guide.md", "external")
    repository = RecordingRepository()
    result = build_knowledge_index(**build_kwargs(
        tmp_path, source_dir=None,
        source_dirs=(Path("docs"), Path("corpus/self-llm/docs")),
        repository=repository,
    ))
    chunks, _ = repository.calls[0]
    assert [chunk.source for chunk in chunks] == [
        "corpus/self-llm/docs/guide.md", "docs/local.md"
    ]
    assert [item.path for item in result.manifest.files] == [
        "corpus/self-llm/docs/guide.md", "docs/local.md"
    ]


def test_single_source_dir_keyword_remains_compatible(tmp_path):
    write_corpus_file(tmp_path, "docs/a.md", "a")
    assert build_knowledge_index(**build_kwargs(tmp_path)).indexed_count == 1
```

- [ ] **Step 2：确认 RED**

```powershell
& E:\AI Project\Totur-Agent\.venv\Scripts\python.exe -m pytest tests/test_knowledge_index_builder.py::test_multiple_source_dirs_are_globally_sorted_and_rebuilt_together -q -p no:cacheprovider --basetemp=E:\AI Project\Totur-Agent\.test-tmp\self-llm-task4-red
```

Expected：unexpected keyword `source_dirs`。

- [ ] **Step 3：最小实现**

将签名扩展为 `source_dir: Path | None = None, source_dirs: Iterable[Path] | None = None`；仅传一个时归一化为 tuple，同时传入或为空报 `ValueError`。收集各源目录的 `rglob("*.md")`，以相对于统一 root 的 POSIX 路径去重并全局排序；后续 chunk、embedding 和 Manifest 逻辑不变。

- [ ] **Step 4：确认 GREEN**

```powershell
& E:\AI Project\Totur-Agent\.venv\Scripts\python.exe -m pytest tests/test_knowledge_index_builder.py -q -p no:cacheprovider --basetemp=E:\AI Project\Totur-Agent\.test-tmp\self-llm-task4-green
```

Expected：原有测试和新增测试全部通过。

- [ ] **Step 5：提交**

```powershell
git add app/services/knowledge_index_builder.py tests/test_knowledge_index_builder.py
git commit -m "feat: build knowledge index from multiple corpus roots"
```

### Task 5：正式索引配置和 Git 缓存忽略

**Files:**
- Modify: `app/services/rag_settings.py`
- Modify: `scripts/build_knowledge_index.py`
- Modify: `.gitignore`
- Modify: `tests/test_knowledge_index_builder.py`

- [ ] **Step 1：写 RED 并运行**

```python
def test_formal_rag_sources_include_local_and_self_llm_corpus():
    from app.services.rag_settings import KNOWLEDGE_SOURCE_DIRS
    assert KNOWLEDGE_SOURCE_DIRS == ("docs", "corpus/self-llm/docs")
```

```powershell
& E:\AI Project\Totur-Agent\.venv\Scripts\python.exe -m pytest tests/test_knowledge_index_builder.py::test_formal_rag_sources_include_local_and_self_llm_corpus -q -p no:cacheprovider --basetemp=E:\AI Project\Totur-Agent\.test-tmp\self-llm-task5-red
```

Expected：`KNOWLEDGE_SOURCE_DIRS` 不存在而 FAIL。

- [ ] **Step 2：实现并运行 GREEN**

在 `rag_settings.py` 保留 `KNOWLEDGE_SOURCE_DIR = "docs"`，新增：

```python
KNOWLEDGE_SOURCE_DIRS = ("docs", "corpus/self-llm/docs")
```

脚本导入该常量，并把 builder 调用改为：

```python
source_dirs=tuple(Path(item) for item in KNOWLEDGE_SOURCE_DIRS),
corpus_label="+".join(KNOWLEDGE_SOURCE_DIRS),
```

`.gitignore` 增加 `/external/`，运行上面的单测，Expected：PASS。

- [ ] **Step 3：提交**

```powershell
git add app/services/rag_settings.py scripts/build_knowledge_index.py tests/test_knowledge_index_builder.py .gitignore
git commit -m "feat: configure combined local and external corpus indexing"
```

### Task 6：基线、真实导入和离线验收

**Files:**
- Generated: `corpus/self-llm/**`

- [ ] **Step 1：运行完整离线测试**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& E:\AI Project\Totur-Agent\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --basetemp=E:\AI Project\Totur-Agent\.test-tmp\self-llm-full
```

Expected：0 failures；已有失败须记录精确测试和输出，不改写冻结数据。

- [ ] **Step 2：执行固定版本导入**

```powershell
& E:\AI Project\Totur-Agent\.venv\Scripts\python.exe scripts/import_self_llm_corpus.py --ref 42c1bff4334f4c21c33e5791f29e9cdca5d47c61
```

Expected：返回 0，输出固定 commit、`files=284` 和 `corpus/self-llm/corpus_manifest.json`；`corpus/self-llm/docs` 恰有 284 个 `.md`，不存在 PNG/Python/Notebook/数据文件，并存在规范化后的 `models_ascend/qwen3.5/3.6/...` 路径。

- [ ] **Step 3：用脚本校验快照**

```powershell
$manifest = Get-Content corpus/self-llm/corpus_manifest.json -Raw | ConvertFrom-Json
if ($manifest.commit_sha -ne '42c1bff4334f4c21c33e5791f29e9cdca5d47c61') { throw 'commit mismatch' }
if ($manifest.markdown_file_count -ne 284) { throw 'markdown count mismatch' }
if ((Get-ChildItem corpus/self-llm/docs -Recurse -Filter *.md).Count -ne 284) { throw 'file count mismatch' }
if (Get-ChildItem corpus/self-llm/docs -Recurse -File | Where-Object Extension -ne '.md') { throw 'non markdown exported' }
```

再运行：

```powershell
& E:\AI Project\Totur-Agent\.venv\Scripts\python.exe -m pytest tests/test_external_corpus_importer.py tests/test_import_self_llm_corpus.py tests/test_knowledge_index_builder.py -q -p no:cacheprovider --basetemp=E:\AI Project\Totur-Agent\.test-tmp\self-llm-acceptance
```

- [ ] **Step 4：提交语料快照并推送**

```powershell
git add corpus/self-llm
git commit -m "data: add self-llm markdown corpus snapshot"
git push
```

本轮不自动调用真实 Embedding，避免未经确认产生费用；正式脚本已配置为两源并写同一 `learning_notes` Collection。

### Task 7：最终验证

- [ ] **Step 1：仓库卫生检查**

```powershell
git diff --check
git status --short --branch
git log --oneline -8
```

确认 `/external/` 被忽略、`corpus/self-llm/` 被跟踪、没有 `.pytest_cache` 或临时文件进入提交。

- [ ] **Step 2：运行最终后端测试**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& E:\AI Project\Totur-Agent\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --basetemp=E:\AI Project\Totur-Agent\.test-tmp\self-llm-final
```

Expected：0 failures；只有看到实际输出后才报告测试状态。