# ADR-007: Versionado y Migración Compatible de Documentos NoSQL

## Contexto
El sistema CDRL almacena eventos de telemetría de sensores en la colección NoSQL `eventos_operativos` (MongoDB). Con la evolución funcional del sistema, se requiere transicionar de un formato v1 (esquema inicial plano y sin control de versión explícito) hacia un formato v2 enriquecido (que incorpora `schemaVersion`, `firmwareVersion`, estado operativo y métricas estructuradas).

En un entorno de producción distribuido, los servicios consumidores no pueden actualizarse todos de forma simultánea. Por lo tanto, el sistema debe garantizar **cero tiempo de inactividad** y evitar romper la compatibilidad con consumidores existentes (legacy) que continúen consultando la base de datos durante y después de la migración.

## Decisiones

### 1. Patrón Expand & Contract (Lectura Dual)
Adoptamos el patrón arquitectónico *Expand & Contract* para garantizar compatibilidad hacia atrás:
- **Fase Expand (Transición actual):** Se actualiza la validación `$jsonSchema` en caliente mediante `collMod`. Los nuevos campos (`schemaVersion`, `firmwareVersion`, `status`, `payload.metrics`) se definen como **opcionales** en la validación de MongoDB, permitiendo la coexistencia pacífica de documentos v1 y v2 en la misma colección.
- **Lectura Dual (Backward Compatibility):**
  - Los documentos v2 conservan en su `payload` los campos heredados (ej. `payload.temperature`) de forma simultánea a la nueva estructura (`payload.metrics.temperature`).
  - La capa de lectura y serialización aplica tolerancia de esquema: si un documento carece de `schemaVersion`, se interpreta como `v1` de manera predeterminada.
  - Los consumidores v1 pueden leer registros v2 sin fallos de parseo, ya que los campos clave esperados continúan presentes en la ubicación esperada.
- **Fase Contract (Límite futuro):** La remoción de campos obsoletos solo se ejecutará cuando todas las aplicaciones y servicios consumidores hayan migrado a v2.

### 2. Idempotencia y Repetibilidad de la Migración
- Los scripts de migración utilizan operaciones en bloque (`bulk_write` / `UpdateMany`) aplicando un filtro discriminador estricto (`schemaVersion: {"$exists": False}` o `schemaVersion: {"$lt": 2}`).
- Reejecutar el proceso de migración múltiples veces es una operación segura e inocua (*no-op*), garantizando idempotencia total frente a reintentos o despliegues fallidos.

### 3. Mecanismo de Rollback Verificado
- Se define un procedimiento automatizado de reversión que permite retrotraer el esquema y los documentos modificados al estado v1 previo en caso de incidente operacional.
- El rollback degrada de forma segura los documentos v2 al formato v1 conservando los datos esenciales, o restaura la colección al estado base validado mediante tests automatizados en Pytest.

### 4. Seguridad y Parametrización
- Todos los scripts de migración, tests y fixtures se alimentan exclusivamente mediante variables de entorno (`.env`), evitando credenciales, tokens o datos sensibles embebidos.

## Límites y Alcance de la Implementación
1. **Alcance de Colección:** La estrategia de versionado y compatibilidad dual aplica únicamente a la colección `eventos_operativos`.
2. **Horizonte de Compatibilidad:** La compatibilidad con v1 se mantendrá activa durante toda la fase de transición. No se eliminarán campos de v1 mientras existan consumidores activos documentados.
3. **No Pérdida de Datos en Rollback:** La reversión conserva métricas troncales pero descarta atributos sintéticos propios de v2 que no posean equivalente en v1.
4. **Procesamiento por Lotes:** La migración opera sobre lotes de documentos dentro de MongoDB; no implementa captura de cambios en tiempo real (Change Streams / CDC distribuido) en esta fase.
