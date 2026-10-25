import os
import pytest
from pymongo.errors import WriteError
from src.m07_migration import (
    get_db,
    evolucionar_esquema_v2,
    migrar_documentos_v2,
    revertir_migracion_v1,
    cargar_fixture_evolucion,
)


@pytest.fixture(scope="module")
def db():
    """Inicializa la conexión y el validador v2 para las pruebas de evolución."""
    database = get_db()
    evolucionar_esquema_v2(database)
    yield database
    database["eventos_operativos"].delete_many({"eventId": {"$regex": "^m07_test_"}})


@pytest.fixture(autouse=True)
def limpiar_coleccion_m07(db):
    """Limpia los eventos sintéticos antes y después de cada prueba individual."""
    db["eventos_operativos"].delete_many({"eventId": {"$regex": "^m07_test_"}})
    yield
    db["eventos_operativos"].delete_many({"eventId": {"$regex": "^m07_test_"}})


def test_caso_normal_migracion_v1_a_v2(db):
    """
    1. CASO NORMAL:
    Verifica que documentos en formato v1 migren correctamente a v2, enriqueciendo
    schemaVersion, firmwareVersion, status y estructurando payload.metrics,
    mientras se garantiza la lectura compatible (Dual-Read) conservando campos raíz.
    """
    coleccion = db["eventos_operativos"]
    doc_v1 = {
        "eventId": "m07_test_normal_01",
        "type": "telemetry",
        "source": "sensor-alpha-01",
        "timestamp": "2026-10-25T10:00:00Z",
        "payload": {
            "temperature": 21.4
        }
    }
    coleccion.insert_one(doc_v1)

    resultado = migrar_documentos_v2(db)
    assert resultado["matched"] >= 1
    assert resultado["modified"] >= 1

    doc_migrado = coleccion.find_one({"eventId": "m07_test_normal_01"})
    assert doc_migrado is not None

    # Verificación de nuevos campos v2
    assert doc_migrado.get("schemaVersion") == 2
    assert doc_migrado.get("firmwareVersion") is not None
    assert doc_migrado.get("status") == "OPERATIONAL"
    assert "metrics" in doc_migrado["payload"]
    assert doc_migrado["payload"]["metrics"]["temperature"] == 21.4
    assert doc_migrado["payload"]["metrics"]["unit"] == "celsius"

    # Verificación de compatibilidad hacia atrás (Dual-Read)
    assert doc_migrado["payload"]["temperature"] == 21.4


def test_caso_limite_idempotencia_migracion_repetida(db):
    """
    2. CASO LÍMITE (A) - IDEMPOTENCIA:
    Verifica que ejecutar la migración múltiples veces consecutivas (ej. 2 o más veces)
    sea una operación segura e inocua (no-op), sin alterar datos ya migrados ni duplicar registros.
    """
    coleccion = db["eventos_operativos"]
    doc_v1 = {
        "eventId": "m07_test_idempotencia_02",
        "type": "telemetry",
        "source": "sensor-beta-02",
        "timestamp": "2026-10-25T10:05:00Z",
        "payload": {
            "temperature": 23.8
        }
    }
    coleccion.insert_one(doc_v1)

    # Primera pasada de migración
    res_1 = migrar_documentos_v2(db)
    assert res_1["modified"] >= 1

    doc_primera_pasada = coleccion.find_one({"eventId": "m07_test_idempotencia_02"})
    assert doc_primera_pasada["schemaVersion"] == 2

    # Segunda pasada de migración: debe ser no-op
    res_2 = migrar_documentos_v2(db)
    assert res_2["matched"] == 0
    assert res_2["modified"] == 0

    doc_segunda_pasada = coleccion.find_one({"eventId": "m07_test_idempotencia_02"})
    assert doc_segunda_pasada["schemaVersion"] == 2
    assert doc_segunda_pasada["payload"]["metrics"]["temperature"] == 23.8
    assert "metrics" not in doc_segunda_pasada["payload"]["metrics"]


def test_caso_limite_rollback_sin_perdida_de_datos(db):
    """
    3. CASO LÍMITE (B) - ROLLBACK SIN PÉRDIDA:
    Verifica que la función de reversión retrotraiga documentos v2 a v1,
    removiendo metadatos v2 (schemaVersion, firmwareVersion, status, payload.metrics)
    sin eliminar documentos ni corromper las métricas esenciales heredadas en payload.
    """
    coleccion = db["eventos_operativos"]
    doc_v1 = {
        "eventId": "m07_test_rollback_03",
        "type": "humidity",
        "source": "sensor-gamma-03",
        "timestamp": "2026-10-25T10:10:00Z",
        "payload": {
            "humidity": 55.0
        }
    }
    coleccion.insert_one(doc_v1)
    migrar_documentos_v2(db)

    total_antes_rollback = coleccion.count_documents({"eventId": "m07_test_rollback_03"})
    assert total_antes_rollback == 1

    # Ejecutar rollback a v1
    res_rollback = revertir_migracion_v1(db)
    assert res_rollback["modified"] >= 1

    # Cero pérdida de registros
    total_despues_rollback = coleccion.count_documents({"eventId": "m07_test_rollback_03"})
    assert total_despues_rollback == total_antes_rollback

    doc_revertido = coleccion.find_one({"eventId": "m07_test_rollback_03"})
    assert doc_revertido is not None
    assert "schemaVersion" not in doc_revertido
    assert "firmwareVersion" not in doc_revertido
    assert "status" not in doc_revertido
    assert "metrics" not in doc_revertido["payload"]
    assert doc_revertido["payload"]["humidity"] == 55.0


def test_fallo_declarado_documento_invalido_rechazado(db):
    """
    4. FALLO DECLARADO:
    Verifica que la inserción de un documento que viola la validación de esquema
    definida en MongoDB (campos requeridos faltantes o tipos inválidos) sea rechazada
    arrojando la excepción esperada (WriteError).
    """
    coleccion = db["eventos_operativos"]
    documento_invalido = {
        "eventId": "m07_test_fallo_04",
        "type": "malformed.event"
    }

    with pytest.raises(WriteError):
        coleccion.insert_one(documento_invalido)
