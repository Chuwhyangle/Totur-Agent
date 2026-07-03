// UserIdInput 是受控输入框：显示什么、怎么更新，都由 App.jsx 管理。
function UserIdInput({ userId, onUserIdChange }) {
  return (
    <label className="user-id-field">
      <span>user_id</span>
      <input
        type="text"
        value={userId}
        onChange={(event) => onUserIdChange(event.target.value)}
        aria-label="user_id"
      />
    </label>
  )
}

export default UserIdInput
