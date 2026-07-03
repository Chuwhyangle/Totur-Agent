// DebugDetails 负责显示调试信息，默认折叠，不打扰正常聊天内容。
function DebugDetails({ data, title = '调试详情' }) {
  return (
    <details className="debug-details">
      <summary>{title}</summary>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </details>
  )
}

export default DebugDetails
