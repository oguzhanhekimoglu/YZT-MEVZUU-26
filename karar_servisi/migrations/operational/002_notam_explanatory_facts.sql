ALTER TABLE video_contexts ADD COLUMN fir_code TEXT;
ALTER TABLE video_contexts ADD COLUMN aerodrome_code TEXT;
ALTER TABLE video_contexts ADD COLUMN operation_lower_limit INTEGER;
ALTER TABLE video_contexts ADD COLUMN operation_upper_limit INTEGER;

ALTER TABLE notams ADD COLUMN display_number TEXT;
ALTER TABLE notams ADD COLUMN notam_year INTEGER;
ALTER TABLE notams ADD COLUMN q_code TEXT;
ALTER TABLE notams ADD COLUMN item_e TEXT;
ALTER TABLE notams ADD COLUMN estimated_end INTEGER NOT NULL DEFAULT 0;
ALTER TABLE notams ADD COLUMN permanent INTEGER NOT NULL DEFAULT 0;
ALTER TABLE notams ADD COLUMN lower_limit INTEGER;
ALTER TABLE notams ADD COLUMN upper_limit INTEGER;
ALTER TABLE notams ADD COLUMN fir_code TEXT;
ALTER TABLE notams ADD COLUMN aerodrome_code TEXT;
ALTER TABLE notams ADD COLUMN operational_reason_tr TEXT;
ALTER TABLE notams ADD COLUMN conflict_with_permission INTEGER NOT NULL DEFAULT 0;
ALTER TABLE notams ADD COLUMN conflict_with_flight_plan INTEGER NOT NULL DEFAULT 0;