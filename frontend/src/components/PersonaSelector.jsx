// PersonaSelector 负责在顶部栏展示当前可选的人设列表。
function PersonaSelector({
  personas,
  selectedPersonaId,
  status,
  onPersonaChange,
}) {
  const personaOptions = Array.isArray(personas) && personas.length > 0
    ? personas
    : [
        {
          persona_id: selectedPersonaId,
          name: '默认导师',
          description: '后端学习与面试训练的默认人设。',
        },
      ]
  const isLoading = status === 'loading'

  return (
    <label className="persona-field">
      <span>人设</span>
      <select
        className="persona-select"
        value={selectedPersonaId}
        disabled={isLoading && personaOptions.length === 0}
        onChange={(event) => onPersonaChange(event.target.value)}
      >
        {personaOptions.map((persona) => (
          <option key={persona.persona_id} value={persona.persona_id}>
            {persona.name}
          </option>
        ))}
      </select>
    </label>
  )
}

export default PersonaSelector
