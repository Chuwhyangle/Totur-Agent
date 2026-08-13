USE tutor_agent;

-- MySQL 8.0 compatibility: conditionally add the column without
-- relying on ADD COLUMN IF NOT EXISTS.
SET @sql = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'agent_traces'
      AND column_name = 'tool_failures'
  ),
  'SET @noop = 1',
  'ALTER TABLE agent_traces ADD COLUMN tool_failures INT DEFAULT 0'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
