# ADR-009: Control de Acceso por Colección, Auditoría con Enmascaramiento y Remediación ante Abusos

## Estado
Aceptado

## Contexto
El sistema CDRL gestiona telemetría operativa sensible en dos motores: PostgreSQL (con roles RBAC ya establecidos en ADR-003) y MongoDB (colección `eventos_operativos`). Hasta el Hito M08, los controles de acceso NoSQL se limitaban a la autenticación del usuario administrador definido en las variables de entorno. No existía:

1. **Separación de roles por colección y operación** en MongoDB (cualquier usuario autenticado podía leer *y* escribir en cualquier colección).
2. **Un log de auditoría estructurado** que registre quién hizo qué, sobre qué recurso y con qué resultado, sin filtrar campos sensibles como contraseñas o tokens.
3. **Un mecanismo de remediación** que detecte y bloquee patrones de abuso (intentos repetidos de operaciones no autorizadas).

Este ADR define las decisiones de arquitectura para cubrir los tres puntos anteriores en el Hito M09 (Semana 10), manteniendo la regla de oro del proyecto: **cero credenciales en código, configuración exclusivamente por variables de entorno y fixtures 100 % sintéticos**.

---

## Decisiones de Arquitectura

### 1. Modelo RBAC por Colección y Operación en MongoDB

Se definen tres roles de base de datos MongoDB con privilegios mínimos necesarios, creados programáticamente en `src/m09_seguridad.py` usando el comando `createRole` sobre la base de datos `${MONGO_DB}`. Ningún nombre de usuario ni contraseña se hardcodea; todos se leen desde variables de entorno.

| Rol MongoDB           | Variable de entorno del usuario | Colecciones permitidas          | Operaciones permitidas                    |
| :-------------------- | :------------------------------ | :------------------------------ | :---------------------------------------- |
| `cdrl_reader`         | `MONGO_USER_READ`               | `eventos_operativos`            | `find`                                    |
| `cdrl_writer`         | `MONGO_USER_WRITE`              | `eventos_operativos`            | `find`, `insert`                          |
| `cdrl_auditor`        | `MONGO_USER_AUDIT`              | `audit_log`                     | `find`, `insert`                          |

**Principios de diseño:**
- El rol `cdrl_reader` **no puede** insertar, modificar ni eliminar documentos en ninguna colección.
- El rol `cdrl_writer` **no puede** leer ni modificar la colección `audit_log`, previniendo que un actor comprometido altere las trazas de sus propias acciones.
- El rol `cdrl_auditor` es de uso exclusivo del módulo de auditoría interno; no se expone a operaciones de negocio.
- El usuario administrador (`MONGO_USER` / `MONGO_PASSWORD`) conserva acceso total solo para operaciones de inicialización y mantenimiento; **no** se usa en el flujo de negocio habitual.

La creación de roles es idempotente: se verifica la existencia del rol antes de intentar crearlo, evitando errores en re-ejecuciones.

---

### 2. Diseño del Log de Auditoría con Enmascaramiento de Secretos

Toda operación sobre MongoDB (autorizada o rechazada) genera un documento en la colección `audit_log` con el siguiente esquema canónico:

```json
{
  "audit_id":   "<uuid-v4>",
  "timestamp":  "<ISO-8601 UTC>",
  "actor":      "<nombre de usuario MongoDB>",
  "action":     "<find | insert | delete | update | createRole | authenticate>",
  "resource":   "<nombre de colección o 'db' para operaciones de base de datos>",
  "outcome":    "<SUCCESS | DENIED | ERROR>",
  "detail":     "<mensaje descriptivo, sin datos sensibles>",
  "client_ip":  "<dirección IP del cliente, o 'internal'>",
  "schema_version": 1
}
```

#### 2.1 Regla de Enmascaramiento Obligatorio

Antes de persistir cualquier documento en `audit_log`, la función `mask_secrets(doc: dict) -> dict` del módulo `src/m09_seguridad.py` aplica las siguientes transformaciones sobre el documento a auditar y sobre cualquier payload adjunto:

- **Lista de campos bloqueados** (configurable vía `AUDIT_MASKED_FIELDS` en `.env`, con valor por defecto): `password`, `token`, `secret`, `api_key`, `credential`, `auth`, `passwd`, `pwd`.
- **Algoritmo**: recorrido recursivo del diccionario. Cualquier clave cuyo nombre (en minúsculas) coincida con la lista anterior es sustituida por el literal `"***REDACTED***"`.
- El enmascaramiento opera sobre una **copia profunda** del documento original (`copy.deepcopy`), garantizando que el objeto en memoria del proceso emisor no se altere.

**Garantía verificable**: los tests de auditoría (`tests/test_m09_seguridad.py`) afirman explícitamente que ningún documento recuperado de `audit_log` contiene valores reales en los campos de la lista bloqueada.

#### 2.2 Colección `audit_log`

La colección `audit_log` se crea con un validador `$jsonSchema` que exige la presencia de `audit_id`, `timestamp`, `actor`, `action`, `resource` y `outcome`. Se define un índice TTL de 90 días sobre `timestamp` para retención automática, y un índice compuesto `{ actor: 1, timestamp: -1 }` para consultas de trazabilidad por actor.

---

### 3. Estrategia de Remediación ante Abusos

Se define un mecanismo de detección y respuesta ante patrones de abuso operacional, implementado en la función `verificar_abuso(actor: str, ventana_segundos: int, umbral: int)` dentro de `src/m09_seguridad.py`.

#### 3.1 Definición de Abuso
Se considera un evento de abuso cuando un mismo `actor` acumula **≥ `umbral`** eventos con `outcome = "DENIED"` dentro de una **ventana deslizante de `ventana_segundos` segundos**. El umbral por defecto (configurable vía `ABUSE_THRESHOLD` y `ABUSE_WINDOW_SECONDS` en `.env`) es:
- `ABUSE_THRESHOLD=3` intentos fallidos
- `ABUSE_WINDOW_SECONDS=60` segundos

#### 3.2 Respuesta al Abuso Detectado
Cuando se supera el umbral, el sistema ejecuta la siguiente secuencia de remediación:

1. **Alerta en log de auditoría**: Se inserta un documento especial en `audit_log` con `action = "ABUSE_DETECTED"` y `outcome = "ALERT"`, registrando el actor, la cantidad de intentos y la ventana de tiempo. Este registro es inmutable desde la perspectiva del rol `cdrl_writer`.
2. **Revocación de sesión activa**: Se llama al comando `killAllSessions` filtrado por el nombre de usuario del actor abusivo, forzando la desconexión inmediata de todas sus sesiones MongoDB activas.
3. **Notificación a stderr**: Se emite un mensaje de alerta estructurado a `stderr` para que sea capturado por el agregador de logs del entorno (compatible con pipelines de CI y sistemas de monitoreo externos).

#### 3.3 Verificabilidad de la Remediación
El test `test_remediacion_bloqueo_tras_abuso` en `tests/test_m09_seguridad.py` simula `ABUSE_THRESHOLD + 1` intentos de operación no autorizada por un actor sintético y verifica:
- Que se inserta el documento `ABUSE_DETECTED` en `audit_log`.
- Que el campo `actor` del documento de alerta coincide con el actor sintético del fixture.
- Que el payload del documento de alerta **no contiene secretos** en texto claro.

---

## Comparación de Alternativas Consideradas

| Alternativa                                      | Razón de Descarte                                                                                        |
| :----------------------------------------------- | :------------------------------------------------------------------------------------------------------- |
| Usar MongoDB Atlas con reglas nativas de acceso  | El entorno es local/Docker sin conectividad a Atlas; incompatible con la infraestructura del proyecto.   |
| Auditoría a nivel de archivo de log del motor    | El log nativo de MongoDB requiere acceso al sistema de archivos del contenedor; no es portable ni testeable en pytest. |
| Bloqueo permanente de usuario en MongoDB         | El comando `dropUser` es destructivo e irreversible; `killAllSessions` es suficiente y reversible para el contexto académico. |
| Enmascaramiento en el consumidor (capa de API)   | Desplaza la responsabilidad al cliente; el ADR exige que el sistema de auditoría sea la única fuente de verdad. |

---

## Variables de Entorno Requeridas (nuevas en M09)

Todas se documentan en `.env.example`. Ninguna tiene valor por defecto distinto de un placeholder sintético.

| Variable                | Descripción                                                       |
| :---------------------- | :---------------------------------------------------------------- |
| `MONGO_USER_READ`       | Nombre del usuario MongoDB con rol `cdrl_reader`                  |
| `MONGO_PASS_READ`       | Contraseña del usuario `cdrl_reader` (sintética en desarrollo)    |
| `MONGO_USER_WRITE`      | Nombre del usuario MongoDB con rol `cdrl_writer`                  |
| `MONGO_PASS_WRITE`      | Contraseña del usuario `cdrl_writer` (sintética en desarrollo)    |
| `MONGO_USER_AUDIT`      | Nombre del usuario MongoDB con rol `cdrl_auditor`                 |
| `MONGO_PASS_AUDIT`      | Contraseña del usuario `cdrl_auditor` (sintética en desarrollo)   |
| `AUDIT_MASKED_FIELDS`   | Lista separada por comas de campos a enmascarar (opcional)        |
| `ABUSE_THRESHOLD`       | Número de intentos fallidos antes de activar remediación          |
| `ABUSE_WINDOW_SECONDS`  | Ventana de tiempo en segundos para conteo de intentos fallidos    |

---

## Consecuencias

- **Positivas**: Separación real de privilegios en MongoDB alineada con ADR-003 (PostgreSQL); trazabilidad completa de actores y operaciones; garantía verificable de no exposición de secretos en auditoría; mecanismo de remediación demostrable en tests automatizados.
- **Negativas / Trade-offs**: La gestión de múltiples usuarios MongoDB incrementa la complejidad operativa del `docker-compose.yml` y del script de inicialización. La creación de roles requiere que el usuario administrador ejecute el setup una sola vez antes de correr los tests.
- **Deuda técnica aceptada**: La revocación de sesión via `killAllSessions` es suficiente para el contexto académico; en producción real se complementaría con listas de acceso IP y rotación automática de credenciales via un gestor de secretos (ej. HashiCorp Vault).

## Límites y Alcance

1. Los controles RBAC de este ADR aplican exclusivamente a la base de datos `${MONGO_DB}` (colección `eventos_operativos` y `audit_log`). Otras bases de datos en el mismo servidor no están en el alcance.
2. El enmascaramiento cubre campos definidos en `AUDIT_MASKED_FIELDS`; no realiza análisis semántico de valores (p. ej., no detecta tokens JWT embebidos en cadenas arbitrarias).
3. La evidencia de ejecución queda registrada en `evidence/m09-seguridad.json`, siguiendo el patrón establecido en hitos anteriores.
