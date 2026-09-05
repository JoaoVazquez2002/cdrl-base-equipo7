CREATE TABLE IF NOT EXISTS telemetry (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    temperature NUMERIC(5, 2) NOT NULL
);