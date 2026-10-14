import os
import pytest
from src.m06_recovery import (
    get_db,
    evolucionar_esquema,
    auditar_operacion,
    recuperar_desde_fixture,
    simular_falla_y_recuperar,
)

@pytest.fixture(scope="module")
def db():
    database = get_db()
    evolucionar_esquema(database)
    yield database
    database["eventos_operativos"].delete_many({"eventId": {"$regex": "^test_"}})
    database["audit_logs"].delete_many({"actorId": "test_actor"})

def test_caso_normal_coexistencia_v1_v2(db):
    # Coexistencia: v1 sin campos nuevos, v2 con campos nuevos
    doc_v1 = {"eventId": "test_v1", "type": "telemetry", "timestamp": "2026"}
    doc_v2 = {"eventId": "test_v2", "type": "telemetry", "timestamp": "2026", "schemaVersion": 2, "firmwareVersion": "2.0"}
    assert db["eventos_operativos"].insert_one(doc_v1).inserted_id
    assert db["eventos_operativos"].insert_one(doc_v2).inserted_id

def test_caso_limite_auditoria_sin_secretos(db):
    auditar_operacion(db, "test_actor", "RESTORE", "evt", "SUCCESS", {"password": "supersecret"})
    log = db["audit_logs"].find_one({"actorId": "test_actor", "action": "RESTORE"})
    assert log["details"]["password"] == "***** [SANITIZED] *****"

def test_auditoria_oculta_token_anidado(db):
    """Verifica que el filtro de auditoría ofusque recursivamente un token dentro de un objeto anidado."""
    detalles_anidados = {"user": {"token": "secret123", "role": "operator"}}
    auditar_operacion(db, "test_actor", "AUTH_LOGIN", "session", "SUCCESS", detalles_anidados)
    log = db["audit_logs"].find_one({"actorId": "test_actor", "action": "AUTH_LOGIN"})
    assert log is not None
    assert log["details"]["user"]["token"] == "***** [SANITIZED] *****"
    assert log["details"]["user"]["role"] == "operator"

def test_caso_limite_recuperacion_idempotente(db):
    recuperar_desde_fixture(db, "fixtures/telemetry_backup.json")
    conteo_1 = db["eventos_operativos"].count_documents({})
    # Correr restore por segunda vez NO debe duplicar
    recuperar_desde_fixture(db, "fixtures/telemetry_backup.json")
    conteo_2 = db["eventos_operativos"].count_documents({})
    assert conteo_1 == conteo_2

def test_fallo_declarado_archivo_inexistente(db):
    with pytest.raises(FileNotFoundError):
        recuperar_desde_fixture(db, "fixtures/no_existe.json")
    log = db["audit_logs"].find_one({"action": "RESTORE", "result": "FAILED"})
    assert log is not None

def test_simulacion_perdida_controlada_y_recuperacion(db):
    """Verifica que la pérdida controlada se recupere consistentemente y registre métricas en artifacts."""
    metricas = simular_falla_y_recuperar(db)
    assert metricas["consistent"] is True
    assert metricas["duration_seconds"] >= 0
    assert os.path.exists("artifacts/recovery_metrics.txt")
    with open("artifacts/recovery_metrics.txt", "r", encoding="utf-8") as f:
        contenido = f.read()
    assert "RECOVERY METRICS" in contenido
    assert "Consistencia de datos: OK / CONSISTENTE" in contenido
