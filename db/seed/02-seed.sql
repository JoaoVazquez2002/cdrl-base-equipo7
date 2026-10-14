INSERT INTO telemetry (device_id, timestamp, temperature)
VALUES
    ('sensor-01', '2026-01-01 00:00:00+00', 22.50),
    ('sensor-02', '2026-01-01 00:00:00+00', 24.10)
ON CONFLICT (device_id, timestamp) DO NOTHING;