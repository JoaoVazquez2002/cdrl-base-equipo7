import pytest
import psycopg2
from psycopg2 import errors

DB_CONFIG = {
    "dbname": "cdrl",
    "user": "cdrl_dev",
    "password": "cdrl_dev_only",
    "host": "localhost",
    "port": "5432"
}

@pytest.fixture
def db_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True 
    yield conn
    conn.close()

def test_caso_normal_lectura_seed(db_connection):
    with db_connection.cursor() as cur:
        cur.execute("SELECT device_id FROM telemetry;")
        records = cur.fetchall()
        devices = [record[0] for record in records]
        assert "sensor-01" in devices, "Falta sensor-01"
        assert "sensor-02" in devices, "Falta sensor-02"

def test_caso_limite_1_temperatura_maxima(db_connection):
    with db_connection.cursor() as cur:
        cur.execute(
            "INSERT INTO telemetry (device_id, timestamp, temperature) VALUES (%s, NOW(), %s)",
            ("sensor-max", 999.99)
        )
        cur.execute("SELECT temperature FROM telemetry WHERE device_id = 'sensor-max';")
        assert float(cur.fetchone()[0]) == 999.99

def test_caso_limite_2_temperatura_minima(db_connection):
    with db_connection.cursor() as cur:
        cur.execute(
            "INSERT INTO telemetry (device_id, timestamp, temperature) VALUES (%s, NOW(), %s)",
            ("sensor-min", -999.99)
        )
        cur.execute("SELECT temperature FROM telemetry WHERE device_id = 'sensor-min';")
        assert float(cur.fetchone()[0]) == -999.99

def test_fallo_declarado_valor_nulo(db_connection):
    with db_connection.cursor() as cur:
        with pytest.raises(errors.NotNullViolation):
            cur.execute(
                "INSERT INTO telemetry (device_id, timestamp, temperature) VALUES (%s, NOW(), %s)",
                (None, 25.00) 
            )
