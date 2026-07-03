import { useEffect, useState } from 'react'

import { getHealth, postChat } from './api/tutorApi.js'
import ApiStatus from './components/ApiStatus.jsx'
import ChatInput from './components/ChatInput.jsx'
import ChatMessage from './components/ChatMessage.jsx'
import UserIdInput from './components/UserIdInput.jsx'

const demoReply = {
  answer: '前端页面可以先理解成运行在浏览器里的程序。',
  next_task: '先分清 index.html、main.jsx 和 App.jsx 各自负责什么。',
  exercise: '打开这三个文件，说出每个文件在页面启动流程里的作用。',
  checkpoints: ['知道浏览器先拿到 HTML', '知道 main.jsx 负责启动 React', '知道 App.jsx 负责页面结构'],
}

const demoDebug = {
  request: {
    user_id: 'demo-user',
    message: '我想借这个项目学前端基础。',
  },
  response: {
    reply: demoReply,
  },
}

const initialMessages = [
  {
    id: 'message-welcome',
    role: 'assistant',
    text: '今天想学点什么？',
  },
  {
    id: 'message-demo-user',
    role: 'user',
    text: '我想借这个项目学前端基础。',
  },
  {
    id: 'message-demo-assistant',
    role: 'assistant',
    reply: demoReply,
    debug: demoDebug,
  },
]

function createErrorReply() {
  return {
    answer: '这次请求后端失败了，但页面没有崩溃。',
    next_task: '先确认后端是否运行在 http://127.0.0.1:8001。',
    exercise: '点击顶部刷新按钮，观察 API 状态是否在线。',
    checkpoints: ['用户消息已经保留', '错误被显示在聊天区', '调试详情里可以查看失败信息'],
  }
}

// App 是当前前端页面的主组件，负责组合组件和管理页面状态。
function App() {
  const [apiStatus, setApiStatus] = useState('checking')
  const [userId, setUserId] = useState('demo-user')
  const [draftMessage, setDraftMessage] = useState('')
  const [messages, setMessages] = useState(initialMessages)
  const [isSending, setIsSending] = useState(false)

  const canSend = draftMessage.trim().length > 0 && !isSending

  async function handleSendMessage(event) {
    event.preventDefault()

    const trimmedMessage = draftMessage.trim()
    if (!trimmedMessage || isSending) {
      return
    }

    const requestBody = {
      user_id: userId,
      message: trimmedMessage,
    }
    const userMessage = {
      id: `message-user-${Date.now()}`,
      role: 'user',
      text: trimmedMessage,
    }

    setMessages((currentMessages) => [...currentMessages, userMessage])
    setDraftMessage('')
    setIsSending(true)

    try {
      const { data, debug } = await postChat(requestBody)
      const assistantMessage = {
        id: `message-assistant-${Date.now()}`,
        role: 'assistant',
        reply: data?.reply,
        debug,
      }

      setMessages((currentMessages) => [...currentMessages, assistantMessage])
      setApiStatus('online')
    } catch (error) {
      const errorMessage = {
        id: `message-error-${Date.now()}`,
        role: 'assistant',
        reply: createErrorReply(),
        debug: error.debug ?? {
          url: 'http://127.0.0.1:8001/chat',
          method: 'POST',
          requestBody,
          error: error.message,
        },
      }

      setMessages((currentMessages) => [...currentMessages, errorMessage])
      setApiStatus('offline')
    } finally {
      setIsSending(false)
    }
  }

  async function checkApiHealth() {
    setApiStatus('checking')

    try {
      await getHealth()
      setApiStatus('online')
    } catch {
      setApiStatus('offline')
    }
  }

  useEffect(() => {
    checkApiHealth()
  }, [])

  return (
    <main className="app-shell">
      {/* 顶部区域：显示标题、API 状态、刷新按钮和当前 user_id。 */}
      <header className="app-header">
        <div>
          <p className="app-kicker">Tutor Agent</p>
          <h1>学习对话工作台</h1>
        </div>
        <div className="header-controls">
          <ApiStatus status={apiStatus} />
          {/* 刷新按钮会重新请求 GET /health，手动更新 API 状态。 */}
          <button
            className="refresh-button"
            type="button"
            disabled={apiStatus === 'checking'}
            onClick={checkApiHealth}
          >
            刷新
          </button>
          <UserIdInput userId={userId} onUserIdChange={setUserId} />
        </div>
      </header>

      {/* 聊天区域：发送消息后，用户消息和真实后端回复都会加入 messages。 */}
      <section className="chat-surface" aria-label="聊天工作区">
        <div className="thread-preview">
          {messages.map((message) => (
            <ChatMessage
              key={message.id}
              role={message.role}
              text={message.text}
              reply={message.reply}
              debug={message.debug}
            />
          ))}
        </div>
        <ChatInput
          message={draftMessage}
          onMessageChange={setDraftMessage}
          onSubmit={handleSendMessage}
          disabled={!canSend}
          isSending={isSending}
        />
      </section>
    </main>
  )
}

export default App
