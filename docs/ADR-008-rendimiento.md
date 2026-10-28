# ADR-008: Optimización de Consultas Documentales y Paginación Estable Bajo Carga Reproducible

## Estado
Aceptado

## Contexto
El sistema CDRL recopila e ingesta flujos continuos de telemetría provenientes de múltiples dispositivos en la colección NoSQL `eventos_operativos` (MongoDB). Conforme el volumen de datos escala, se evidenciaron dos limitaciones críticas de arquitectura en la capa de lectura y consulta:

1. **Inestabilidad de Paginación ante Inserciones Concurrentes:**
   El enfoque convencional de paginación mediante desplazamiento (*offset-based pagination* utilizando `skip()` y `limit()`) asume una vista estática de los datos. Cuando nuevos sensores insertan eventos continuamente en la cabeza de la colección, el puntero de *offset* se desplaza. Esto provoca anomalías operativas severas:
   - **Duplicación de registros:** Eventos ya vistos en la página $N$ reaparecen en la página $N+1$.
   - **Omisión de registros:** Eventos recién insertados empujan registros no leídos fuera del rango visible.

2. **Degradación de Latencia en Páginas Profundas ($O(N)$):**
   Para resolver una consulta con `skip(M).limit(K)`, el motor de almacenamiento de MongoDB debe escanear, deserializar y descartar en memoria $M$ documentos antes de retornar los $K$ resultados deseados. En conjuntos de datos masivos, esto degrada drásticamente la latencia en percentiles altos ($p95$).

3. **Necesidad de Verificación Científica:**
   El rendimiento no puede asumirse como una afirmación sin sustento empírico. Se requiere un protocolo de benchmark reproducible que inyecte una carga sintética determinista, registre las condiciones del entorno y evalúe la dispersión de latencias mediante percentiles representativos ($p50$ y $p95$).

---

## Decisiones de Arquitectura

### 1. Adopción de Paginación Estable Basada en Cursores (Keyset Pagination)
Se prohíbe el uso de `skip()` para la paginación de eventos operativos y se adopta la paginación por cursor (*Keyset / Seek method*):
- Cada consulta utiliza el último identificador de clave ordenado (ej. `_id` o la tupla compuesta `(timestamp, _id)`) como ancla o cursor de paginación para la siguiente solicitud:
  ```json
  {
    "type": "temperature_reading",
    "_id": { "$lt": ObjectId("puntero_ultimo_evento") }
  }
  ```
- **Inmunidad ante Inserciones:** Al anclar la consulta al valor exacto del último registro procesado en lugar de una posición ordinal relativa, las inserciones concurrentes en cualquier punto de la colección no alteran ni desalinean los resultados subsecuentes.
- **Complejidad Constante $O(1)$:** El motor utiliza el índice para posicionarse directamente en el puntero del cursor sin recorrer registros intermedios.

### 2. Creación de Índices Compuestos Específicos
Para dar soporte óptimo tanto al filtrado operativo por tipo de sensor como al ordenamiento cronológico inverso y al cursor keyset, se definen los siguientes índices en la colección `eventos_operativos`:
- **Índice Compuesto Principal:** `{ type: 1, timestamp: -1, _id: -1 }`
- **Índice de Ordenamiento Temporal Global:** `{ timestamp: -1, _id: -1 }`
- **Índice de Idempotencia:** `{ eventId: 1 }` (Unique, heredado de ADR-005).

Esto garantiza que las consultas de paginación se resuelvan exclusivamente mediante escaneo de índice (`IXSCAN`) sin requerir ordenamiento en memoria (`SORT` stage en memoria).

### 3. Protocolo de Benchmark Reproducible y Métricas ($p50$ / $p95$)
- Se implementa un generador de carga sintética determinista en `src/m08_benchmark.py` parametrizado con semilla fija (`seed=42`) para inyectar 1,000+ documentos estructurados bajo el estándar v2 (ADR-007).
- Se ejecutan $N$ iteraciones estadísticas consecutivas midiendo la latencia mediante cronómetros de alta precisión (`time.perf_counter`).
- Se reportan formalmente:
  - **$p50$ (Mediana):** Comportamiento típico del sistema bajo carga controlada.
  - **$p95$ (Percentil 95):** Latencia en condiciones de cola (peor caso representativo sin considerar anomalías extremas).
- Se audita el entorno de ejecución (OS, CPU cores, versión de Python, versión del driver y de MongoDB).

### 4. Gobernanza de Variables de Entorno
Todas las credenciales y parámetros de conexión se leen estrictamente desde `.env` (`MONGO_URI`, `MONGO_USER`, `MONGO_PASSWORD`, `MONGO_DB`), prohibiendo terminantemente credenciales hardcodeadas en código fuente o fixtures.

---

## Comparación y Análisis de Trade-offs

| Dimensión de Análisis | Línea Base (Skip / Limit) | Propuesta Optimizada (Keyset Cursor) |
| :--- | :--- | :--- |
| **Complejidad Temporal** | $O(N)$ proporcional al desplazamiento | $O(1)$ directo al puntero del índice |
| **Estabilidad ante Inserciones** | **Inestable:** Genera duplicados y omisiones | **Totalmente Estable:** Determinista e idempotente |
| **Latencia $p95$ en Deep Pages** | Crece linealmente con el número de página | Se mantiene baja y constante |
| **Uso de CPU / Memoria Motor** | Alto (descarta documentos leídos en memoria) | Mínimo (solo lee los $K$ documentos requeridos) |
| **Navegación Arbitraria** | Permite saltar a "Página 85" arbitraria | Requiere navegación secuencial (Siguiente / Anterior) |
| **Sobrecarga de Almacenamiento** | Ninguna adicional | Mayor tamaño en disco y memoria WiredTiger por índices |
| **Penalización en Escrituras** | Mínima | Ligero incremento en latencia de `insert` (actualización de B-Tree) |

### Justificación de los Trade-offs Aceptados
- **Impacto en Escrituras vs. Lecturas:** La degradación milimétrica en la velocidad de inserción al mantener índices compuestos se justifica ampliamente por la reducción de órdenes de magnitud en la latencia de lectura y la eliminación del riesgo de saturación de memoria en consultas analíticas concurrentes.
- **Acceso Secuencial:** En aplicaciones de monitoreo de telemetría y streams operativos (*infinite scroll*, logs en tiempo real o pipelines ETL), el patrón de consumo predominante es secuencial (los eventos más recientes primero), haciendo irrelevante la necesidad de saltar a páginas intermedias arbitrarias.

---

## Límites y Alcance
1. **Alcance de Entidades:** La estrategia de paginación por cursores aplica primordialmente a la colección documental `eventos_operativos`.
2. **Direccionalidad del Cursor:** La implementación inicial optimiza la navegación descendente (eventos recientes a pasados); la navegación bidireccional reversa se implementará reutilizando el operador complementario `$gt` si un caso de uso lo requiere.
3. **Persistencia de Evidencias:** Los resultados comparativos y metadatos del entorno quedan documentados en `evidence/m08-performance.json`.
