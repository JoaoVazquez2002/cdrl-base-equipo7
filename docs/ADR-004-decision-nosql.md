# ADR-004: Selección de Familia NoSQL para Telemetría

## Contexto
El sistema CDRL genera 250,000 eventos diarios de telemetría operativa con esquemas variables. Procesar esta ingesta masiva en el motor relacional principal (PostgreSQL) degradaría el rendimiento de las transacciones académicas críticas. Se requiere seleccionar una familia NoSQL adecuada para derivar esta carga.

## Criterios y Matriz Ponderada
Evaluamos las 4 familias NoSQL basándonos en consultas, escala, consistencia, costo y fallos.

| Criterio (Peso) | Document (MongoDB) | Graph (Neo4j) | Column (Cassandra) | Object (S3) |
| :--- | :--- | :--- | :--- | :--- |
| **Consultas** (30%) | **4** (Filtros por rango/estado dinámicos) | 2 | 3 | 1 |
| **Escala/Escritura** (25%) | **3** (Sharding nativo) | 2 | 4 (Escritura extrema) | 3 |
| **Consistencia** (15%) | **3** (Eventual configurable) | 3 | 2 | 2 |
| **Costo/Operación** (15%)| **3** (Moderado, fácil en Docker) | 2 | 2 (Infraestructura pesada)| 4 |
| **Tolerancia a fallos** (15%)| **3** (Réplicas automáticas) | 2 | 4 | 4 |
| **PUNTAJE TOTAL** | **3.30** | 2.15 | 3.05 | 2.50 |

*(Escala de 1 a 4, donde 4 es el mejor ajuste al caso de uso CDRL).*

## Alternativa Descartada
**Descartamos la familia Column Store (ej. Cassandra)**. Aunque ofrece un rendimiento superior en ingesta pura de datos (escala = 4), su esquema de consultas por clave de partición es demasiado rígido. Los eventos operativos del CDRL requieren consultas flexibles (por tipo, dispositivo, rango de tiempo), para lo cual Document Store es mucho más eficiente.

## Decisión
Seleccionamos **Document Store (MongoDB)**. 
Conecta perfectamente con nuestras necesidades: permite consultas flexibles sobre JSON/BSON, soporta la escala de 250,000 eventos mediante sharding, maneja esquemas dinámicos para los fallos, y ofrece un equilibrio aceptable de costos y consistencia eventual sin requerir la infraestructura masiva de un Column Store.