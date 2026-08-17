# AGENTS.md (xl-pdf)

Node 项目：用 playwright-core + 系统 Edge 把 RAG 教程网页批量转 PDF。

## 要点

- 直接依赖系统 Edge 的 `executablePath`，不要改成自行下载浏览器
- 唯一依赖是 `playwright-core`，不引入额外运行时
- `pdfs/`、`test.pdf`、`node_modules/` 均为生成物/依赖，不入库（见项目 .gitignore）
- 章节清单在 `download.js` 的 `chapters` 数组里，加章节就改那里

## 运行 / 验证

```powershell
npm install      # 首次或换机
node download.js # 跑全量下载，看结尾 OK/FAIL 汇总
```