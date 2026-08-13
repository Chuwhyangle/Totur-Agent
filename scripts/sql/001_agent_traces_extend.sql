USE tutor_agent;

ALTER TABLE agent_traces
  ADD COLUMN trace_id     CHAR(32)    AFTER id,
  ADD COLUMN session_id   BIGINT      AFTER user_id,
  ADD COLUMN persona_id   VARCHAR(32) AFTER session_id,
  ADD COLUMN model        VARCHAR(64),
  ADD COLUMN react_rounds INT         DEFAULT 0,
  ADD COLUMN llm_calls    INT         DEFAULT 0,
  ADD COLUMN tool_calls   INT         DEFAULT 0,
  ADD COLUMN embed_ms     INT,
  ADD COLUMN search_ms    INT,
  ADD COLUMN rerank_ms    INT,
  ADD COLUMN tool_other_ms INT;

ALTER TABLE agent_traces ADD INDEX idx_trace_id (trace_id);
ALTER TABLE agent_traces ADD INDEX idx_created_at (created_at);
