# Arquitectura y Pipeline de Extracción Institucional de Binance

Este documento detalla la arquitectura técnica, lógica operativa y especificaciones de ingesta implementadas en el sistema de recolección de criptoactivos para Data Science y Modelado Predictivo.

> **Alcance actual:** la ingesta usa únicamente la API REST. Binance Vision quedó archivado en `binance_vision/` como respaldo manual y **no participa** en el pipeline. El sistema persiste solo **7 archivos por símbolo**: 3 datasets analíticos, 3 maestros de sentimiento y 1 maestro de funding. No se guardan Klines crudas, maestros de Klines ni checkpoints. Las liquidaciones forzadas se descartaron del proyecto.

---

## 1. Topología de Fuentes de Datos

```text
                               ┌────────────────────────────────────────┐
                               │            API REST AUTENTICADA        │
                               │             (fapi.binance.com)         │
                               └──────────────────┬─────────────────────┘
                                                  │
                                     Extracción de datos históricos y recientes
                                     • Klines 5m, 15m y 12h
                                     • Funding Rates (cada 8h)
                                     • Ratios de sentimiento (ventana 28d)
                                                  │
                                                  ▼
                               ┌────────────────────────────────────────┐
                               │     ORQUESTADOR + FETCHER (en memoria) │
                               │  • Delta calculado desde los archivos  │
                               │  • Sin archivos crudos persistentes    │
                               └──────────────────┬─────────────────────┘
                                                  │
                                                  ▼
                               ┌────────────────────────────────────────┐
                               │         MÓDULO CONSOLIDADOR            │
                               │  • Deduplicación por timestamp         │
                               │  • Alineación asíncrona temporal       │
                               │  • Feature Engineering derivado        │
                               │  • Hora UTC + hora local               │
                               └──────────────────┬─────────────────────┘
                                                  │
                                                  ▼
                               ┌────────────────────────────────────────┐
                               │        7 ARCHIVOS CSV POR SÍMBOLO      │
                               │           (consolidado/)               │
                               └────────────────────────────────────────┘
```

### A. API REST Autenticada (fapi.binance.com)

- **Protocolo:** HTTPS con inyección del encabezado `X-MBX-APIKEY` y firma criptográfica HMAC-SHA256.
- **Propósito:** obtención de Klines, tasas de fondeo y sentimiento de mercado reciente.
- **Límites operativos:** 2,400 unidades de peso por minuto para cuentas autenticadas estándar.
- **Restricción de ventana (sentimiento):** Binance solo permite consultar los últimos 28-30 días calendario de `openInterestHist`, `globalLongShortAccountRatio`, `topLongShortAccountRatio`, `topLongShortPositionRatio` y `takerlongshortRatio`. El pipeline ingesta el delta desde el último `timestamp` del maestro (con solape de 2 periodos y piso en 28 días) y lo acumula; una vez por semana re-pide la ventana completa para reconciliar.
- **Klines:** la API permite reconstruir varios años de historia paginando por bloques. El pipeline usa 30 días por lote para 5m y 15m, y 180 días por lote para 12h. Las velas se mantienen en memoria y se fusionan directamente con el dataset; no se escriben archivos crudos.

### B. Binance Vision (archivado, respaldo manual)

- Se conserva el script `binance_vision/backfill_vision.py` como herramienta autónoma de recuperación.
- Escribe únicamente `data/<symbol>/raw/binance_vision/binance_vision_klines_<tf>.csv`.
- **No** siembra `raw/api_rest`, **no** crea checkpoints y **no** es leído por el pipeline.
- Sus CSV son un archivo frío: si se necesitan para reconstruir historia, deben importarse manualmente o reemplazarse por una corrida de la API REST.
- Timeframes por defecto del script: `15m` y `12h`. Para archivar `5m`, pasar `--timeframes 5m`.

### C. Liquidaciones forzadas (fuera de alcance)

- El endpoint público `GET /fapi/v1/allForceOrders` ya devuelve HTTP 404.
- El método `futures_liquidation_orders` de python-binance apunta a `/fapi/v1/forceOrders` con firma, es decir, a las órdenes forzadas de la propia cuenta, no al mercado.
- Por decisión del proyecto, no se capturan liquidaciones ni se generan columnas relacionadas.

## 2. Lógica del Pipeline y Estado sin Checkpoints

El pipeline resuelve dos cuellos de botella: la pérdida de conexión y el bucle de re-descargas innecesarias. El estado ya no se guarda en archivos JSON; se infiere de los propios CSV persistidos.

- **Ejecución exclusiva:** `auth.py` adquiere un bloqueo `flock` sobre `logs/pipeline.lock`. Si ya hay otra corrida activa, aborta con un mensaje de error.
- **Estado por timeframe:** el último `open_time_ms` del `dataset_analisis_<tf>.csv` define desde dónde pedir Klines nuevas. Si el dataset no existe, se solicita la ventana completa de 3 años.
- **Estado de funding:** el último `fundingTime` del `funding_rates_master.csv` define el delta. Si el maestro no existe, se solicitan 3 años.
- **Estado de sentimiento:** el último `timestamp` de `sentimiento_<tf>_master.csv` define el delta. Cada corrida solicita desde `max(timestamp) - 2*intervalo` (con piso en `ahora - 28 días`), detecta y repara huecos dentro de la retención, y hace upsert con `combine_first`. En la **primera corrida de cada día** (medianoche local) se re-pide la ventana completa de 28 días como recuperación; las corridas siguientes del mismo día son incrementales.
- **Modo Backfill:** si el dataset no existe, o si su primer registro es posterior a la ventana de 3 años, se rellena el tramo faltante. Al finalizar, el dataset queda completo.
- **Modo Incremental:** en corridas normales solo se solicita el delta desde el último `open_time_ms` hasta ahora.
- **Detección de huecos internos:** en cada corrida se comparan los `open_time_ms` consecutivos contra el intervalo del timeframe. Si falta al menos una vela, se solicita el rango faltante a la API y se rellena antes de escribir. Esto permite reparar huecos históricos sin intervención manual.
- **Pausas antifraude:** Klines y funding usan 1 segundo entre lotes (`PAUSA_SEGUNDOS = 1`); sentimiento usa 0.25 s entre lotes (`PAUSA_ENTRE_LOTES`) y backoff exponencial solo ante HTTP 418/429. El consumo se mantiene muy por debajo del techo de 2,400 unidades por minuto.
- **Tolerancia a fallos:** si falla un endpoint, se conserva el maestro correspondiente y el dataset se reconstruye con los datos disponibles. Sentimiento reintenta con backoff y, si persiste el fallo, `combine_first` conserva el valor previo. La escritura es atómica y solo ocurre si hay datos nuevos o corregidos.

## 3. Matriz de Ingesta: Datos Extraídos vs Fuentes

| Dataset | Granularidad | Fuente Primaria | Ventana Histórica | Estrategia de Descarga |
| --- | --- | --- | --- | --- |
| Klines (Velas Completas) | 5m, 15m y 12h | API REST | 3 años continuos | Paginación en lotes de 30 días (5m y 15m) y 180 días (12h); sin semilla Vision |
| Funding Rate (Tasa Fondeo) | 8 horas | API REST (`/fapi/v1/fundingRate`) | 3 años continuos | Paginación en bloques de 300 días (hasta 1,000 registros) |
| Open Interest Histórico | 5m, 15m y 12h | API REST (`/futures/data/openInterestHist`) | 28 días acumulados | Incremental + huecos; lotes de 480 puntos (~1.67 días en 5m, 5 días en 15m, 1 bloque en 12h) con `limit=500` |
| Global Long/Short Ratio | 5m, 15m y 12h | API REST (`/futures/data/globalLongShortAccountRatio`) | 28 días acumulados | Incremental + huecos; lotes de 480 puntos (~1.67 días en 5m, 5 días en 15m, 1 bloque en 12h) con `limit=500` |
| Top Trader Accounts Ratio | 5m, 15m y 12h | API REST (`/futures/data/topLongShortAccountRatio`) | 28 días acumulados | Incremental + huecos; lotes de 480 puntos (~1.67 días en 5m, 5 días en 15m, 1 bloque en 12h) con `limit=500` |
| Top Trader Positions Ratio | 5m, 15m y 12h | API REST (`/futures/data/topLongShortPositionRatio`) | 28 días acumulados | Incremental + huecos; lotes de 480 puntos (~1.67 días en 5m, 5 días en 15m, 1 bloque en 12h) con `limit=500` |
| Taker Long/Short Ratio | 5m, 15m y 12h | API REST (`/futures/data/takerlongshortRatio`) | 28 días acumulados | Incremental + huecos; lotes de 480 puntos (~1.67 días en 5m, 5 días en 15m, 1 bloque en 12h) con `limit=500` |

## 4. Proceso de Consolidación y Alineación Temporal

Para construir los datasets analíticos finales (`dataset_analisis_5m.csv`, `dataset_analisis_15m.csv` y `dataset_analisis_12h.csv`), el consolidador aplica estas operaciones:

1. **Estado desde el dataset:** lee `dataset_analisis_<tf>.csv` (columnas de Klines + `fecha_procesamiento`) como estado previo. No existen maestros de Klines.
2. **Fusión de Klines nuevas:** detecta huecos internos, solicita los tramos faltantes, deduplica y ordena por `open_time_ms`, conservando la columna `fecha_procesamiento` de las filas ya existentes.
3. **Sentimiento con columnas explícitas:** renombra las columnas de cada métrica con prefijos (`global_ls_*`, `top_accounts_*`, `top_positions_*`, `oi_*`, `taker_*`) para evitar sufijos ambiguos `_x/_y`. Cruza las 5 métricas por `timestamp`, acumula el resultado en `sentimiento_<tf>_master.csv` y luego hace un merge exacto contra `open_time_ms`.
4. **Actualización y propagación del Funding Rate:** acumula los pagos nuevos en `funding_rates_master.csv`. Como el Funding Rate se cobra cada 8 horas, mediante un cruce retrospectivo (`merge_asof`, `direction="backward"`) cada vela hereda la última tasa vigente.
5. **Hora local:** cada archivo conserva `fecha_utc` y añade `fecha_local` en `America/Mexico_City` (ISO 8601 con offset). Las claves de cruce siguen en milisegundos UTC.
6. **Escritura segura:** los CSV se escriben primero en un archivo temporal y luego se reemplazan de forma atómica. Si existe un lock de LibreOffice (`.~lock.<archivo>#`), la consolidación de ese símbolo se omite con una advertencia.

**Salidas:** 7 archivos por símbolo (3 datasets analíticos, 3 maestros de sentimiento y 1 maestro de funding). No se generan archivos crudos, maestros de Klines, checkpoints ni archivos de liquidaciones. Con 5 símbolos, `data/` ocupa aproximadamente 693 MB.
