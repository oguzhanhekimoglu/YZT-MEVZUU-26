CREATE TABLE video_contexts (
    video_id TEXT PRIMARY KEY,
    camera_id TEXT NOT NULL,
    context_id TEXT NOT NULL,
    operational_area_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    video_start_time_utc TEXT NOT NULL,
    description TEXT,
    environment TEXT NOT NULL DEFAULT 'DEMO',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    source_type TEXT NOT NULL DEFAULT 'DEMO_MOCK'
);

CREATE TABLE permissions (
    permission_id TEXT PRIMARY KEY,
    platform_id TEXT NOT NULL,
    registration_mark TEXT,
    operator_name TEXT,
    context_id TEXT NOT NULL,
    operational_area_id TEXT,
    scenario_id TEXT,
    flight_purpose TEXT,
    flight_type TEXT,
    valid_from_utc TEXT NOT NULL,
    valid_to_utc TEXT NOT NULL,
    altitude_ft_msl INTEGER,
    departure_aerodrome TEXT,
    arrival_aerodrome TEXT,
    permission_status TEXT NOT NULL,
    issued_at_utc TEXT,
    source_type TEXT NOT NULL DEFAULT 'DEMO_MOCK',
    notes TEXT
);

CREATE INDEX idx_permissions_lookup
ON permissions (platform_id, context_id, valid_from_utc, valid_to_utc);

CREATE TABLE flight_plans (
    flight_plan_id TEXT PRIMARY KEY,
    platform_id TEXT NOT NULL,
    registration_mark TEXT,
    callsign TEXT,
    context_id TEXT NOT NULL,
    operational_area_id TEXT,
    scenario_id TEXT,
    departure_aerodrome TEXT,
    arrival_aerodrome TEXT,
    planned_departure_utc TEXT NOT NULL,
    planned_arrival_utc TEXT,
    route_or_area TEXT,
    flight_plan_status TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'DEMO_MOCK',
    notes TEXT
);

CREATE INDEX idx_flight_plans_lookup
ON flight_plans (platform_id, context_id, planned_departure_utc);

CREATE TABLE notams (
    notam_id TEXT PRIMARY KEY,
    series TEXT,
    notam_number TEXT,
    context_id TEXT,
    operational_area_id TEXT NOT NULL,
    valid_from_utc TEXT NOT NULL,
    valid_to_utc TEXT NOT NULL,
    notam_status TEXT NOT NULL,
    restriction_type TEXT,
    operation_effect TEXT NOT NULL,
    relevance_tags_json TEXT,
    affected_platform_categories_json TEXT,
    affected_platform_ids_json TEXT,
    summary_tr TEXT NOT NULL,
    source_reference TEXT,
    scenario_id TEXT,
    source_type TEXT NOT NULL DEFAULT 'DEMO_MOCK'
);

CREATE INDEX idx_notams_lookup
ON notams (operational_area_id, valid_from_utc, valid_to_utc);
