# Knowledge Document Import

Date: 2026-08-25

## Overview

在前端设置面板中新增「文档库」,用户可上传 PDF / Markdown 文件。
文件经解析、切块、向量化后进入一个**独立的持久化 RAG 集合**,供 Agent 检索。
要求:重复文件不重复入库、同名文件按版本替换、可删除、可重试、进程重启后不丢件。

本文件是 Phase 3~7 的可执行任务书。执行者应从 `docs/main-quest-progress.md`
的「知识库文档导入」小节进入,顺着指针读到本文件。

---

## 最高优先级红线(先读这一条)

**用户上传的文档必须写入独立 Chroma 集合 `user_documents`。
绝对不允许写入 `learning_notes`,也不允许写入 `knowledge`。**

原因:`scripts/build_knowledge_index.py` 会调用
`KnowledgeRepository.rebuild()`,而 `rebuild()` 的实现是
**删除整个 collection 后重建**。共用集合等于埋了一颗定时炸弹——
任何人跑一次离线索引重建,用户上传的全部文档就没了。

踩了这条线,后果是整个索引需要重建,且用户数据不可恢复。

---

## 当前进度

| Phase | 状态 | 产出 |
|---|---|---|
| Phase 1 | ✅ 已完成 | `app/services/documents/pdf_markdown_converter.py` —— PDF 解析结果转带标题推断与页码哨兵的伪 Markdown |
| Phase 1.5 | ✅ 已完成 | 修复罗马数字误删、空页哨兵、标题页码归属三个缺陷(35 passed) |
| Phase 2 | ✅ 已完成 | `0005_knowledge_documents` 迁移 + `knowledge_document_repository.py`(8 passed) |
| Phase 2.5 | ✅ 已完成 | 0005 已在 MySQL 契约库验证,契约测试补充新表 collation 断言(10 passed) |
| Phase 3 | ⬜ 待办 | user_documents 独立向量集合 Repository |
| Phase 4 | ⬜ 待办 | 摄入编排 Service(状态机 + 三层去重 + 补偿删除) |
| Phase 5 | ⬜ 待办 | API 路由 + 启动恢复 |
| Phase 6 | ⬜ 待办 | 检索接入(feature flag + 多集合融合) |
| Phase 7 | ⬜ 待办 | 前端文档库面板 |

---

## 执行模式

按 Phase 3 → 4 → 5 → 6 → 7 顺序连续执行,**不需要在每个 Phase 前等待人工确认**。

每完成一个 Phase,立即运行该 Phase 指定的**专项测试命令**,全绿后进入下一个。
**任何一个 Phase 的专项测试没有全绿,立刻停止,不要继续往下做**,
并说明卡在哪一步、报错原文、你尝试过什么。

**不要运行 `pytest tests -q` 全量测试**(耗时太长)。只运行每个 Phase 指定的文件。
全量测试由人工在最后统一执行。

每个 Phase 完成后,在 `docs/main-quest-progress.md` 对应条目打勾。

---

## 已拍板的架构决策(不要提替代方案,直接执行)

1. **PDF 与 Markdown 共用一条切块链路**。PDF 先转伪 Markdown(Phase 1 已完成),
   再喂 `chunk_markdown`。目的是让 PDF 也拿到 `title_path` 这个检索强特征,
   并且全库只有一套切块粒度(512/50),避免大小块在同一索引里检索失衡。
2. **独立 Chroma 集合 `user_documents`**。理由见上方最高优先级红线。
3. **独立表 `knowledge_documents`**,不复用 `documents` 表。
   理由:去重唯一索引语义冲突——临时附件允许同一文件在不同 session 共存,
   知识库不允许;共表则该唯一索引无法表达(MySQL 无部分索引)。
4. **去重作用域为用户级**(`user_id`)。当前系统只有单用户,不要做多租户抽象。
5. **去重分三层**:L1 文件字节 sha256 / L2 提取正文 sha256 / L3 chunk 文本 sha256。
6. **同名文件重传是版本更新,不是重复**:先删旧向量,再软删旧元数据。

---

## 全程红线(违反任意一条即判定失败)

- 不修改 `app/repositories/knowledge_repository.py`、
  `app/services/knowledge_index_builder.py`、`scripts/build_knowledge_index.py`。
- 不修改 `app/services/documents/attachment_chunker.py`、
  `app/repositories/attachment_vector_repository.py` 的现有行为
  (临时附件链路必须逐字节保持原样)。
- 不在 `app/services/knowledge_chunker.py` 里加任何 PDF 专用分支。
  PDF 的特殊处理已经全部在 `pdf_markdown_converter.py` 里做完。
- 不引入 Celery / Redis / 消息队列。后台任务继续用 FastAPI `BackgroundTasks`,
  持久性问题用「启动时重扫」解决。
- 不做 OCR、不做双栏版面还原、不做表格结构还原、不做语义近重复去重。
- 不重构现有导航结构、不引入新的前端 UI 库。
- **不碰 `app/repositories/public_jd_repository.py`**(它的 `ON CONFLICT`
  是已知技术债,与本功能无关,现在改只会让 diff 变脏)。
- **不改 `_now()` 的返回格式**。新代码必须与 `workspace_asset_repository.py`
  保持一致,返回 `datetime.now(timezone.utc).isoformat()`。
  这个格式在割接 MySQL 时确实要改,但要全库一起改;
  现在只改新表会造成同一代码库两种时间戳风格,比不改更糟。

---

## Phase 3 —— user_documents 独立向量集合

### 具体方法

#### 3.1 配置(只追加,不改任何现有值)

在 `app/services/rag_settings.py` 末尾追加:

```python
# 用户上传文档的独立集合。与 learning_notes 物理隔离,
# 因为 build_knowledge_index.py 的 rebuild() 会删除整个 collection。
USER_DOCUMENT_COLLECTION_NAME = "user_documents"
USER_DOCUMENT_SIMILARITY_THRESHOLD = 0.45
# Phase 6 才打开。关闭时 search_learning_notes 行为与现在完全一致。
ENABLE_USER_DOCUMENT_RETRIEVAL = False
```

#### 3.2 新建 `app/repositories/user_document_vector_repository.py`

类结构照抄 `app/repositories/attachment_vector_repository.py`:
构造函数注入 client、`_get_or_create_collection()`、
`_get_collection()` 配 `NotFoundError` 兜底、`metadata={"hnsw:space": "cosine"}`、
按 `EMBEDDING_BATCH_SIZE` 分批写入。

**必须去掉**:`session_id`、`expires_at`、`_normalize_utc_iso` 及所有 TTL 逻辑。
**必须加上**:`title_path`、`page_start`、`page_end`、`version_no`。

#### 3.3 数据类

```python
@dataclass(frozen=True, slots=True)
class UserDocumentHit:
    chunk_id: str
    document_id: str
    content: str
    source: str              # original_filename
    title_path: str
    chunk_index: int
    page_start: int | None
    page_end: int | None
    similarity: float
```

#### 3.4 方法

```python
upsert_document_chunks(*, document_id, user_id, original_filename, version_no,
                       chunks: list[KnowledgeChunk],
                       page_ranges: list[tuple[int | None, int | None]],
                       embeddings: list[list[float]]) -> int
search(query_embedding, user_id, top_k, document_ids=None) -> list[UserDocumentHit]
delete_document(document_id) -> None
count_document(document_id) -> int
count() -> int
list_entries(include_embeddings: bool = False) -> list[KnowledgeEntry]
```

#### 3.5 四条硬性要求

1. **chunk_id 必须自己构造成 `f"{document_id}#{chunk_index}"`,
   绝对不要用 `chunk.chunk_id`。**
   `KnowledgeChunk.chunk_id` 这个 property 返回的是 `f"{source}#{chunk_index}"`,
   而 `source` 是原始文件名。同名文件的 v1 和 v2 会生成**完全相同的 ID**,
   版本切换时新版会覆盖旧版、旧版删除时会连带删掉新版。
   这是本 Phase 最容易踩的坑,务必用 `document_id`(uuid)而非文件名。

2. `upsert_document_chunks` 的**第一件事**必须是
   `collection.delete(where={"document_id": document_id})`。
   原因:重试后 chunk 数量可能变少,残留的尾部 chunk 会变成幽灵数据。
   `AttachmentVectorRepository` 里有同样的注释,照抄那个思路并保留注释。

3. `list_entries` 的返回类型必须是
   `app/repositories/knowledge_repository.py` 里已有的 `KnowledgeEntry`,
   不要自己定义一个同名的。这样 Phase 6 能把本 repository 直接传进现成的
   `hybrid_search(repository=...)`,不需要写适配层。

4. `PROJECT_ROOT` 与持久化路径的取法照抄 `attachment_vector_repository.py`
   顶部的写法(`Path(__file__).resolve().parents[2]` + `CHROMA_PERSIST_DIR`),
   不要自己算相对路径。

#### 3.6 参数校验

- `len(chunks) != len(embeddings)` 或 `len(chunks) != len(page_ranges)` → 抛 `ValueError`
- `chunks` 为空 → 直接返回 0,不建集合
- `user_id` 空串或纯空白 → 抛 `ValueError`
- `page_start` / `page_end` 为 None 时,metadata 里**不写这两个键**
  (Chroma 不接受 None 值),读取时用 `metadata.get(...)` 兜底成 None

### 输出要求

- 一个新文件 `app/repositories/user_document_vector_repository.py`
- `rag_settings.py` 末尾追加三个常量
- **不改其他任何文件**。特别是本 Phase 不要修改 `search_learning_notes.py`

### 验收标准

1. 写入后能按 `user_id` 检索到,换一个 `user_id` 检索不到
2. 同一 document_id 重复 upsert 不产生重复 id
3. 第二次 upsert 的 chunk 数量少于第一次时,多余的尾部 chunk 被清除
4. `delete_document` 后 `count_document` 返回 0
5. 两个不同 document_id、但 `original_filename` 相同的文档,
   写入后互不覆盖(这条验证第 3.5.1 条硬性要求)
6. `list_entries` 返回的对象类型是 `KnowledgeEntry`

### 测试要求(专项)

新建 `tests/test_user_document_vector_repository.py`,用 `chromadb.EphemeralClient()` 注入。

1. `test_upsert_then_search_returns_hit`
2. `test_search_filters_by_user_id`
3. `test_deterministic_chunk_ids_are_idempotent` —— 连续 upsert 两次,`count()` 不变
4. `test_retry_with_fewer_chunks_removes_stale_tail` —— 先写 5 块再写 3 块,
   断言 `count_document == 3`
5. `test_same_filename_different_document_ids_do_not_collide` ——
   **对应硬性要求 1**。两个 document_id 用同一个 `original_filename`,
   各写 3 块,断言 `count() == 6` 且删除其中一个后另一个仍是 3 块
6. `test_delete_document_clears_all_chunks`
7. `test_page_range_none_is_tolerated` —— page_ranges 传 `(None, None)` 不报错,
   检索回来 `page_start is None`
8. `test_list_entries_returns_knowledge_entry_type` ——
   `assert isinstance(entries[0], KnowledgeEntry)`
9. `test_length_mismatch_raises_value_error`

**运行命令**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_user_document_vector_repository.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_attachment_vector_repository.py -q
```

第二条是回归护栏,确认你没有改到临时附件的向量库。

---

## Phase 4 —— 摄入编排 Service

这是整个功能的核心,也是最容易写错的一个 Phase。**请逐条对照实现,不要凭印象**。

### 具体方法

#### 4.1 新建

- 目录 `app/services/knowledge_docs/`(与临时附件的 `app/services/documents/` 划清边界)
- `app/services/knowledge_docs/__init__.py`
- `app/services/knowledge_docs/storage.py`
- `app/services/knowledge_docs/ingestion_service.py`

#### 4.2 storage.py

照抄 `app/services/workspaces/storage.py` 的 `stage_upload` 思路:
边写盘边用 `hashlib.sha256()` 增量更新,返回 `(storage_key, size_bytes, file_sha256)`。
落盘根目录取自 `StorageConfig.from_env()`,新增子目录 `knowledge_docs/`。

必须实现:

- 文件名安全校验(拒绝路径穿越、控制字符),照抄现有 `InvalidWorkspaceFilename` 的检查逻辑
- 扩展名白名单:只放行 `.pdf` `.md` `.markdown`,其余抛 `UnsupportedKnowledgeDocumentType`
- 单文件大小上限 50MB,超出抛 `KnowledgeDocumentTooLarge`
- `delete(storage_key)` 方法,供去重命中和失败清理时删除已落盘文件

#### 4.3 ingestion_service.py 主流程

错误处理骨架照抄 `app/services/documents/attachment_indexing_service.py`:
每一步失败都调 `_mark_failed(document_id, error_code, message, cause=exc)`;
**向量写入成功之后**的任何失败,都必须先 `_compensate_vectors(document_id)` 再标 FAILED。

```
第 1 步  落盘,得到 (storage_key, size_bytes, file_sha256)

第 2 步  【L1 去重】get_active_by_file_hash(user_id, file_sha256)
         命中 → storage.delete(刚落盘的 key)
              → 返回 (已有记录, duplicate=True),流程结束
         注意:这一步不创建任何新记录,也不改动已有记录

第 3 步  【版本判定】get_latest_by_filename(user_id, original_filename)
         命中且未被软删 → version_no = 旧版.version_no + 1,记下 old_document_id
         未命中 → version_no = 1,old_document_id = None

第 4 步  insert_uploaded(...)  status=UPLOADED
         捕获 IntegrityError → 再查一次 L1,查到就按第 2 步处理,查不到才向上抛

第 5 步  CAS 推进 → PARSING
         .pdf:  PdfParser().parse(路径, document_id, filename,
                                  max_pages / min_extracted_chars 取自配置)
                → parsed_pdf_to_markdown(parsed)         [Phase 1 的函数]
                → parser_name = PdfParser.name, parser_version = PdfParser.version
                → page_count = parsed.page_count
                PdfParsingError 的各子类分别映射到自己的 error_code
                (直接用 exc.error_code 属性,PdfParser 已经定义好了)
         .md / .markdown:
                → 读取文件字节,按 UTF-8 解码(errors="strict")
                → UnicodeDecodeError → FAILED / INVALID_ENCODING
                → parser_name = "markdown", parser_version = "1", page_count = None

第 6 步  text_sha256 = sha256( re.sub(r"\s+", "", text) 的 UTF-8 字节 ).hexdigest()
         【L2 去重】get_active_by_text_hash(user_id, text_sha256)
         命中 且 命中记录的 id != old_document_id 时:
             → _mark_failed(DUPLICATE_CONTENT,
                            f"内容与《{命中记录.original_filename}》重复")
             → storage.delete(storage_key)
             → 流程结束
         ★★ 这一步必须在 embedding 之前。它的全部价值就是省掉 embedding 调用。
            如果写到 embedding 之后,本 Phase 判定失败。

第 7 步  update_parse_result(text_sha256, page_count, parser_name, parser_version)

第 8 步  CAS 推进 → CHUNKING
         chunks = chunk_markdown(text, source=original_filename)
         逐块处理:
            body, ps, pe = strip_page_sentinels(chunk.content)
            若 ps is None → ps = pe = 上一个块的 page_end(第一个块则为 None)
            若 body.strip() == "" → 丢弃该块(纯哨兵块,必须过滤)
            用 body 替换 chunk.content(KnowledgeChunk 是 frozen dataclass,
            用 dataclasses.replace 重建)
         【L3 去重】同一文档内 body 的 sha256 完全相同的块,只保留第一个
         过滤和去重之后重新编号 chunk_index,从 0 连续递增
         (因为 chunk_id 依赖 chunk_index,不能有空洞)
         chunks 为空 → FAILED / NO_EXTRACTABLE_TEXT

第 9 步  CAS 推进 → EMBEDDING
         按 EMBEDDING_BATCH_SIZE 分批调 EmbeddingClient().embed_texts([...])
         每批校验返回条数 == 请求条数,不等则抛 EmbeddingError
         (照抄 attachment_indexing_service 里那段校验)
         失败 → FAILED / EMBEDDING_FAILED

第 10 步 vector_repo.upsert_document_chunks(...)
         失败 → _compensate_vectors + FAILED / VECTOR_INDEX_FAILED

第 11 步 【版本切换】old_document_id 不为 None 时:
         (a) vector_repo.delete_document(old_document_id)
         (b) repo.soft_delete(old_document_id)
         顺序不能反。先删向量再删元数据,中途崩了还能靠元数据重试;
         反过来则元数据没了、向量还在,变成永远清不掉的幽灵数据。

第 12 步 update_chunk_count(len(chunks)) → CAS 推进 → READY
         READY 更新失败 → _compensate_vectors + FAILED / VECTOR_INDEX_FAILED
```

#### 4.4 依赖注入

构造函数接受 `repository`、`vector_repository`、`embedding_client`、`storage`、`pdf_parser`
五个可选参数,默认值为各自的真实实现。这样测试能全部替换成 fake,不碰真实 API 和磁盘。

#### 4.5 CAS 推进

每一步状态推进都调 `update_status(id, 新状态, expected_status=当前状态)`。
返回 `None` 说明有并发已经推进过,**直接 return,不要报错**。

### 输出要求

- 三个新文件
- 公开入口只有两个:
  - `ingest_document(user_id, original_filename, media_type, file_stream) -> tuple[Record, bool]`
  - `reprocess_document(document_id) -> Record`(供重试和启动恢复复用)
- 每个 `error_code` 都要是大写下划线常量,集中定义在模块顶部,不要散落成字符串字面量

### 验收标准

1. PDF 和 MD 两条路都能走到 READY
2. L1 命中时不产生新记录、不调用 embedding、落盘文件被清理
3. L2 命中时 **embedding 一次都没被调用**
4. 同名重传后:新记录 version_no=2 且 READY,旧记录 status=DELETED 且 dedupe_key 为 NULL,
   旧向量在集合中 count 为 0
5. embedding 抛异常后,向量集合里没有该 document_id 的任何残留
6. 纯哨兵块被过滤,且过滤后 chunk_index 连续无空洞

### 测试要求(专项)

新建 `tests/test_knowledge_ingestion_service.py`。
外部依赖全部用 fake:`FakeEmbeddingClient`(记录调用次数)、
`FakeVectorRepository`(内存 dict)、临时目录做 storage、真实 SQLite repository。

1. `test_markdown_happy_path_reaches_ready`
2. `test_pdf_happy_path_reaches_ready` —— 用手工构造的 `ParsedDocument` + fake parser
3. `test_l1_duplicate_returns_existing_without_new_record` ——
   断言记录总数没变 **且** `fake_embedding.call_count == 0`
4. `test_l2_duplicate_content_skips_embedding` ——
   **断言 `fake_embedding.call_count == 0`**,status 为 FAILED,error_code 为 DUPLICATE_CONTENT
5. `test_same_filename_creates_version_two_and_removes_old_vectors` ——
   断言新记录 version_no==2、旧记录 status==DELETED 且 dedupe_key is None、
   `fake_vector.count_document(old_id) == 0`
6. `test_embedding_failure_leaves_no_vector_residue`
7. `test_ready_update_failure_triggers_compensation` ——
   monkeypatch 让最后一次 update_status 返回 None,断言向量被补偿删除
8. `test_sentinel_only_chunks_are_dropped_and_indices_are_contiguous` ——
   断言写入向量库的 chunk_index 是 `list(range(n))`
9. `test_invalid_utf8_markdown_fails_with_invalid_encoding`

**运行命令**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_ingestion_service.py -q
```

---

## Phase 5 —— API 路由 + 启动恢复

### 具体方法

#### 5.1 新建

- `app/schemas/knowledge_documents.py`
- `app/api/routes/knowledge_documents.py`
- `app/services/knowledge_docs/recovery_service.py`

#### 5.2 路由(前缀 `/knowledge`,在 `app/main.py` 注册)

| 方法 | 路径 | 成功码 | 说明 |
|---|---|---|---|
| POST | `/knowledge/documents` | 202 新建 / **200 重复** | 表单字段 `user_id` + `file` |
| GET | `/knowledge/documents` | 200 | query: `user_id` 必填,`status`、`limit`(1~100,默认 50) |
| GET | `/knowledge/documents/{id}` | 200 | 前端轮询状态用 |
| POST | `/knowledge/documents/{id}/retry` | 202 | CAS 抢占后重新入队 |
| DELETE | `/knowledge/documents/{id}` | 200 | 返回删除后的记录 |

- 响应体统一 `KnowledgeDocumentItem`,字段与 `KnowledgeDocumentRecord` 一一对应,
  外加 `user_safe_message: str | None`——把 error_code 映射成中文可读提示,
  映射表照抄 `app/api/routes/attachments.py` 里 `_user_safe_message` 的写法
- 上传响应体是 `KnowledgeDocumentUploadResponse { document, duplicate: bool }`,
  形状照抄 `WorkspaceAssetUploadResponse`
- 身份继续用现有的 `user_id` query/form 桥接,**不要引入任何新鉴权机制**
- 错误映射照抄 `app/api/routes/workspace_assets.py` 的 `_error(code, message, extra)` 风格
- POST 成功后用 `background_tasks.add_task(...)` 触发摄入;`duplicate=True` 时**不入队**

#### 5.3 DELETE 的四步级联(最容易漏,重点写)

```
1. update_status(id, DELETING, expected_status 为 READY 或 FAILED)
   —— 两种 expected 各试一次,都失败说明状态不允许删,返回 409
2. vector_repository.delete_document(id)
   —— 漏这步会留下幽灵向量,检索能搜出已删除的文档
3. storage.delete(record.storage_key)
4. repository.soft_delete(id)
```

任何一步抛异常,**都停在 DELETING 状态并向上抛 500**,由启动恢复重试。
**绝对不要 try/except 吞掉异常然后直接标 DELETED。**

#### 5.4 recovery_service.py

提供 `recover_pending_documents(limit: int = 100) -> dict[str, int]`,
在 `app/main.py` 的 lifespan startup 阶段调用
(现有 lifespan 写法参考 `tests/test_main_lifespan.py`)。

```
records = repository.list_non_terminal(limit)
for record in records:
    若 status == DELETING → 重跑 DELETE 的第 2~4 步
    否则(UPLOADED/PARSING/CHUNKING/EMBEDDING)→ 调 reprocess_document(record.id)
返回 {"requeued": n1, "deleted": n2, "failed": n3}
```

单条失败必须 try/except 记 log 后继续处理下一条,
**不能让一条坏记录阻断整个启动**。

在 docstring 里写明理由:`BackgroundTasks` 不跨进程重启持久
(`app/api/routes/attachments.py` 已有同样注释)。
临时附件丢了有 TTL 兜底,知识库文档丢了会永久卡在非终态,所以必须补这一层。

### 输出要求

- 三个新文件 + `app/main.py` 两处改动(注册 router、startup 调 recovery)
- `app/main.py` 的改动必须最小化,不要重构现有 lifespan 结构

### 验收标准

1. 上传新文件返回 202,同一文件再传返回 200 且 `duplicate: true`
2. 删除后:向量库 `count_document` 为 0、物理文件不存在、记录 status 为 DELETED
3. 删除过程中向量删除失败时,状态停在 DELETING(不是 DELETED,也不是 READY)
4. 启动恢复能把卡在 PARSING 的记录重新推进到 READY
5. `/docs` 里能看到 5 个端点

### 测试要求(专项)

新建 `tests/test_knowledge_documents_api.py`,用 FastAPI `TestClient` + fake embedding/vector:

1. `test_upload_returns_202_and_enqueues`
2. `test_duplicate_upload_returns_200_with_duplicate_flag`
3. `test_list_filters_by_status_and_respects_limit`
4. `test_get_single_document_returns_user_safe_message_on_failure`
5. `test_delete_cascades_to_vectors_and_storage`
6. `test_delete_stops_at_deleting_when_vector_delete_fails` ——
   monkeypatch `delete_document` 抛异常,断言 HTTP 500 **且** 数据库里 status == 'DELETING'
7. `test_retry_uses_cas_and_rejects_when_already_processing` —— 并发重试第二次返回 409
8. `test_unsupported_extension_returns_415`

新建 `tests/test_knowledge_recovery_service.py`:

9. `test_recovery_requeues_stuck_parsing_document`
10. `test_recovery_completes_stuck_deleting_document`
11. `test_recovery_continues_after_single_record_failure` ——
    三条记录,中间一条抛异常,断言另外两条仍被处理

**运行命令**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_documents_api.py tests/test_knowledge_recovery_service.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_main_lifespan.py -q
```

第二条是回归护栏,确认你改 `main.py` 没破坏现有启动流程。

---

## Phase 6 —— 接入检索链路(风险最高的一个 Phase)

### 具体方法

#### 6.1 只改这两个文件

- `app/services/rag_settings.py`:把 `ENABLE_USER_DOCUMENT_RETRIEVAL` 改为 `True`
- `app/services/agent/tools/search_learning_notes.py`:扩展 `_retrieve_hits`

**不要新建检索工具**。用户不应该需要记住「该用哪个工具查我上传的文档」。

#### 6.2 实现顺序(必须按这个顺序,否则你无法证明没破坏主链路)

1. **先**在 `tests/test_user_document_retrieval.py` 里写「flag 关闭时行为不变」的测试并跑通
2. **再**动 `_retrieve_hits` 的代码
3. **最后**把 flag 改成 True

#### 6.3 `_retrieve_hits` 的扩展

当 `ENABLE_USER_DOCUMENT_RETRIEVAL` 为 True 时,并行查两路,各取 `top_k`,融合后截断。
融合方式**照抄** `app/services/shard_router.py` 的 `_broadcast`:

```python
with ThreadPoolExecutor(max_workers=2) as executor:
    futures = [executor.submit(查笔记), executor.submit(查用户文档)]
    for future in as_completed(futures):
        results.extend(future.result())
return sorted(
    results,
    key=lambda hit: (-hit.similarity, hit.source, hit.title_path, hit.content),
)[:top_k]
```

**排序 key 一个字符都不要改**。这个 key 保证了评测结果可复现,
改了之后 `run_retrieval_eval.py` 的历史基线就没有可比性了。

#### 6.4 五条硬性要求

1. **flag 关闭时,`_retrieve_hits` 的行为必须与现在逐字节一致**,
   并且**不能对 user_documents 集合发起任何查询**(测试要断言这一点)
2. 两路的相似度都是 cosine、同一个 embedding 模型,可以直接比较。
   **不要再加归一化层**,加了只会引入不可解释的偏移
3. user_documents 那一路也要能走 hybrid:因为 Phase 3 的 `list_entries` 返回
   `KnowledgeEntry`,直接
   `hybrid_search(repository=user_doc_repo, query=..., query_embedding=...,
   top_k=..., fingerprint=f"userdocs:{user_doc_repo.count()}")` 即可。
   **在这行上方写注释**:这是弱指纹,文档数不变但内容变了不会触发 BM25 重建,
   单用户场景可接受,已记入技术债
4. 任一路抛异常时,另一路的结果仍要正常返回。
   容错写法照抄 `shard_router._safe_search_shard`
   (try/except + logger.warning + 返回空列表)
5. `UserDocumentHit` 需要转成 `KnowledgeHit` 才能进融合列表。
   写一个 `_hit_from_user_document(hit) -> KnowledgeHit`,
   `source` 用 `original_filename`,`title_path` 直接透传

#### 6.5 输出增强

`_item_from_hit` 里为来自 user_documents 的命中额外输出两个字段:

- `doc_type: "user_upload"`
- `page_range`:有页码时形如 `"p.12"` 或 `"p.12-13"`,无页码时不输出该键

笔记那一路**保持原样,不加任何字段**——现有 ReAct trace 解析和评测脚本依赖当前形状。
实现上给 `_item_from_hit` 加一个 `extra: dict | None = None` 可选参数,默认 None 时行为不变。

#### 6.6 观测

`trace_db.save_retrieval_event` 的 `collection` 参数,
flag 打开时传 `"notes+userdocs"`,关闭时仍传 `"notes"`。这样后续能按来源拆 P95。

### 输出要求

- 只改上述两个文件 + 新增一个测试文件
- 不改 `hybrid_retriever.py`、不改 `shard_router.py`、不改 `reranking.py`

### 验收标准

1. flag=False 时,`test_search_learning_notes_hybrid.py` 和
   `test_knowledge_search.py` 全绿,且断言 user_documents 未被查询
2. flag=True 且两路都有数据时,结果按 similarity 正确交错
3. flag=True 但 user_documents 为空集合时,不报错,退化为纯笔记检索
4. 一路抛异常时另一路结果仍返回
5. **`run_retrieval_eval.py` 的指标不低于当前基线。**
   若下降,先把 flag 改回 False 保住主链路,再排查——
   **不要通过调 `SIMILARITY_THRESHOLD` 来让指标好看**。
   那个 0.45 是在纯笔记语料上校准的,混入 PDF 语料后分布会漂,
   这是阈值需要重新校准的信号,不是可以随手改的旋钮

### 测试要求(专项)

新建 `tests/test_user_document_retrieval.py`:

1. `test_flag_off_does_not_query_user_documents` ——
   用 spy 断言 user_doc_repo.search **调用次数为 0**
2. `test_flag_on_merges_and_sorts_by_similarity`
3. `test_flag_on_with_empty_user_collection_degrades_gracefully`
4. `test_notes_branch_failure_still_returns_user_document_hits`
5. `test_user_document_branch_failure_still_returns_note_hits`
6. `test_user_upload_items_carry_doc_type_and_page_range`
7. `test_note_items_shape_is_unchanged` —— 用
   `assert set(item.keys()) == {...}` 精确断言笔记命中的 key 集合与 flag 关闭时一致

**运行命令**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_user_document_retrieval.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_search_learning_notes_hybrid.py tests/test_search_learning_notes_reranking.py tests/test_knowledge_search.py tests/test_hybrid_retriever.py -q
```

第二条是本轮最重要的回归护栏,四个文件必须全绿。

两条测试都全绿之后再跑评测:

```powershell
.\.venv\Scripts\python.exe scripts\run_retrieval_eval.py
```

把评测输出的关键指标数字**原样贴进回复里**,并与 `reports/` 下的历史结果对比。

---

## Phase 7 —— 前端文档库面板

### 具体方法

#### 7.1 新建

- `frontend/src/components/KnowledgeLibrary.jsx`
- `frontend/src/components/KnowledgeLibrary.test.jsx`
- 在 `frontend/src/api/` 下追加请求方法(文件位置和风格跟随现有 api 模块)

#### 7.2 结构模板

照抄 `frontend/src/components/workspaces/WorkspaceAssets.jsx`:
上传区 + 列表 + 状态徽标 + 删除确认。
样式复用 `frontend/src/styles` 下现有的类,
**不要引入新 UI 库,不要写内联大段样式**。

#### 7.3 功能清单

1. **上传**:点击选择 + 拖拽。前端先校验扩展名(`.pdf` `.md` `.markdown`)和大小(50MB),
   不合格直接本地提示,不发请求
2. **列表**:文件名、大小、页数、chunk 数、状态徽标、上传时间、操作按钮。
   `version_no > 1` 时在文件名后显示 `v2` 这样的小标记
3. **状态轮询**:列表中存在非终态记录时,每 2 秒轮询一次 `GET /knowledge/documents`;
   全部进入终态(READY/FAILED/DELETED)后停止。
   **组件卸载时必须 `clearInterval`**,在 `useEffect` 的 cleanup 里做
4. **重复上传**:HTTP 200 且 `duplicate: true` → 中性提示「该文件已在文档库中」。
   **不要用红色错误样式**,这不是错误
5. **失败态**:显示 `user_safe_message`,并提供「重试」按钮调 retry 端点
6. **同名确认**:上传前若列表中已有同名文件,先弹确认框
   「文档库中已有同名文件《xxx》,继续上传将替换旧版本」,确认后才发请求
7. **删除确认**:二次确认后才发 DELETE

#### 7.4 入口

挂在现有设置区域。如果当前没有独立设置面板,
就在 `App.jsx` 的侧边栏加一个「文档库」入口。
**只加入口,不要顺手重构导航结构。**

### 输出要求

- 两个新组件文件 + api 模块追加 + `App.jsx` 最小改动
- 组件必须是受控的函数组件,状态用 `useState`/`useEffect`,不引入状态管理库
- 所有用户可见文案用中文

### 验收标准

1. 上传成功后列表自动刷新,新记录出现且状态在 2 秒内开始变化
2. 重复上传显示中性提示,列表不新增行
3. FAILED 记录显示中文错误信息和重试按钮
4. 组件卸载后没有残留定时器(测试要断言)
5. `npm run build` 和 `npm run lint` 都通过,无新增警告

### 测试要求(专项)

`frontend/src/components/KnowledgeLibrary.test.jsx`,用 vitest + testing-library,fetch 用 mock:

1. 上传成功后列表刷新
2. duplicate 响应显示中性提示且列表行数不变
3. FAILED 记录显示 user_safe_message 和重试按钮
4. 点击重试调用 retry 端点
5. 同名文件上传前弹出确认框
6. 卸载时清除轮询定时器 —— 用 `vi.useFakeTimers()`,
   unmount 后再 `advanceTimersByTime(10000)`,断言 fetch 没有再被调用
7. 扩展名不合法时不发请求

**运行命令**

```powershell
cd frontend
npx vitest run src/components/KnowledgeLibrary.test.jsx
npm run build
npm run lint
```

---

## 全部完成后的收尾(必做)

### 1. 更新 `docs/main-quest-progress.md`

把「6. RAG 学习资料」那一行的状态从 TODO 改为 DONE,
并勾掉「设计学习资料导入方式」「文档切片并保存来源信息」
「为文档片段生成 embedding」「根据问题检索相关资料片段」「回答时附带引用来源」。

在「知识库文档导入」小节补一段:数据流概述、三层去重策略、独立集合的原因。

### 2. 技术债清单(原样写进文档,不要遗漏)

- PDF 双栏版面未处理,双栏论文的块顺序会左右串行
- 未提取真实字号,标题推断依赖 bbox 高度启发式
- 不支持扫描件(无文本层),依赖 `PdfParser` 的 `NO_EXTRACTABLE_TEXT` 拦截
- 未做语义近重复去重(仅精确 sha256)
- `DVD` 等合法罗马数字词仍会被当作页码删除
- user_documents 的 BM25 指纹是弱指纹(仅基于 chunk 总数)
- `BackgroundTasks` 单进程,多副本部署下并发入库无协调
- `SIMILARITY_THRESHOLD` 仍是纯笔记语料校准值,混入 PDF 后需重新扫描校准
- 解析预览确认流程未实现(需要「暂停在 CHUNKING 等待确认」的中间态)
- `public_jd_repository.py:61` 用 `ON CONFLICT ... DO UPDATE`(SQLite/PG 语法),
  MySQL 需改为 `ON DUPLICATE KEY UPDATE`
- 全库 `_now()` 返回 ISO 字符串(带 `T` 和 `+00:00`),
  MySQL `DATETIME(6)` 在严格模式下会拒绝,割接前需统一改为 `datetime` 对象
- 无 SQLite → MySQL 数据搬迁脚本(需按外键依赖排序 + 行数/内容校验)

### 3. 汇总输出

在回复中给出:每个 Phase 的专项测试通过情况、
`run_retrieval_eval.py` 的前后指标对比、以及你认为最需要人工复核的三个点。

### 4. 全量测试

**最后才**由人工执行,你不要跑:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```
