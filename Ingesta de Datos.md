# Documentación del Pipeline de Ingesta: Binance Data Science

**Arquitectura del Sistema**

El sistema opera mediante una arquitectura modular de cuatro componentes. La ingesta usa únicamente la API REST de Binance; Binance Vision quedó archivado como herramienta manual de recuperación y las liquidaciones forzadas están fuera del alcance.

1. **Orquestador (`auth.py`)**: coordina los ciclos temporales, protege el pipeline con un bloqueo de ejecución (`flock`), gestiona las pausas de 1 segundo para respetar los límites de la API y administra los bloques de descarga según el límite de cada endpoint.
2. **Motor de Extracción (`fetcher.py`)**: ejecuta las peticiones HTTP a la API REST para Klines, Funding Rates y métricas de sentimiento.
3. **Almacenamiento y Estado (`storage.py`)**: centraliza la escritura en disco con operaciones atómicas, deduplica cualquier dataset por su campo de tiempo clave (`open_time_ms`, `fundingTime`, `timestamp`) y gestiona los archivos `checkpoint_*.json` para reanudar la ingesta.
4. **Consolidador (`consolidator.py`)**: procesa los datos crudos, agrega columnas de trazabilidad, calcula variables derivadas y entrega los datasets listos para Machine Learning. Añade `fecha_local` en hora de Ciudad de México junto a `fecha_utc`.

**Lógica de Extracción y Control de Estado**

La API REST permite reconstruir Klines y Funding Rates con varios años de historia. Las métricas de sentimiento tienen una restricción de 28 días hacia el pasado, por lo que el pipeline las captura de forma recurrente y las acumula en `raw/` para construir un histórico propio. Si un endpoint falla por límite de peticiones (HTTP 429) o por parámetros inválidos, el sistema conserva el progreso en los checkpoints y lo reintenta en la siguiente ejecución.

**Fuentes Utilizadas**

* **API REST Autenticada (`fapi.binance.com`)**: Klines históricas y recientes, Funding Rates, Open Interest, ratios Long/Short globales y de Traders Top, y Taker Long/Short Volume.
* **Binance Vision (archivado)**: se conserva el script en `binance_vision/backfill_vision.py` como respaldo manual. Ya no participa en la ejecución diaria.
* **Liquidaciones forzadas**: fuera de alcance. El endpoint público `allForceOrders` ya no está disponible y el método de python-binance consulta órdenes propias, no el mercado.

**Datos Extraídos en este Proyecto**

* **Klines Completas (15m y 12h)**: 3 años de velas obtenidas de la API REST.
* **Tasa de Financiamiento (Funding Rates)**: historial completo extraído de la API, con pagos cada 8 horas.
* **Sentimiento de Mercado**: Open Interest, Global Long/Short Ratio, Top Accounts Long/Short Ratio, Top Positions Long/Short Ratio y Taker Long/Short Volume. Ventana máxima de 28 días, acumulada en el archivo local.

# Estructura de directorios

```text
data/
└── btcusdt/
    ├── raw/
    │   ├── binance_vision/          # archivo frío, ya no se lee en el pipeline
    │   └── api_rest/
    │       ├── api_rest_klines_15m.csv / .json
    │       ├── api_rest_klines_12h.csv / .json
    │       ├── api_rest_funding_rate.csv / .json
    │       ├── api_rest_open_interest_15m.csv / .json
    │       ├── api_rest_global_ls_15m.csv / .json
    │       ├── api_rest_top_ls_accounts_15m.csv / .json
    │       ├── api_rest_top_ls_positions_15m.csv / .json
    │       └── api_rest_taker_vol_15m.csv / .json
    ├── checkpoints/
    │   ├── checkpoint_api_rest_klines_15m.json
    │   ├── checkpoint_api_rest_klines_12h.json
    │   └── checkpoint_api_rest_funding_rate.json
    └── consolidado/
        ├── klines_15m_master.csv
        ├── klines_12h_master.csv
        ├── funding_rates_master.csv
        ├── sentimiento_15m_master.csv
        ├── sentimiento_12h_master.csv
        ├── dataset_analisis_15m.csv
        └── dataset_analisis_12h.csv
```

# Flujo de datos

```text
FUENTES CRUDAS (raw/)                                      ARCHIVOS EN consolidado/
─────────────────────────────────────────────────────────────────────────────────────────────
[api_rest_klines_15m]                     ───► 1. klines_15m_master.csv
[api_rest_klines_12h]                     ───► 2. klines_12h_master.csv
[api_rest_funding_rate]                   ───► 3. funding_rates_master.csv
[api_rest_sentimiento (5 métricas 15m)]   ───► 4. sentimiento_15m_master.csv
[api_rest_sentimiento (5 métricas 12h)]   ───► 5. sentimiento_12h_master.csv
                                                          │
   ┌──────────────────────────────────────────────────────┘
   ▼
Fusión horizontal de [1] + [3] + [4]           ───► 6. dataset_analisis_15m.csv
Fusión horizontal de [2] + [3] + [5]           ───► 7. dataset_analisis_12h.csv
```
