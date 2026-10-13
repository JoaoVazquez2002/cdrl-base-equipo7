
import os
from pymongo import MongoClient

MONGO_USER = os.getenv("MONGO_USER", "admin")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "admin123")
MONGO_DB = os.getenv("MONGO_DB", "cdrl_nosql")
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = os.getenv("MONGO_PORT", "27017")
URI = f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/"


def configurar_base_documental():
    cliente = MongoClient(URI)

    try:
        db = cliente[MONGO_DB]

        validador = {
            "$jsonSchema": {
                "bsonType": "object",
                "required": [
                    "eventId", "type", "source", "timestamp", "payload"
                ],
                "properties": {
                    "eventId": {"bsonType": "string"},
                    "type": {"bsonType": "string"},
                    "source": {"bsonType": "string"},
                    "timestamp": {"bsonType": "string"},
                    "payload": {"bsonType": "object"}
                }
            }
        }

        if "eventos_operativos" not in db.list_collection_names():
            db.create_collection(
                "eventos_operativos",
                validator=validador,
                validationLevel="strict",
                validationAction="error"
            )
        else:
            db.command({
                "collMod": "eventos_operativos",
                "validator": validador,
                "validationLevel": "strict",
                "validationAction": "error"
            })

        coleccion = db["eventos_operativos"]

        coleccion.create_index("eventId", unique=True)
        coleccion.create_index([("type", 1), ("timestamp", -1)])

        print("=> Base documental configurada sin eliminar eventos existentes.")

    finally:
        cliente.close()


if __name__ == "__main__":
    configurar_base_documental()
