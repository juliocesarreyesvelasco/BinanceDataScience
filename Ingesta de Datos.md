# Documentación del Pipeline de Ingesta: Binance Data Science

**Arquitectura del Sistema**

El sistema opera mediante una arquitectura modular de cuatro componentes. La ingesta usa únicamente la API REST de Binance; Binance Vision quedó archivado como herramienta manual de recuperación y no participa en el pipeline. Las liquidaciones forzadas están fuera del alcance. Solo se persisten **7 archivos por símbolo**: 3 datasets analíticos, 3 maestros de sentimiento y 1 maestro de funding.

1. **Orquestador (`auth.py`)**: coordina los ciclos temporales, protege el pipeline con un bloqueo de ejecución (`flock`), gestiona las pausas para respetar los límites de la API, planifica el delta de sentimiento y calcula el delta con base en los archivos persistidos.
2. **Motor de Extracción (`fetcher.py`)**: ejecuta las peticiones HTTP a la API REST para Klines, Funding Rates y métricas de sentimiento, con reintentos y backoff exponencial ante HTTP 418/429.
3. **Almacenamiento (`storage.py`)**: centraliza la escritura atómica de CSV (archivo temporal + `os.replace`) y la detección de locks de LibreOffice. No gestiona JSON ni checkpoints.
4. **Consolidador (`consolidator.py`)**: fusiona Klines nuevas con el dataset previo, acumula los maestros de sentimiento y funding, calcula variables derivadas y entrega los datasets listos para Machine Learning. Añade `fecha_local` en hora de Ciudad de México junto a `fecha_utc`.

**Lógica de Extracción y Control de Estado**

La API REST permite reconstruir Klines y Funding Rates con varios años de historia. Las métricas de sentimiento tienen una restricción de 28 días hacia el pasado, por lo que el pipeline las acumula en `sentimiento_<tf>_master.csv` para construir un histórico propio. El estado se infiere de los archivos: el último `open_time_ms` del dataset define el delta de Klines, el último `fundingTime` del maestro de funding define su delta y el último `timestamp` del maestro de sentimiento define su delta. Además, cada corrida compara los timestamps consecutivos contra el intervalo del timeframe y solicita los tramos faltantes para reparar huecos históricos. No se usan checkpoints. Si un endpoint falla por límite de peticiones (HTTP 429/418) se reintenta con backoff; si persiste, se conserva el maestro correspondiente y el pipeline continúa con los datos disponibles.

**Fuentes Utilizadas**

* **API REST Autenticada (`fapi.binance.com`)**: Klines históricas y recientes, Funding Rates, Open Interest, ratios Long/Short globales y de Traders Top, y Taker Long/Short Volume.
* **Binance Vision (archivado)**: se conserva el script en `binance_vision/backfill_vision.py` como respaldo manual. Escribe únicamente en `data/<symbol>/raw/binance_vision/` y no es leído por el pipeline.
* **Liquidaciones forzadas**: fuera de alcance. El endpoint público `allForceOrders` ya no está disponible y el método de python-binance consulta órdenes propias, no el mercado.

**Datos Extraídos en este Proyecto**

* **Klines Completas (5m, 15m y 12h)**: 3 años de velas obtenidas de la API REST. Se mantienen en memoria y se fusionan directamente en el dataset; no se guardan crudas.
* **Tasa de Financiamiento (Funding Rates)**: historial completo extraído de la API, con pagos cada 8 horas. Se acumula en `funding_rates_master.csv`.
* **Sentimiento de Mercado**: Open Interest, Global Long/Short Ratio, Top Accounts Long/Short Ratio, Top Positions Long/Short Ratio y Taker Long/Short Volume. Retención de la API de 28 días; se ingesta de forma incremental y se acumula en `sentimiento_<tf>_master.csv`.

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
[sentimiento 5m]  ──► delta + huecos (28d) ─────► 5. sentimiento_5m_master.csv
[sentimiento 15m] ──► delta + huecos (28d) ─────► 6. sentimiento_15m_master.csv
[sentimiento 12h] ──► delta + huecos (28d) ─────► 7. sentimiento_12h_master.csv

Cada dataset_analisis_<tf>.csv integra:
  Klines del timeframe + sentimiento_<tf>_master + funding_rates_master + variables derivadas
```

**Orden de ejecución por símbolo**

1. Actualizar `funding_rates_master.csv` con el delta desde el último `fundingTime`.
2. Para cada timeframe: leer el dataset previo, pedir Klines nuevas desde el último `open_time_ms`, detectar y pedir los huecos internos, y actualizar el maestro de sentimiento con el delta desde su último `timestamp` (más solape y huecos dentro de la retención).
3. Construir y escribir el dataset con los tres bloques alineados por timestamp.
4. Auditar filas previas, nuevas, duplicadas y cobertura de sentimiento/funding en `logs/consolidacion.log`.

## Optimización de la ingesta de sentimiento

El maestro de sentimiento se actualiza de forma **incremental**, no con la ventana completa en cada corrida:

- **Delta:** se parte de `max(timestamp)` del maestro menos un solape de 2 periodos, con piso en `ahora - 28 días`.
- **Chunking:** cada petición cubre hasta 480 puntos (`PUNTOS_POR_LOTE_SENTIMIENTO`), por debajo del `limit=500` de la API. Esto da ~1.67 días en 5m, 5 días en 15m y un solo bloque para 12h.
- **Huecos:** se detectan timestamps faltantes dentro de la retención (incluido un hueco inicial) y se piden solo esos tramos.
- **Recuperación diaria:** en la **primera corrida de cada día** (cuando el maestro aún no tiene datos de hoy), se re-pide la ventana completa de 28 días para autocorregir fallos silenciosos y rellenar `NaN` recuperables. Las corridas siguientes del mismo día son incrementales. El día se define por medianoche en `America/Mexico_City`.
- **Escritura condicional:** si no hay timestamps nuevos ni valores corregidos, el CSV no se reescribe.
- **Robustez:** reintentos con backoff exponencial ante HTTP 418/429.
- **Métrica de log:** `rangos`, `peticiones`, `nuevos`, `actualizados` y si hubo `escritura`. `nuevos` cuenta timestamps realmente nuevos, no filas re-descargadas.

Impacto medido (corrida diaria, por símbolo): de ~190 peticiones y 35 s de pausa a ~15 peticiones y ~0.75 s. El arranque en frío de 5m baja de 140 a 85 peticiones.
