USE tutor_agent;

CREATE TABLE IF NOT EXISTS retrieval_events (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  trace_id    CHAR(32),
  query       TEXT,
  collection  VARCHAR(32),

  embed_ms    INT,
  search_ms   INT,
  rerank_ms   INT,
  cost_ms     INT,

  top_k             INT,
  candidate_count   INT,
  hit_count         INT,
  top_score         FLOAT,
  min_score         FLOAT,
  passed            TINYINT,

  threshold         FLOAT,
  rerank_applied    TINYINT,
  rerank_fallback   VARCHAR(64),
  corpus_fingerprint VARCHAR(128),

  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_trace_id (trace_id),
  INDEX idx_created_at (created_at)
);
