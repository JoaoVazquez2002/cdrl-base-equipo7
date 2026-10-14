import pytest
import psycopg2
from tests.test_db import get_connection

def test_usuario_lectura_no_puede_insertar():
    """El rol de solo lectura debe fallar si intenta escribir datos o crear tablas."""
    conn = get_connection("DB_USER_READ", "DB_PASS_READ")
    conn.autocommit = True
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("CREATE TABLE tabla_ilegal (id INT);")
    conn.close()

def test_usuario_escritura_no_puede_eliminar_esquemas():
    """El rol de escritura no tiene permisos de DDL destructivos."""
    conn = get_connection("DB_USER_WRITE", "DB_PASS_WRITE")
    conn.autocommit = True
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("DROP SCHEMA public CASCADE;")
    conn.close()

def test_usuario_escritura_no_puede_borrar_registros():
    """El rol de escritura no debe tener permisos de DELETE sobre la tabla principal."""
    conn = get_connection("DB_USER_WRITE", "DB_PASS_WRITE")
    conn.autocommit = True
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("DELETE FROM telemetry WHERE device_id = 'sensor-01';")
    conn.close()

def test_usuario_operacion_no_puede_crear_roles():
    """El rol de operación es limitado y no debe poder crear nuevos usuarios ni roles."""
    conn = get_connection("DB_USER_OP", "DB_PASS_OP")
    conn.autocommit = True
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("CREATE ROLE usuario_malicioso;")
    conn.close()

def test_usuario_operacion_no_puede_leer_telemetria_directa():
    """El rol de operacion no debe poder leer directamente la tabla principal de telemetria."""
    conn = get_connection("DB_USER_OP", "DB_PASS_OP")
    conn.autocommit = True
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("SELECT * FROM telemetry;")
    conn.close()

def test_usuario_operacion_puede_leer_vista_segura():
    """El rol de operacion debe poder consultar la vista segura telemetry_operator_view sin datos sensibles."""
    conn = get_connection("DB_USER_OP", "DB_PASS_OP")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM telemetry_operator_view;")
        filas = cur.fetchall()
        assert isinstance(filas, list)
        assert len(filas) >= 1, "La vista segura debería devolver los registros del seed"
        columnas = [desc[0] for desc in cur.description]
        assert "temperature" not in columnas, "La vista segura no debe exponer la columna 'temperature'"
        assert "device_id" in columnas, "La vista debe exponer 'device_id'"
        assert "timestamp" in columnas, "La vista debe exponer 'timestamp'"
    conn.close()