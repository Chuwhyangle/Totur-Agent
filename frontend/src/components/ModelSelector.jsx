// ModelSelector 负责在顶部栏展示当前可用的聊天模型。
function ModelSelector({
  models,
  selectedModelId,
  status,
  onModelChange,
}) {
  const modelOptions = Array.isArray(models) && models.length > 0
    ? models
    : [
        {
          model_id: selectedModelId,
          display_name: '默认模型',
        },
      ]
  const isLoading = status === 'loading'

  return (
    <label className="model-field">
      <span>模型</span>
      <select
        className="model-select"
        value={selectedModelId}
        disabled={isLoading && modelOptions.length === 0}
        onChange={(event) => onModelChange(event.target.value)}
      >
        {modelOptions.map((model) => (
          <option key={model.model_id} value={model.model_id} title={model.description}>
            {model.display_name}
          </option>
        ))}
      </select>
    </label>
  )
}

export default ModelSelector
