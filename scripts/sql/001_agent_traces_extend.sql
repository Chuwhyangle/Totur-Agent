USE tutor_agent;

CREATE TABLE IF NOT EXISTS agent_traces (
  id              BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id         VARCHAR(64),
  question        TEXT,
  total_ms        INT,
  retrieval_ms    INT,
  llm_ms          INT,
  status          VARCHAR(16) DEFAULT 'OK',
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

SET @sql = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'agent_traces'
      AND column_name = 'trace_id'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD COLUMN trace_id CHAR(32) AFTER id'
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
      AND column_name = 'session_id'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD COLUMN session_id BIGINT AFTER user_id'
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
      AND column_name = 'persona_id'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD COLUMN persona_id VARCHAR(32) AFTER session_id'
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
      AND column_name = 'model'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD COLUMN model VARCHAR(64)'
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
      AND column_name = 'react_rounds'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD COLUMN react_rounds INT DEFAULT 0'
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
      AND column_name = 'llm_calls'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD COLUMN llm_calls INT DEFAULT 0'
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
      AND column_name = 'tool_calls'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD COLUMN tool_calls INT DEFAULT 0'
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
      AND column_name = 'embed_ms'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD COLUMN embed_ms INT'
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
      AND column_name = 'search_ms'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD COLUMN search_ms INT'
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
      AND column_name = 'rerank_ms'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD COLUMN rerank_ms INT'
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
      AND column_name = 'tool_other_ms'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD COLUMN tool_other_ms INT'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'agent_traces'
      AND index_name = 'idx_trace_id'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD INDEX idx_trace_id (trace_id)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'agent_traces'
      AND index_name = 'idx_created_at'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD INDEX idx_created_at (created_at)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
