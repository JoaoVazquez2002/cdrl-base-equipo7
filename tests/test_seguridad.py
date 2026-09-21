import pytest
import psycopg2
from tests.test_db import get_connection

def test_usuario_lectura_no_puede_insertar():
    """El rol de solo lectura debe fallar si intenta escribir datos."""
    conn = get_connection("DB_USER_READ", "DB_PASS_READ")
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("CREATE TABLE tabla_ilegal (id INT);")
    conn.close()

def test_usuario_escritura_no_puede_eliminar_esquemas():
    """El rol de escritura no tiene permisos de DDL destructivos."""
    conn = get_connection("DB_USER_WRITE", "DB_PASS_WRITE")
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("DROP SCHEMA public CASCADE;")
    conn.close()

def test_usuario_operacion_no_puede_crear_roles():
    """El rol de operación es limitado y no debe poder crear nuevos usuarios."""
    conn = get_connection("DB_USER_OP", "DB_PASS_OP")
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("CREATE ROLE usuario_malicioso;")
    conn.close()