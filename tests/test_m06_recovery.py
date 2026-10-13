import pytest
from src.m06_recovery import get_db, evolucionar_esquema, auditar_operacion, recuperar_desde_fixture

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


def test_sanitizacion_secreta_anidada(db):
    auditar_operacion(
        db,
        "test_actor",
        "RESTORE",
        "evt",
        "SUCCESS",
        {
            "metadata": {
                "password": "no_debe_guardarse",
                "token": "token_privado"
            }
        }
    )

    log = db["audit_logs"].find_one(
        {"actorId": "test_actor", "action": "RESTORE"},
        sort=[("_id", -1)]
    )

    assert log["details"]["metadata"]["password"] == "***** [SANITIZED] *****"
    assert log["details"]["metadata"]["token"] == "***** [SANITIZED] *****"
