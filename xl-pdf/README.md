# xl-pdf — RAG 教程网页批量转 PDF

用 Playwright 驱动本机 Edge 浏览器，把 `xiaolinnote.com/ai/rag/` 的 20 章 RAG 教程网页批量打印成 PDF。

## 依赖（硬前提）

- Node ≥ 20（`playwright-core` 要求）
- 系统已装 **Microsoft Edge**（本机路径 `C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe`）
- 不打包浏览器，直接复用系统 Edge，`playwright-core` 已经 `npm install` 过（`node_modules/` 已忽略不入库）

## 运行

```powershell
node download.js   # 全部 20 章 → 输出到 pdfs/，结束打印 成功/失败 汇总
node test.js       # 探索：单页打印到 test.pdf
node list.js       # 探索：抓取目标页里的 /ai/rag/ 链接
```

`node_modules/` 丢了或换机器就再装一次：

```powershell
npm install
```

## 目录约定

- `pdfs/`、`test.pdf` 是生成物，已 gitignore，不入库
- 章节清单硬编码在 `download.js` 顶部的 `chapters` 数组
- 时间相关（如 `networkidle`、`waitForTimeout`）对慢页面可调，见 `download.js`