USE tutor_agent;

CREATE TABLE IF NOT EXISTS llm_calls (
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

SET @sql = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'agent_traces'
      AND column_name = 'prompt_tokens'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD COLUMN prompt_tokens INT'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'agent_traces'
      AND column_name = 'completion_tokens'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD COLUMN completion_tokens INT'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
