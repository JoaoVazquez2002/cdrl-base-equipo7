# ADR-006: Evolución, Auditoría y Recuperación NoSQL

## Contexto
Durante las semanas anteriores se detectaron problemas de pérdida de datos en el despliegue (`drop_collection`) y duplicidad al reejecutar la ingesta. Se requería una estrategia para soportar evolución del formato de sensores, auditar fallas y recuperar backups sin corromper el entorno.

## Decisiones
1. **Evolución sin destrucción:** Se reemplazó `drop_collection` por `collMod` (modificación de esquema en caliente). Esto soporta documentos v1 (sin versión) y v2 (con `schemaVersion`) coexistiendo en la misma colección.
2. **Auditoría higienizada recursiva:** Se implementó `sanitizar_detalles` en `audit_logs` con recorrido profundo recursivo. Esto intercepta y ofusca claves sensibles como `password`, `token`, `secret`, `api_key` tanto en el nivel superior como en estructuras anidadas arbitrarias.
3. **Recuperación Idempotente (Upsert):** El mecanismo de restore ahora utiliza `bulk_write` con operaciones `UpdateOne(upsert=True)`. Esto permite que el comando de recuperación se ejecute N veces garantizando el mismo estado, eliminando la duplicidad histórica.
4. **Simulación de Falla Controlada y Métricas:** Se implementó `simular_falla_y_recuperar()` que inyecta una pérdida controlada de eventos, audita el incidente, mide el tiempo exacto de restauración en milisegundos y valida la consistencia final, registrando los resultados en `artifacts/recovery_metrics.txt`.