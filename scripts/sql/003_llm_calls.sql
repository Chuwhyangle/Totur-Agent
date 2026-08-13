USE tutor_agent;

CREATE TABLE llm_calls (
  id                BIGINT AUTO_INCREMENT PRIMARY KEY,
  trace_id          CHAR(32),
  round_number      INT,
  call_type         VARCHAR(16),   -- with_tools / final / stream
  model             VARCHAR(64),
  prompt_tokens     INT,
  completion_tokens INT,
  total_tokens      INT,
  cost_ms           INT,
  finish_reason     VARCHAR(32),
  created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_trace_id (trace_id)
);

ALTER TABLE agent_traces
  ADD COLUMN prompt_tokens     INT,
  ADD COLUMN completion_tokens INT;
