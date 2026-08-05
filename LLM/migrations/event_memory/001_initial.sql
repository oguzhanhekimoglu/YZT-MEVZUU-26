CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    request_id TEXT UNIQUE NOT NULL,
    event_fingerprint TEXT,
    retry_of_event_id TEXT,
    video_id TEXT,
    camera_id TEXT,
    context_id TEXT,
    track_id TEXT,
    observation_time_utc TEXT,
    event_status TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    completed_at_utc TEXT,
    error_code TEXT,
    error_message TEXT,
    FOREIGN KEY(retry_of_event_id) REFERENCES events(event_id)
);

CREATE UNIQUE INDEX ux_events_active_fingerprint
ON events (event_fingerprint)
WHERE event_fingerprint IS NOT NULL
  AND event_status IN (
    'CREATED',
    'INPUT_VALIDATED',
    'CONTEXT_RESOLVED',
    'WAITING_FOR_GPU_HANDOFF',
    'TOOLS_RUNNING',
    'TOOLS_COMPLETED',
    'VERIFICATION_COMPLETED',
    'RISK_ASSESSED',
    'RAG_COMPLETED',
    'LLM_COMPLETED'
  );

CREATE UNIQUE INDEX ux_events_finalized_fingerprint
ON events (event_fingerprint)
WHERE event_fingerprint IS NOT NULL AND event_status = 'FINALIZED';

CREATE INDEX idx_events_fingerprint_history
ON events (event_fingerprint, created_at_utc DESC);

CREATE TABLE event_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    step_status TEXT NOT NULL,
    payload_json TEXT,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(event_id) REFERENCES events(event_id) ON DELETE CASCADE
);

CREATE INDEX idx_event_steps_event_order
ON event_steps (event_id, id);

CREATE TABLE tool_executions (
    tool_execution_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    execution_status TEXT NOT NULL,
    domain_status TEXT,
    request_json TEXT,
    response_json TEXT,
    latency_ms INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),
    error_code TEXT,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(event_id) REFERENCES events(event_id) ON DELETE CASCADE,
    UNIQUE(event_id, tool_name, attempt_number)
);

CREATE INDEX idx_tool_executions_request
ON tool_executions (request_id);

CREATE INDEX idx_tool_executions_event
ON tool_executions (event_id, tool_name, attempt_number);

CREATE TABLE final_outputs (
    event_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    output_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(event_id) REFERENCES events(event_id) ON DELETE CASCADE
);

CREATE TABLE raw_inputs (
    event_id TEXT PRIMARY KEY,
    sanitized_request_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(event_id) REFERENCES events(event_id) ON DELETE CASCADE
);
