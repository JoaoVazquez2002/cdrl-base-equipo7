import os
import pytest
from pymongo import MongoClient
from pymongo.errors import OperationFailure

MONGO_USER = os.getenv("MONGO_USER", "admin")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "admin123")
MONGO_DB = os.getenv("MONGO_DB", "cdrl_nosql")
MONGO_PORT = os.getenv("MONGO_PORT", "27017")
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")

URI = f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/"


@pytest.fixture
def mongo_collection():
    cliente = MongoClient(URI, serverSelectionTimeoutMS=2000)
    db = cliente[MONGO_DB]
    coleccion = db["eventos_telemetria"]

    coleccion.delete_many({})

    yield coleccion

    coleccion.delete_many({})
    cliente.close()


def test_happy_path_insercion_evento(mongo_collection):
    evento = {
        "id_usuario": 123,
        "tipo": "login",
        "dispositivo": "movil"
    }

    resultado = mongo_collection.insert_one(evento)

    assert resultado.inserted_id is not None


def test_edge_case_esquema_dinamico(mongo_collection):
    evento_complejo = {
        "id_usuario": 456,
        "tipo": "video",
        "metadata": {
            "resolucion": "1080p",
            "buffering": True
        }
    }

    mongo_collection.insert_one(evento_complejo)

    doc = mongo_collection.find_one({"id_usuario": 456})

    assert "metadata" in doc


def test_edge_case_busqueda_inexistente(mongo_collection):
    doc = mongo_collection.find_one({"tipo": "evento_falso"})

    assert doc is None


def test_fallo_declarado_credenciales_invalidas():
    uri_falsa = f"mongodb://falso:falso@{MONGO_HOST}:{MONGO_PORT}/"

    cliente_falso = MongoClient(
        uri_falsa,
        serverSelectionTimeoutMS=1000
    )

    with pytest.raises(OperationFailure):
        cliente_falso[MONGO_DB].command("ping")
