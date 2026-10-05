# ADR-005 Estrategia de Validación e Índices Documentales

## Contexto
El sistema procesa eventos operativos masivos. Una ingesta sin controles corromperá el formato NoSQL. Necesitamos rechazar datos mal formados, evitar duplicados por fallos de red y acelerar las consultas críticas.

## Decisiones y Justificación
1. Validación Estricta ($jsonSchema) 
   - Se exigen obligatoriamente los campos `eventId`, `type`, `source`, `timestamp` y `payload`.
   - Por qué Garantiza la integridad; los documentos sin estos campos son rechazados (WriteError).
2. Índice de Idempotencia (Único)
   - Se creó un índice `unique=True` sobre el campo `eventId`.
   - Por qué Evita la duplicación de registros si un sensor reintenta enviar el mismo evento.
3. Índice Compuesto (type + timestamp)
   - Se creó un índice compuesto para las consultas operativas.
   - Por qué Evita el escaneo de millones de documentos al filtrar eventos específicos por fecha.