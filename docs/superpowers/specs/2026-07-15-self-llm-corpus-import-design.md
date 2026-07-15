# self-llm 外部语料导入与联合索引设计

| 项 | 内容 |
|---|---|
| 日期 | 2026-07-15 |
| 上游仓库 | `https://github.com/datawhalechina/self-llm.git` |
| 首次固定版本 | `42c1bff4334f4c21c33e5791f29e9cdca5d47c61` |
| 实现基线 | `feature/v0.5-frozen-corpus-manifest` |
| 目标 | 在 Windows 上可复现地导入全部 Markdown，规范化路径，并与原 `docs/` 语料联合建库 |

## 1. 决策

采用 **partial bare clone + Git 对象导出**：不 checkout 上游工作树，直接读取提交树中的 Markdown blob。这样可以绕过上游路径 `models_ascend/qwen3.5\3.6/...` 在 Git for Windows 上无法 checkout 的问题，同时保留精确 commit 和原始路径。

语料文件物理隔离、索引逻辑合并：

- 原小语料继续位于 `docs/`；
- self-llm 导出到 `corpus/self-llm/docs/`；
- 正式构建时将两者写入同一个 `learning_notes` Chroma Collection；
- 冻结评测仍只使用 `tests/data/corpus/docs/`，不受外部语料变化影响。

不采用压缩包解压，因为更新与 commit 追踪较弱；不依赖 WSL，因为项目需要在现有 Windows 环境直接复现。

## 2. 目录布局

```text
external/
  self-llm.git/                 # partial bare clone，本地缓存，gitignore
corpus/
  self-llm/
    LICENSE                     # 上游 Apache-2.0 许可证
    corpus_manifest.json        # 导入来源、路径映射和文件哈希
    docs/                       # 全部规范化后的 Markdown
      README.md
      models/...
docs/                           # 现有小语料，保持原位
```

`external/self-llm.git/` 不提交；`corpus/self-llm/` 提交，使语料快照无需联网即可复用和评测。

## 3. 组件边界

### 3.1 `app/services/external_corpus_importer.py`

负责纯导入逻辑：

- 规范化仓库路径；
- 从 Git tree 条目筛选 `.md`；
- 读取 blob 并写入 staging 目录；
- 生成稳定路径映射和 Manifest；
- 校验目标始终位于项目 `corpus/` 内；
- staging 完整成功后替换正式目录。

该模块不读取应用环境变量、不连接 Chroma。

### 3.2 `scripts/import_self_llm_corpus.py`

负责 CLI 与 Git 命令：

```powershell
.\.venv\Scripts\python.exe scripts\import_self_llm_corpus.py `
  --ref 42c1bff4334f4c21c33e5791f29e9cdca5d47c61
```

行为：

1. `external/self-llm.git/` 不存在时执行 partial bare clone；
2. 已存在时从 `origin` fetch 指定 ref；
3. 解析 ref 为完整 commit SHA；
4. 枚举该提交的 tree，导出全部 `.md`；
5. 同时导出根目录 `LICENSE`；
6. 输出 commit、Markdown 文件数和 Manifest 路径。

网络、Git、UTF-8 解码或替换失败时返回非零，不留下半成品正式语料。

### 3.3 `app/services/knowledge_index_builder.py`

将单个 `source_dir` 扩展为向后兼容的多个源目录输入。所有文件仍按相对于统一 `corpus_root` 的 POSIX 路径排序，统一分块、Embedding、写入 Chroma 和生成索引 Manifest。

正式索引源目录：

```python
("docs", "corpus/self-llm/docs")
```

冻结评测继续传入单个：

```python
("docs",)
```

## 4. 路径规范化

输入路径来自 Git tree 的 UTF-8 字节，输出必须在 Windows 和 POSIX 上稳定：

1. Unicode 统一为 NFC；
2. 将原始反斜杠 `\` 视为路径分隔符；
3. 拒绝绝对路径、空路径、`.` 和 `..`；
4. 每个组件中的控制字符及 `< > : " | ? *` 替换为 `_`；
5. 删除组件结尾的空格和句点；空组件替换为 `_`；
6. Windows 保留名 `CON`、`PRN`、`AUX`、`NUL`、`COM1`–`COM9`、`LPT1`–`LPT9` 前置 `_`；
7. 以 Unicode casefold 后的路径检测大小写不敏感冲突；
8. 冲突文件在扩展名前追加 `--<原始路径 SHA-256 前 8 位>`。

例如：

```text
models_ascend/qwen3.5\3.6/01-Qwen3.6.md
→ models_ascend/qwen3.5/3.6/01-Qwen3.6.md
```

Manifest 始终保留 `original_path`，因此规范化不会丢失上游定位信息。

## 5. 导入 Manifest

`corpus/self-llm/corpus_manifest.json` 包含：

```json
{
  "schema_version": 1,
  "repository_url": "https://github.com/datawhalechina/self-llm.git",
  "commit_sha": "42c1bff4334f4c21c33e5791f29e9cdca5d47c61",
  "license": "Apache-2.0",
  "markdown_file_count": 284,
  "files": [
    {
      "original_path": "README.md",
      "normalized_path": "docs/README.md",
      "content_sha256": "sha256:<hex>",
      "byte_count": 19547
    }
  ],
  "fingerprint": "sha256:<hex>"
}
```

Fingerprint 只包含仓库 URL、commit、许可证及排序后的文件稳定字段；不包含导入时间和本机绝对路径。文件列表按 `normalized_path` 排序。

## 6. 原子替换与安全边界

导入先写入 `corpus/.self-llm-staging-<uuid>/`。全部文件、LICENSE、Manifest 生成并复核后：

1. 确认 staging、目标和备份的解析路径都位于项目 `corpus/`；
2. 将已有 `corpus/self-llm/` 移到同目录备份；
3. 将 staging 移为正式目录；
4. 成功后删除备份；
5. 替换失败时恢复备份。

任何 Git 或导出失败发生在替换前，现有正式语料保持不变。

## 7. 联合索引语义

- 继续使用单一 Collection `learning_notes`，满足“与原小语料合并”；
- Chunk `source` 保留完整相对路径，外部来源以 `corpus/self-llm/docs/` 开头；
- 当前分块参数、Embedding 模型、检索阈值和 Agent 工具接口不在本次修改范围；
- v0.5 索引 Manifest 会同时记录原 `docs/` 和外部语料的文件哈希与 chunk 数；
- 默认检索评测仍从冻结语料建立临时索引，防止外部仓库更新污染历史基线。

## 8. 测试

严格 TDD，覆盖：

- 反斜杠、非法字符、尾随点/空格、Windows 保留名；
- 大小写不敏感冲突的稳定消歧；
- 仅导出 `.md`，忽略 PNG、Python、Notebook 和数据文件；
- Git 原始路径到规范路径的 Manifest 映射；
- 相同输入产生相同 Manifest fingerprint；
- 导出失败不替换已有目标；
- 多源目录发现顺序稳定，且原 `docs/` 与 self-llm 均进入同一 rebuild；
- 冻结评测单目录调用保持兼容；
- 最终运行后端完整测试。

真实导入验收固定到首次版本，验证：

```text
commit_sha = 42c1bff4334f4c21c33e5791f29e9cdca5d47c61
Markdown 文件数 = 284
非 Markdown 文件不会出现在 docs/
非法反斜杠路径已规范化
联合索引 Manifest 同时包含 docs/ 与 corpus/self-llm/docs/
```

## 9. 非目标

本次不做：

- 图片 OCR 或多模态索引；
- Notebook/Python 转 Markdown；
- Markdown 内容清洗、去重或重写；
- 中文 BM25 分词优化；
- Chunk 代码块感知重构；
- 检索阈值重标和新语料问答集。

这些工作必须在语料导入与联合索引稳定后单独评估，避免扩大当前变更范围。