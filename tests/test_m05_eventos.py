
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

    coleccion.delete_many({})
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
    resultado = coleccion_eventos.find_one(
        {"eventId": "falso"}
    )

    assert resultado is None


def test_fallo_declarado_documento_invalido_rechazado(coleccion_eventos):
    evento_basura = {"type": "sensor.alert"}

    with pytest.raises(WriteError):
        coleccion_eventos.insert_one(evento_basura)
