# Tutor Agent Frontend 主线任务进度表

这份文档是你的前端学习任务日志。它不是一次性读完的教程，而是用来边做边打勾、边联调边复盘的路线图。

项目主线：做出一个 **React + Vite 前端学习工作台**，连接当前 FastAPI 后端，验证 Tutor Agent 的对话能力。

学习主线：通过这个前端项目，理解浏览器页面、React 组件、状态管理、API 请求、CORS、错误处理、调试信息和前后端联调。

使用方式：

- 每完成一个任务，就把 `[ ]` 改成 `[x]`。
- 每个阶段都要先跑起来，再解释清楚，再进入下一阶段。
- 遇到报错时，不要急着跳过；把报错复制给 AI，让 AI 带你定位。
- 每个阶段结束后，至少写 3 句话复盘。
- 如果你无法解释自己刚写的前端代码，就不算真正完成。
- 不要一次性让 AI 把整个前端写完；按阶段推进。

通关原则：

- 能运行
- 能联调
- 能测试
- 能解释
- 能复盘

---

## 前端第一版定位

第一版前端不是营销页，也不是完整产品后台。

第一版前端是一个 **Tutor Agent 对话测试工作台**：

- 最终用途：给别人演示项目能力。
- 当前用途：和后端接上，测试接口是否正确。
- 界面形态：ChatGPT 式聊天界面。
- 技术栈：React + Vite。
- 项目位置：`frontend/`。
- 后端位置：继续使用当前 `app/` FastAPI 后端。
- 第一版重点：`GET /health`、`POST /chat` 和 `GET /conversations/{user_id}`。
- 历史记录：阶段 7 已接入，当前可以按 `user_id` 查看最近几条对话。

---

## 当前后端契约

前端第一版先只依赖当前已经存在或正在稳定中的接口。

### GET /health

用途：检测后端是否启动。

响应示例：

```json
{
  "status": "ok",
  "service": "tutor-agent-api"
}
```

前端用途：

- 页面打开时自动请求。
- 顶部显示 `API 在线`、`API 离线` 或 `连接中`。
- 提供一个刷新按钮，方便后端重启后重新检测。

### POST /chat

用途：发送用户问题，获取 Tutor Agent 的结构化回复。

请求示例：

```json
{
  "user_id": "default",
  "message": "FastAPI 的路由是什么？"
}
```

当前响应结构：

```json
{
  "user_id": "default",
  "message": "FastAPI 的路由是什么？",
  "reply": {
    "answer": "FastAPI 的路由可以理解为 URL 和 Python 函数之间的绑定。",
    "next_task": "写一个很小的 GET 接口。",
    "exercise": "请写一个 /hello 接口，让它返回一段 JSON。",
    "checkpoints": [
      "你能解释什么是路由",
      "你能写出一个 GET 接口",
      "你能在浏览器里测试接口"
    ]
  }
}
```

前端显示规则：

- `reply.answer` 显示为 AI 主回复。
- `reply.next_task` 显示为“下一步”。
- `reply.exercise` 显示为“小练习”。
- `reply.checkpoints` 显示为“检查点”列表。
- 每条 AI 回复下面放一个默认折叠的“调试详情”。

### 扩展接口：GET /conversations/{user_id}

后端已经提供历史查询接口。

前端用途：

- 在左侧历史面板里按当前 `user_id` 查询。
- 支持调整 `limit`，控制要读取的历史条数。
- 展示用户问题、AI 主回答、记录 id 和创建时间。
- 默认折叠“历史调试详情”，用于查看请求 URL、状态码和响应体。

---

## 总进度

- [x] 阶段 0：前端定位与环境准备
- [x] 阶段 1：创建并启动 React + Vite 项目
- [x] 阶段 2：理解前端文件结构与组件边界
- [x] 阶段 3：搭建静态 ChatGPT 式界面
- [x] 阶段 4：React 状态管理与本地消息流
- [ ] 阶段 5：连接后端 `/health` 与 CORS
- [x] 阶段 6：连接后端 `/chat` 与结构化 Tutor 回复
- [x] 阶段 7：查看用户历史记录
- [ ] 阶段 8：最终验收与复盘

---

## 建议文件结构

第一版建议使用下面的结构。真正开始写代码时，可以按阶段逐步创建，不需要第一天全部建完。

```text
frontend/
  package.json
  vite.config.js
  index.html
  src/
    main.jsx
    App.jsx
    api/
      tutorApi.js
    components/
      ApiStatus.jsx
      UserIdInput.jsx
      ChatMessage.jsx
      ChatInput.jsx
      DebugDetails.jsx
      ConversationHistory.jsx
    styles/
      app.css
```

文件职责说明：

- `frontend/package.json`：前端项目说明书，记录脚本和依赖。
- `frontend/vite.config.js`：Vite 配置文件，第一版可以保持默认。
- `frontend/index.html`：浏览器打开的 HTML 入口，React 会挂载到这里。
- `frontend/src/main.jsx`：React 应用挂载入口。
- `frontend/src/App.jsx`：页面主组件，负责组合整个界面。
- `frontend/src/api/tutorApi.js`：集中放请求后端 API 的函数，例如 `getHealth()` 和 `postChat()`。
- `frontend/src/components/ApiStatus.jsx`：顶部 API 在线状态组件。
- `frontend/src/components/UserIdInput.jsx`：顶部 `user_id` 输入组件。
- `frontend/src/components/ChatMessage.jsx`：单条聊天消息组件。
- `frontend/src/components/ChatInput.jsx`：底部输入框组件。
- `frontend/src/components/DebugDetails.jsx`：默认折叠的请求/响应调试详情组件。
- `frontend/src/components/ConversationHistory.jsx`：当前用户的历史记录面板。
- `frontend/src/styles/app.css`：页面样式文件。

---

## UI 布局说明

第一版页面直接进入可用的聊天工作台，不做 landing page。

页面结构：

```text
顶部栏
  项目名：Tutor Agent
  API 状态：连接中 / API 在线 / API 离线
  刷新状态按钮
  user_id 输入框

主聊天区
  用户消息靠右
  AI 消息靠左
  空状态显示示例问题
  加载中显示 AI 正在生成回复

AI 消息内容
  answer 主回复
  下一步 next_task
  小练习 exercise
  检查点 checkpoints
  调试详情按钮

底部输入区
  多行输入框
  发送按钮
  发送中禁用按钮
```

第一版 UI 原则：

- 页面要像聊天工具，不像 API 表单。
- 调试信息默认隐藏，需要时展开。
- `user_id` 要放在顶部，默认值是 `default`。
- 结构化 Tutor 信息要清楚，但不要抢走主回答的注意力。
- 错误提示要让新手看得懂，例如“后端没有启动”比“Failed to fetch”更友好。
- 不做登录、不做复杂动画、不做移动端优先设计。

---

## 常用 PowerShell 命令

启动后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

后端地址：

```text
http://127.0.0.1:8001
```

后端 API 文档：

```text
http://127.0.0.1:8001/docs
```

运行后端测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

创建前端项目：

```powershell
npm create vite@latest frontend -- --template react
```

进入前端目录：

```powershell
cd frontend
```

安装前端依赖：

```powershell
npm install
```

启动前端：

```powershell
npm run dev
```

前端默认地址：

```text
http://127.0.0.1:5173
```

如果 `5173` 已经被别的本地项目占用，可以临时使用：

```text
http://127.0.0.1:5174
```

---

## 阶段 0：前端定位与环境准备

阶段目标：先理解前端在这个项目里负责什么，再开始创建项目。

这一阶段不要急着写 React。重点是搞清楚：浏览器页面、前端开发服务器、后端 API、JSON 和 CORS 分别是什么。

### 你要学习

- [x] 前端和后端分别负责什么
- [x] 浏览器页面为什么不能直接等于后端 API
- [x] 什么是 Vite 开发服务器
- [x] 什么是 API base URL
- [x] 为什么前端和后端端口不同会遇到 CORS
- [x] 为什么第一版先做 `/health` 和 `/chat`
- [x] 为什么 `user_id` 暂时用输入框，而不是登录系统

### 主线任务

- [x] 确认前端目录使用 `frontend/`
- [x] 确认技术栈使用 React + Vite
- [x] 确认后端默认地址是 `http://127.0.0.1:8001`
- [x] 确认前端默认地址优先使用 `http://127.0.0.1:5173`，本机当前使用 `http://127.0.0.1:5174`
- [x] 确认第一版只接 `GET /health` 和 `POST /chat`
- [x] 确认历史接口留到阶段 7 扩展
- [x] 检查本机是否已经安装 Node.js 和 npm

### 关键命令提示

```powershell
node -v
npm -v
```

如果这两个命令不能正常输出版本号，先不要继续写前端，应该先解决 Node.js 环境。

### 交付物

- [x] 你知道前端项目会放在 `frontend/`
- [x] 你知道后端项目仍然在 `app/`
- [x] 你知道两个服务会同时运行
- [x] 你知道第一版前端要验证哪些 API

### 验收标准

- [x] 你能解释前端为什么需要单独的 `frontend/` 目录
- [x] 你能解释 `127.0.0.1:8001` 和 `127.0.0.1:5173` / `127.0.0.1:5174` 的区别
- [x] 你能说出第一版前端的三个核心功能
- [x] 你能说明为什么暂时不做登录和历史记录

### 阶段复盘

复盘记录：

```text
1. 前端负责浏览器里的交互界面，后端负责 API、模型调用和数据库。
2. 后端运行在 8001，前端默认会运行在 5173；如果 5173 被占用，当前项目可以临时运行在 5174。
3. 第一版前端先验证 API 状态和聊天主流程，历史记录留到聊天工作台跑通后扩展。
```

---

## 阶段 1：创建并启动 React + Vite 项目

阶段目标：创建最小 React 前端项目，并确认浏览器能打开 Vite 页面。

这一阶段只解决“前端能跑起来”。不要急着改成聊天界面，也不要急着连后端。

### 你要学习

- [x] 什么是 React
- [x] 什么是 Vite
- [x] `package.json` 是什么
- [x] `npm install` 做了什么
- [x] `npm run dev` 做了什么
- [x] 为什么前端也有自己的开发服务器

### 主线任务

- [x] 在项目根目录创建 `frontend/`
- [x] 使用 Vite 创建 React 项目
- [x] 进入 `frontend/`
- [x] 安装依赖
- [x] 启动前端开发服务器
- [x] 在浏览器打开 Vite 页面
- [x] 停止和重启一次前端服务

### 关键命令提示

```powershell
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm run dev
```

### 交付物

- [x] `frontend/package.json`
- [x] `frontend/index.html`
- [x] `frontend/src/main.jsx`
- [x] `frontend/src/App.jsx`
- [x] 前端页面可以在浏览器打开

### 验收标准

- [x] 你能启动前端服务
- [x] 你能说清楚 `npm install` 和 `npm run dev` 的区别
- [x] 你能解释为什么浏览器打开的是 Vite 地址
- [x] 你知道前端服务停止后页面为什么不能继续热更新

### 阶段复盘

复盘记录：

```text
1. React 项目已经创建在 frontend/，里面有自己的 package.json、依赖和 src 入口文件。
2. npm install 负责安装依赖，npm run dev 负责启动 Vite 开发服务器。
3. 本机 5173 端口被其他项目占用，所以当前 Tutor Agent 前端运行在 http://127.0.0.1:5174/。
```

---

## 阶段 2：理解前端文件结构与组件边界

阶段目标：清理默认模板，建立适合 Tutor Agent 的前端目录结构。

这一阶段的重点不是界面多漂亮，而是让你知道每个文件负责什么。文件边界清楚，以后 AI 才不容易乱改。

### 你要学习

- [x] `main.jsx` 的作用
- [x] `App.jsx` 的作用
- [x] 什么是 React 组件
- [x] 为什么组件要拆分
- [x] 为什么 API 请求要放进 `api/`
- [x] 为什么样式可以集中放进 `styles/`
- [x] 为什么清晰文件结构有利于 AI 协作

### 主线任务

- [x] 清理 Vite 默认示例内容
- [x] 创建 `src/api/`
- [x] 创建 `src/components/`
- [x] 创建 `src/styles/`
- [x] 创建或整理 `src/styles/app.css`
- [x] 在 `App.jsx` 中保留最小页面结构
- [x] 确认页面修改后浏览器会自动刷新

### 关键代码提示

`main.jsx` 的核心作用是把 React 应用挂载到 HTML 页面：

```jsx
createRoot(document.getElementById("root")).render(<App />)
```

这一阶段只需要理解它的作用，不需要频繁修改它。

### 交付物

- [x] `frontend/src/api/`
- [x] `frontend/src/components/`
- [x] `frontend/src/styles/`
- [x] `frontend/src/styles/app.css`
- [x] 清理后的 `App.jsx`

### 验收标准

- [x] 你能说清楚 `main.jsx` 和 `App.jsx` 的区别
- [x] 你能解释为什么不把所有代码都写在 `App.jsx`
- [x] 你能指出未来 API 请求应该写在哪个文件夹
- [x] 你能指出未来聊天消息组件应该写在哪个文件夹

### 阶段复盘

复盘记录：

```text
1. main.jsx 只负责把 React 应用挂载到 index.html 的 root 节点，平时不需要频繁修改。
2. App.jsx 现在只保留页面骨架，后续会把 API、聊天消息和输入区拆到单独目录里。
3. 默认 Vite 示例内容已经清理，样式集中到 src/styles/app.css，后面继续做静态聊天界面。
```

---

## 阶段 3：搭建静态 ChatGPT 式界面

阶段目标：先做一个静态聊天界面，不接 API，不写复杂状态。

这一阶段像画界面草图。先让页面长得像你想要的工作台，再让它动起来。

### 你要学习

- [x] 什么是静态 UI
- [x] 什么是组件 props
- [x] 为什么先做静态界面再接数据
- [x] 如何把一个页面拆成多个组件
- [x] 用户消息和 AI 消息为什么适合用同一个组件处理
- [x] Tutor Agent 的结构化回复如何展示

### 主线任务

- [x] 创建 `ApiStatus.jsx`
- [x] 创建 `UserIdInput.jsx`
- [x] 创建 `ChatMessage.jsx`
- [x] 创建 `ChatInput.jsx`
- [x] 创建 `DebugDetails.jsx`
- [x] 在 `App.jsx` 里组合这些组件
- [x] 做一个顶部栏：标题、API 状态、刷新按钮、`user_id`
- [x] 做一个中间聊天区：用户消息靠右，AI 消息靠左
- [x] 做一个 AI 示例回复：包含 answer、下一步、小练习、检查点
- [x] 做一个底部输入区：输入框和发送按钮
- [x] 做一个默认折叠的调试详情样式

### 关键代码提示

静态阶段可以先用假数据理解结构：

```js
const demoReply = {
  answer: "这里显示 AI 的主要回答。",
  next_task: "这里显示下一步任务。",
  exercise: "这里显示一个小练习。",
  checkpoints: ["检查点 1", "检查点 2", "检查点 3"],
}
```

组件调用大致会像这样：

```jsx
<ChatMessage role="assistant" reply={demoReply} />
```

### 交付物

- [x] 顶部栏能显示出来
- [x] 聊天区能显示静态用户消息
- [x] 聊天区能显示静态 AI 消息
- [x] AI 消息能显示 answer、下一步、小练习、检查点
- [x] 底部输入框能显示出来
- [x] 调试详情默认折叠

### 验收标准

- [x] 你能解释为什么先做静态界面
- [x] 你能说清楚每个组件负责什么
- [x] 你能指出 `ChatMessage` 里哪里显示 `answer`
- [x] 你能指出 `DebugDetails` 为什么默认隐藏
- [x] 页面看起来是聊天工作台，而不是普通 API 表单

### 阶段复盘

复盘记录：

```text
1. 阶段 3 先把页面当成静态草图来做，没有急着接后端和复杂状态。
2. 顶部栏、消息区、输入区和调试详情已经拆成清晰组件，App.jsx 只负责组合它们。
3. 下一阶段要让输入框和消息列表真正动起来，所以会开始学习 useState、受控输入框和本地消息流。
```

---

## 阶段 4：React 状态管理与本地消息流

阶段目标：让聊天界面在不连接后端的情况下先能本地交互。

这一阶段开始让页面“活起来”。用户输入问题后，页面应该能把用户消息添加到聊天区。

### 你要学习

- [x] 什么是 `useState`
- [x] 状态改变为什么会让页面重新渲染
- [x] 什么是受控输入框
- [x] 什么是消息列表
- [x] 为什么消息需要 `id`
- [x] 为什么发送后要清空输入框
- [x] 为什么发送中要禁用按钮

### 主线任务

- [x] 用 `useState` 保存 `userId`
- [x] 用 `useState` 保存输入框内容
- [x] 用 `useState` 保存消息列表
- [x] 点击发送后，把用户消息加入列表
- [x] 发送空消息时不新增消息
- [x] 发送后清空输入框
- [x] 先用本地假 AI 回复模拟一次完整对话
- [x] 给发送按钮加禁用状态

### 关键代码提示

消息列表可以先从空数组开始：

```js
const [messages, setMessages] = useState([])
```

一条消息可以大致长这样：

```js
{
  id: "message-1",
  role: "user",
  content: "FastAPI 的路由是什么？"
}
```

AI 消息后面会比用户消息多一个 `reply` 和 `debug`。

### 交付物

- [x] 顶部 `user_id` 输入框可以修改
- [x] 底部消息输入框可以输入内容
- [x] 点击发送能新增用户消息
- [x] 空消息不会被发送
- [x] 发送后输入框会清空
- [x] 本地假 AI 回复可以显示在聊天区

### 验收标准

- [x] 你能解释 `useState` 是做什么的
- [x] 你能解释为什么不能直接修改 `messages`
- [x] 你能说出用户消息的数据结构
- [x] 你能说出 AI 消息为什么需要保存结构化 `reply`
- [x] 你能完成一轮本地假对话

### 阶段复盘

复盘记录：

```text
1. 阶段 4 把 UserIdInput 和 ChatInput 改成受控组件，输入内容由 App.jsx 的状态统一管理。
2. messages 变成真正的消息列表，点击发送会追加用户消息和本地假 AI 回复。
3. 现在页面已经能完成一轮本地假对话，下一阶段再开始连接后端 /health。
```

---

## 阶段 5：连接后端 `/health` 与 CORS

阶段目标：让前端打开时自动检测后端是否在线。

这一阶段是第一次真正前后端联调。你会遇到一个重要概念：浏览器跨域限制。

### 你要学习

- [x] 什么是 `fetch`
- [x] 什么是 HTTP 请求
- [x] 什么是 API base URL
- [x] 什么是 CORS
- [x] 为什么 Swagger 能访问接口，但前端页面可能不能访问
- [x] 为什么后端要允许当前前端地址，例如 `http://127.0.0.1:5173` 或 `http://127.0.0.1:5174`
- [x] 前端如何显示 loading、success、error 三种状态

### 主线任务

- [x] 启动后端服务
- [x] 启动前端服务
- [x] 在后端添加 CORS 配置
- [x] 创建 `src/api/tutorApi.js`
- [x] 在 `tutorApi.js` 中写 `getHealth()`
- [x] 页面打开时自动调用 `GET /health`
- [x] 顶部显示 `连接中`
- [x] 成功时显示 `API 在线`
- [x] 失败时显示 `API 离线`
- [x] 添加一个刷新按钮，手动重新检测 `/health`
- [ ] 停掉后端，确认前端能显示离线状态

### 后端 CORS 关键提示

后端需要允许前端开发地址访问。具体代码以后按阶段让 AI 带你写，不要直接乱贴。

你会接触到的核心导入大致是：

```py
from fastapi.middleware.cors import CORSMiddleware
```

允许的前端来源大致是：

```py
"http://127.0.0.1:5173"
"http://127.0.0.1:5174"
```

### 前端请求关键提示

`tutorApi.js` 里会出现类似这样的请求：

```js
const API_BASE_URL = "http://127.0.0.1:8001"

export async function getHealth() {
  const response = await fetch(`${API_BASE_URL}/health`)
  return response.json()
}
```

### 交付物

- [x] 后端允许前端跨域访问
- [x] `frontend/src/api/tutorApi.js`
- [x] `getHealth()` 函数
- [x] 顶部 API 状态显示
- [x] 刷新状态按钮

### 验收标准

- [x] 后端启动时，前端显示 `API 在线`
- [ ] 后端停止时，前端显示 `API 离线`
- [x] 刷新按钮可以重新检测状态
- [x] 你能解释 CORS 为什么出现
- [x] 你能解释为什么这一阶段只连 `/health`，不急着连 `/chat`

### 阶段复盘

复盘记录：

```text
1. 阶段 5 先连接 GET /health，只验证后端是否在线，不急着发送聊天内容。
2. 后端加了 CORS，允许当前 Vite 前端地址从浏览器访问 API。
3. 前端新增 tutorApi.js，把请求后端的代码集中管理，App.jsx 只负责调用和更新状态。
```

---

## 阶段 6：连接后端 `/chat` 与结构化 Tutor 回复

阶段目标：把用户问题发送给后端，并把 Tutor Agent 的结构化回复显示在聊天界面。

这一阶段是第一版前端的核心。完成后，你就可以用浏览器测试真实后端对话能力。

### 你要学习

- [x] 什么是 POST 请求
- [x] 什么是请求体
- [x] 什么是响应体
- [x] 前端如何发送 JSON
- [x] 前端如何读取嵌套字段
- [x] loading 状态为什么重要
- [x] 错误处理为什么不能只靠浏览器控制台
- [x] 调试详情为什么适合当前项目

### 主线任务

- [x] 在 `tutorApi.js` 中写 `postChat()`
- [x] 请求体包含 `user_id` 和 `message`
- [x] 点击发送时先把用户消息加入聊天区
- [x] 发送请求时显示 loading 状态
- [x] 请求成功后，把 AI 回复加入聊天区
- [x] AI 回复显示 `reply.answer`
- [x] AI 回复显示 `reply.next_task`
- [x] AI 回复显示 `reply.exercise`
- [x] AI 回复显示 `reply.checkpoints`
- [x] 每条 AI 回复下面显示默认折叠的调试详情
- [x] 调试详情展示请求 URL
- [x] 调试详情展示请求体
- [x] 调试详情展示响应 JSON
- [x] 调试详情展示请求耗时
- [x] 请求失败时显示友好错误
- [x] 后端返回结构缺字段时，前端不直接崩溃

### 关键代码提示

发送聊天请求的调用大致会像这样：

```js
const data = await postChat({
  user_id: userId,
  message: inputText,
})
```

前端读取主回答时，大致会访问：

```js
data.reply.answer
```

调试信息可以保存这些内容：

```js
{
  url: "http://127.0.0.1:8001/chat",
  method: "POST",
  requestBody: { user_id: "default", message: "..." },
  responseBody: data,
  durationMs: 1234
}
```

### 交付物

- [x] `postChat()` 函数
- [x] 真实 `/chat` 请求可以从前端发出
- [x] 聊天区能显示真实 AI 回复
- [x] AI 回复能显示结构化 Tutor 信息
- [x] 调试详情默认折叠并且可以展开
- [x] 请求失败时页面不会崩溃

### 验收标准

- [x] 输入问题后，前端会请求 `POST /chat`
- [x] 请求体里包含当前顶部输入框的 `user_id`
- [x] 请求体里包含用户刚输入的 `message`
- [x] 后端成功响应后，页面能显示 `answer`
- [x] 页面能显示下一步、小练习、检查点
- [x] 展开调试详情能看到请求体和响应体
- [x] 停掉后端后，发送消息会显示友好错误
- [x] 你能解释一次完整的前后端聊天流程

### 阶段复盘

复盘记录：

```text
1. 阶段 6 把发送消息从本地假回复切换成真实 POST /chat 请求。
2. 成功时页面会显示后端返回的结构化 TutorReply，失败时会显示友好错误消息。
3. 调试详情现在能看到请求 URL、请求体、响应 JSON、状态码和耗时，方便前后端联调。
```

---

## 阶段 7：查看用户历史记录

阶段目标：把后端已经保存的对话历史显示到前端页面里。

这一阶段开始接入第三个真实接口：`GET /conversations/{user_id}`。它和 `/chat` 不一样，`/chat` 是发送一条新消息，历史查询是按当前 `user_id` 把数据库里已经保存过的记录读出来。

### 你要学习

- [x] 什么是 GET 查询接口
- [x] 什么是路径参数 `user_id`
- [x] 什么是查询参数 `limit`
- [x] 为什么历史记录适合单独拆成组件
- [x] 前端如何显示 idle、loading、success、error 状态
- [x] 为什么历史查询也需要调试详情

### 当前主线任务

- [x] 创建 `ConversationHistory.jsx`
- [x] 在 `tutorApi.js` 中添加 `getConversations(userId, limit)`
- [x] 根据顶部 `user_id` 查询最近几条历史
- [x] 支持输入 `limit`，控制查询条数
- [x] 在左侧历史区域展示对话记录
- [x] 显示历史记录 id、创建时间、用户问题和 AI 主回答
- [x] 历史查询成功时显示列表
- [x] 历史查询为空时显示空状态
- [x] 历史查询失败时显示错误状态
- [x] 历史调试详情展示请求 URL、方法、状态码、响应体和耗时
- [x] 用浏览器验证 `demo-user` 可以读取保存过的历史记录

### 关键代码提示

历史查询函数大致长这样：

```js
export async function getConversations(userId, limit = 20) {
  const response = await fetch(
    `${API_BASE_URL}/conversations/${userId}?limit=${limit}`,
  )

  return response.json()
}
```

真实代码里还额外做了两件事：

- 用 `encodeURIComponent(userId)` 处理用户输入，避免特殊字符破坏 URL。
- 保存 `debug`，让你能展开历史调试详情看请求和响应。

### 交付物

- [x] `frontend/src/components/ConversationHistory.jsx`
- [x] `getConversations(userId, limit)`
- [x] 左侧历史记录面板
- [x] 历史记录条数输入框
- [x] “查看历史”按钮
- [x] 历史调试详情
- [x] 阶段复盘记录

### 验收标准

- [x] 页面能显示历史记录区域
- [x] 点击“查看历史”会请求 `GET /conversations/{user_id}`
- [x] 请求会带上当前输入框里的 `user_id`
- [x] 请求会带上当前设置的 `limit`
- [x] 有历史时能显示问题和回答
- [x] 展开历史调试详情能看到请求 URL 和状态码
- [x] 你能解释历史查询和发送聊天的区别

---

## 阶段 8：最终验收与复盘

阶段目标：把第一版前端做一次最终收口，确认能运行、能联调、能解释。

### 第一版最终验收清单

- [x] 前端项目位于 `frontend/`
- [x] 后端可以通过 PowerShell 启动
- [x] 前端可以通过 PowerShell 启动
- [x] 页面顶部有 `user_id` 输入框
- [x] 页面顶部有 API 状态
- [x] 页面打开会自动检测 `/health`
- [x] 用户可以输入问题
- [x] 用户可以发送问题到 `/chat`
- [x] 页面能显示 AI 的 `answer`
- [x] 页面能显示下一步任务
- [x] 页面能显示小练习
- [x] 页面能显示检查点
- [x] 调试详情默认折叠
- [x] 调试详情展开后能看到请求和响应
- [x] 页面可以查看当前用户历史记录
- [ ] 后端停止时页面有友好错误
- [ ] 你能解释前端到后端的一次完整请求流程

### 交付物

- [x] 可运行的 React + Vite 前端
- [x] 可联调的 FastAPI 后端
- [x] 完整的 ChatGPT 式 Tutor Agent 测试界面
- [x] 隐藏式调试详情
- [x] 用户历史记录面板
- [ ] 最终阶段复盘记录

### 验收标准

- [ ] 你能从零启动后端和前端
- [x] 你能用浏览器完成一轮真实对话
- [x] 你能解释 `GET /health` 的作用
- [x] 你能解释 `POST /chat` 的请求和响应
- [x] 你能解释 `GET /conversations/{user_id}` 的请求和响应
- [ ] 你能告诉 AI 下一阶段应该只改哪些文件

### 阶段复盘

复盘记录：

```text
1. 阶段 7 把历史记录从“未来扩展”变成了真实前端功能。
2. ConversationHistory.jsx 负责显示历史区域，App.jsx 负责保存历史状态和触发查询。
3. getConversations(userId, limit) 使用 GET 请求读取后端保存的数据，和 POST /chat 的“新增对话”不是一回事。
```

---

## 常见联调问题

### 页面显示 API 离线

优先检查：

- 后端是否启动。
- 后端是否运行在 `http://127.0.0.1:8001`。
- 浏览器控制台是否有 CORS 报错。
- `/health` 在浏览器或 Swagger 中是否能访问。

### 浏览器控制台出现 CORS 错误

说明浏览器阻止了前端访问后端。

优先检查：

- 后端是否添加了 `CORSMiddleware`。
- `allow_origins` 是否包含当前前端地址，比如 `http://127.0.0.1:5173` 或 `http://127.0.0.1:5174`。
- 前端地址是不是实际运行在 `5173`，还是 Vite 换了另一个端口。

### Swagger 可以请求，前端不能请求

这通常不是接口本身坏了，而是浏览器跨域限制。

Swagger 页面通常来自后端同源地址；Vite 前端来自另一个端口，所以会触发 CORS。

### `/chat` 返回 422

通常是请求体不符合后端 schema。

检查前端是否发送：

```json
{
  "user_id": "default",
  "message": "..."
}
```

`user_id` 和 `message` 都不能为空。

### `/chat` 返回 500 或 502

可能是后端配置、模型调用或数据库逻辑出错。

第一步不要改前端，先看后端终端日志。

### 页面显示空白

优先检查：

- 前端终端是否有编译错误。
- 浏览器控制台是否有 JavaScript 错误。
- `App.jsx` 是否正常导出组件。
- `main.jsx` 是否正常渲染 `<App />`。

---

## AI 协作提示词模板

这些模板用于让 AI 像前端学习导师一样带你推进，而不是一次性替你写完整项目。

### 阶段推进模板

```text
你是我的前端学习导师。请根据 docs/frontend-quest-progress.md 只推进当前阶段，不要提前实现后续阶段。

当前阶段：
阶段 X：这里写阶段名称

要求：
1. 先解释这一阶段要学什么。
2. 再告诉我会改哪些文件。
3. 一次只改必要文件。
4. 改完后给我 Windows PowerShell 运行命令。
5. 最后用新手能懂的话解释代码。
6. 不要提前实现后续阶段的功能。
```

### 代码解释模板

```text
请用新手能懂的话解释刚才改过的前端代码。

重点解释：
1. 每个文件负责什么。
2. 每个 React 组件负责什么。
3. useState 或 fetch 在这里做了什么。
4. 这段代码和后端 API 的关系是什么。
5. 我需要自己复述的 3 个关键点是什么。
```

### 报错求助模板

```text
我在推进 docs/frontend-quest-progress.md 的阶段 X 时遇到了报错。

我执行的命令是：
这里粘贴命令

终端或浏览器报错是：
这里粘贴完整报错

请你：
1. 先判断这是前端、后端、环境还是 CORS 问题。
2. 用新手能懂的话解释原因。
3. 给我最小修复步骤。
4. 不要顺手重构无关代码。
```

### 前后端联调排查模板

```text
前端请求后端失败了。请你按顺序带我排查。

当前信息：
前端地址：http://127.0.0.1:5173 或当前实际端口
后端地址：http://127.0.0.1:8001
失败接口：这里写 /health 或 /chat
浏览器错误：这里粘贴错误
后端终端日志：这里粘贴日志

要求：
1. 先判断后端有没有启动。
2. 再判断 API 地址是否正确。
3. 再判断是不是 CORS。
4. 再判断请求体是否符合后端 schema。
5. 每一步告诉我该运行什么 PowerShell 命令或该看哪里。
```

### 阶段复盘模板

```text
我刚完成 docs/frontend-quest-progress.md 的阶段 X。

请你用提问的方式帮我复盘，不要直接给答案。

请问我：
1. 这一阶段最重要的概念是什么？
2. 我改了哪些文件，每个文件负责什么？
3. 如果这个功能坏了，我会从哪里开始排查？
4. 这个阶段和后端 API 有什么关系？
5. 我能否用自己的话解释完整流程？
```

---

## 第一版不做的功能

这些功能以后有价值，但不属于第一版前端范围：

- 登录注册
- JWT 鉴权
- 用户头像上传
- 复杂侧边栏历史
- 对话搜索
- Markdown 富文本渲染
- 文件上传
- RAG 文档问答
- 语音输入
- 移动端专门适配
- 深色/浅色主题切换
- 复杂动画
- 前端自动化测试
- 部署上线

第一版先把最重要的链路跑通：

```text
用户输入问题
  -> React 保存输入
  -> 前端发送 POST /chat
  -> FastAPI 调用 Tutor Agent
  -> 后端返回结构化 reply
  -> 前端展示 answer、next_task、exercise、checkpoints
  -> 用户可以展开调试详情查看请求和响应
```

---

## 下一版可能方向

第一版完成后，可以考虑这些方向：

- 接入 `GET /conversations/{user_id}`，显示历史记录。
- 给聊天消息增加 Markdown 渲染。
- 给后端错误增加更友好的前端提示。
- 增加学习主题选择。
- 增加示例问题按钮。
- 增加“复制回复”按钮。
- 增加“重新生成”按钮。
- 增加“继续追问”快捷按钮。
- 把 API base URL 放入 `.env`。
- 为前端添加基础测试。

这些都不是第一版必须做的内容。先完成主线，再扩展。
