# Documentación del Pipeline de Ingesta: Binance Data Science

**Arquitectura del Sistema**

El sistema opera mediante una arquitectura modular de cuatro componentes. La ingesta usa únicamente la API REST de Binance; Binance Vision quedó archivado como herramienta manual de recuperación y no participa en el pipeline. Las liquidaciones forzadas están fuera del alcance. Solo se persisten **7 archivos por símbolo**: 3 datasets analíticos, 3 maestros de sentimiento y 1 maestro de funding.

1. **Orquestador (`auth.py`)**: coordina los ciclos temporales, protege el pipeline con un bloqueo de ejecución (`flock`), gestiona las pausas de 1 segundo para respetar los límites de la API y calcula el delta con base en los archivos persistidos.
2. **Motor de Extracción (`fetcher.py`)**: ejecuta las peticiones HTTP a la API REST para Klines, Funding Rates y métricas de sentimiento.
3. **Almacenamiento (`storage.py`)**: centraliza la escritura atómica de CSV (archivo temporal + `os.replace`) y la detección de locks de LibreOffice. No gestiona JSON ni checkpoints.
4. **Consolidador (`consolidator.py`)**: fusiona Klines nuevas con el dataset previo, acumula los maestros de sentimiento y funding, calcula variables derivadas y entrega los datasets listos para Machine Learning. Añade `fecha_local` en hora de Ciudad de México junto a `fecha_utc`.

**Lógica de Extracción y Control de Estado**

La API REST permite reconstruir Klines y Funding Rates con varios años de historia. Las métricas de sentimiento tienen una restricción de 28 días hacia el pasado, por lo que el pipeline las captura en cada corrida y las acumula en `sentimiento_<tf>_master.csv` para construir un histórico propio. El estado se infiere de los archivos: el último `open_time_ms` del dataset define el delta de Klines, el último `fundingTime` del maestro de funding define su delta y el maestro de sentimiento se actualiza con la ventana de 28 días. Además, cada corrida compara los `open_time_ms` consecutivos contra el intervalo del timeframe y solicita los tramos faltantes para reparar huecos históricos. No se usan checkpoints. Si un endpoint falla por límite de peticiones (HTTP 429) o por parámetros inválidos, se conserva el maestro correspondiente y el pipeline continúa con los datos disponibles.

**Fuentes Utilizadas**

* **API REST Autenticada (`fapi.binance.com`)**: Klines históricas y recientes, Funding Rates, Open Interest, ratios Long/Short globales y de Traders Top, y Taker Long/Short Volume.
* **Binance Vision (archivado)**: se conserva el script en `binance_vision/backfill_vision.py` como respaldo manual. Escribe únicamente en `data/<symbol>/raw/binance_vision/` y no es leído por el pipeline.
* **Liquidaciones forzadas**: fuera de alcance. El endpoint público `allForceOrders` ya no está disponible y el método de python-binance consulta órdenes propias, no el mercado.

**Datos Extraídos en este Proyecto**

* **Klines Completas (5m, 15m y 12h)**: 3 años de velas obtenidas de la API REST. Se mantienen en memoria y se fusionan directamente en el dataset; no se guardan crudas.
* **Tasa de Financiamiento (Funding Rates)**: historial completo extraído de la API, con pagos cada 8 horas. Se acumula en `funding_rates_master.csv`.
* **Sentimiento de Mercado**: Open Interest, Global Long/Short Ratio, Top Accounts Long/Short Ratio, Top Positions Long/Short Ratio y Taker Long/Short Volume. Ventana máxima de 28 días, acumulada en `sentimiento_<tf>_master.csv`.

# Estructura de directorios

```text
data/
└── btcusdt/
    └── consolidado/
        ├── dataset_analisis_5m.csv
        ├── dataset_analisis_15m.csv
        ├── dataset_analisis_12h.csv
        ├── sentimiento_5m_master.csv
        ├── sentimiento_15m_master.csv
        ├── sentimiento_12h_master.csv
        └── funding_rates_master.csv
```

> No existen `raw/`, `checkpoints/` ni maestros de Klines en el flujo operativo. Si se usa `binance_vision/backfill_vision.py` manualmente, se crea `data/<symbol>/raw/binance_vision/` como archivo frío, ajeno al pipeline.

# Flujo de datos

```text
API REST (en memoria)                              ARCHIVOS EN consolidado/
─────────────────────────────────────────────────────────────────────────────────────────────
[klines 5m]  ──┐
[klines 15m] ──┼──► fusión con dataset previo ──► 1. dataset_analisis_5m.csv
[klines 12h] ──┘                                   2. dataset_analisis_15m.csv
                                                   3. dataset_analisis_12h.csv
[funding rates] ──► delta + merge_asof ─────────► 4. funding_rates_master.csv
[sentimiento 5m]  ──► acumulación 28d ──────────► 5. sentimiento_5m_master.csv
[sentimiento 15m] ──► acumulación 28d ──────────► 6. sentimiento_15m_master.csv
[sentimiento 12h] ──► acumulación 28d ──────────► 7. sentimiento_12h_master.csv

Cada dataset_analisis_<tf>.csv integra:
  Klines del timeframe + sentimiento_<tf>_master + funding_rates_master + variables derivadas
```

**Orden de ejecución por símbolo**

1. Actualizar `funding_rates_master.csv` con el delta desde el último `fundingTime`.
2. Para cada timeframe: leer el dataset previo, pedir Klines nuevas desde el último `open_time_ms`, detectar y pedir los huecos internos, pedir los últimos 28 días de sentimiento y acumularlos en el maestro.
3. Construir y escribir el dataset con los tres bloques alineados por timestamp.
4. Auditar filas previas, nuevas, duplicadas y cobertura de sentimiento/funding en `logs/consolidacion.log`.
