USE tutor_agent;

CREATE TABLE IF NOT EXISTS tool_calls (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  trace_id      CHAR(32),
  round_number  INT,
  tool_name     VARCHAR(64),
  channel       VARCHAR(16),      -- internal / mcp
  forced        TINYINT DEFAULT 0,-- 1=force_rag/force_web_search 强制触发
  ok            TINYINT,
  error_code    VARCHAR(64),      -- tool_not_found / invalid_arguments /
                                  -- tool_execution_failed / web_search_budget_exceeded
  cost_ms       INT,
  args_preview  VARCHAR(512),
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_trace_id (trace_id),
  INDEX idx_tool_created (tool_name, created_at),
  INDEX idx_created_at (created_at)
);
