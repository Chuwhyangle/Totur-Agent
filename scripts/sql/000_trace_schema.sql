-- Canonical fresh-install reference for the Agent observability database.
-- Connect the mysql client to TRACE_DB_NAME before executing this file.
-- The Python initializer is preferred because it also upgrades old tables.

CREATE TABLE IF NOT EXISTS agent_traces (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  trace_id CHAR(32) NOT NULL,
  user_id VARCHAR(64),
  session_id BIGINT,
  persona_id VARCHAR(64),
  model VARCHAR(128),
  question TEXT,
  total_ms INT,
  retrieval_ms INT,
  llm_ms INT,
  status VARCHAR(16) NOT NULL DEFAULT 'RUNNING',
  react_rounds INT DEFAULT 0,
  llm_calls INT DEFAULT 0,
  tool_calls INT DEFAULT 0,
  tool_failures INT DEFAULT 0,
  embed_ms INT,
  search_ms INT,
  rerank_ms INT,
  tool_other_ms INT,
  prompt_tokens INT,
  completion_tokens INT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_agent_traces_trace_id (trace_id),
  KEY idx_agent_traces_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS retrieval_events (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  trace_id CHAR(32),
  query TEXT,
  collection VARCHAR(64),
  embed_ms INT,
  search_ms INT,
  rerank_ms INT,
  cost_ms INT,
  top_k INT,
  candidate_count INT,
  hit_count INT,
  top_score FLOAT,
  min_score FLOAT,
  passed TINYINT,
  threshold FLOAT,
  rerank_applied TINYINT,
  rerank_fallback VARCHAR(64),
  corpus_fingerprint VARCHAR(128),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_retrieval_events_trace_id (trace_id),
  KEY idx_retrieval_events_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS llm_calls (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  trace_id CHAR(32),
  round_number INT,
  call_type VARCHAR(16),
  model VARCHAR(128),
  prompt_tokens INT,
  completion_tokens INT,
  total_tokens INT,
  cost_ms INT,
  finish_reason VARCHAR(32),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_llm_calls_trace_id (trace_id),
  KEY idx_llm_calls_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS tool_calls (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  trace_id CHAR(32),
  round_number INT,
  tool_name VARCHAR(64),
  channel VARCHAR(16),
  forced TINYINT DEFAULT 0,
  ok TINYINT,
  error_code VARCHAR(64),
  cost_ms INT,
  args_preview VARCHAR(1024),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_tool_calls_trace_id (trace_id),
  KEY idx_tool_calls_created_at (created_at),
  KEY idx_tool_calls_name_created (tool_name, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
