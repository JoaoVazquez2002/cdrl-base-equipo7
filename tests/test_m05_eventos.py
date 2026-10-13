
import pytest
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, WriteError
from src.init_mongo import configurar_base_documental, URI, MONGO_DB


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    configurar_base_documental()


@pytest.fixture
def coleccion_eventos():
    cliente = MongoClient(URI)
    coleccion = cliente[MONGO_DB]["eventos_operativos"]

    yield coleccion

    coleccion.delete_many({
        "eventId": {"$in": ["evt_001", "evt_002"]}
    })
    cliente.close()


def test_caso_normal_insercion_valida(coleccion_eventos):
    evento = {
        "eventId": "evt_001",
        "type": "sensor.alert",
        "source": "fw",
        "timestamp": "2026-10-01T12:00:00Z",
        "payload": {"status": "up"}
    }

    resultado = coleccion_eventos.insert_one(evento)
    assert resultado.inserted_id is not None


def test_caso_limite_duplicado_idempotencia(coleccion_eventos):
    evento = {
        "eventId": "evt_002",
        "type": "sensor.alert",
        "source": "fw",
        "timestamp": "2026-10-01T12:00:00Z",
        "payload": {"status": "up"}
    }

    coleccion_eventos.insert_one(evento)

    with pytest.raises(DuplicateKeyError):
        coleccion_eventos.insert_one(evento)


def test_caso_limite_ausencia_datos(coleccion_eventos):
    resultado = coleccion_eventos.find_one({"eventId": "falso"})
    assert resultado is None


def test_fallo_declarado_documento_invalido_rechazado(coleccion_eventos):
    evento_basura = {"type": "sensor.alert"}

    with pytest.raises(WriteError):
        coleccion_eventos.insert_one(evento_basura)


def test_inicializacion_conserva_eventos_existentes(coleccion_eventos):
    evento = {
        "eventId": "evt_preservacion_test",
        "type": "sensor.alert",
        "source": "test",
        "timestamp": "2026-10-13T12:00:00Z",
        "payload": {"status": "preserve"}
    }

    coleccion_eventos.replace_one(
        {"eventId": evento["eventId"]},
        evento,
        upsert=True
    )

    configurar_base_documental()

    conservado = coleccion_eventos.find_one(
        {"eventId": "evt_preservacion_test"}
    )

    assert conservado is not None
    assert conservado["payload"]["status"] == "preserve"

    coleccion_eventos.delete_one(
        {"eventId": "evt_preservacion_test"}
    )
