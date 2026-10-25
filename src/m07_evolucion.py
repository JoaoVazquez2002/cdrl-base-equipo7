"""
Módulo de compatibilidad para ADR-007 y evidencia m07-evolucion.json.
Reenvía todas las llamadas a src/m07_migration.py.
"""
from src.m07_migration import (
    get_mongo_uri,
    get_db,
    evolucionar_esquema_v2,
    migrar_documentos_v2,
    revertir_migracion_v1,
    cargar_fixture_evolucion,
    main,
)

if __name__ == "__main__":
    main()
