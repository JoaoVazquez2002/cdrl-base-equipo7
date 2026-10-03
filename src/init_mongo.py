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
    db = cliente[MONGO_DB]
    
    if "eventos_operativos" in db.list_collection_names():
        db.drop_collection("eventos_operativos")

    # 1. Esquema de Validación Estricta
    validador = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["eventId", "type", "source", "timestamp", "payload"],
            "properties": {
                "eventId": {"bsonType": "string"},
                "type": {"bsonType": "string"},
                "source": {"bsonType": "string"},
                "timestamp": {"bsonType": "string"},
                "payload": {"bsonType": "object"}
            }
        }
    }
    db.create_collection("eventos_operativos", validator=validador)

    # 2. Índices para consultas del ADR e Idempotencia
    db.eventos_operativos.create_index("eventId", unique=True)
    db.eventos_operativos.create_index([("type", 1), ("timestamp", -1)])

    print("=> Base documental configurada exitosamente.")
    cliente.close()

if __name__ == "__main__":
    configurar_base_documental()