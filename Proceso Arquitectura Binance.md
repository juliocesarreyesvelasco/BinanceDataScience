# Arquitectura y Pipeline de Extracción Institucional de Binance

Este documento detalla la arquitectura técnica, lógica operativa y especificaciones de ingesta implementadas en el sistema de recolección de criptoactivos para Data Science y Modelado Predictivo.

> **Alcance actual:** la ingesta usa únicamente la API REST. Binance Vision quedó archivado en `binance_vision/` como respaldo manual y las liquidaciones forzadas se descartaron del proyecto.

---

## 1. Topología de Fuentes de Datos

```text
                               ┌────────────────────────────────────────┐
                               │            API REST AUTENTICADA        │
                               │             (fapi.binance.com)         │
                               └──────────────────┬─────────────────────┘
                                                  │
                                     Extracción de datos históricos y recientes
                                     • Klines 15m y 12h
                                     • Funding Rates (cada 8h)
                                     • Ratios de sentimiento (ventana 28d)
                                                  │
                                                  ▼
                               ┌────────────────────────────────────────┐
                               │        DATA LAKE LOCAL (raw/)          │
                               │   Organizado por fuente y tipo         │
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
                               │       7 ARCHIVOS MAESTROS CSV          │
                               │           (consolidado/)               │
                               └────────────────────────────────────────┘
```

### A. API REST Autenticada (fapi.binance.com)

- **Protocolo:** HTTPS con inyección del encabezado `X-MBX-APIKEY` y firma criptográfica HMAC-SHA256.
- **Propósito:** obtención de Klines, tasas de fondeo y sentimiento de mercado reciente.
- **Límites operativos:** 2,400 unidades de peso por minuto para cuentas autenticadas estándar.
- **Restricción de ventana (sentimiento):** Binance solo permite consultar los últimos 28-30 días calendario de `openInterestHist`, `globalLongShortAccountRatio`, `topLongShortAccountRatio`, `topLongShortPositionRatio` y `takerlongshortRatio`. El pipeline captura esa ventana de forma recurrente y la acumula en el archivo local.
- **Klines:** la API permite reconstruir varios años de historia paginando por bloques. El pipeline usa 30 días por lote para 15m y 180 días por lote para 12h.

### B. Binance Vision (archivado)

- Se conserva el script `binance_vision/backfill_vision.py` y los CSV históricos en `data/*/raw/binance_vision/`.
- Ya no se ejecuta en el flujo diario ni se lee en la consolidación.
- Motivo: el 100% de sus filas estaba contenido en la API y duplicaba el trabajo de lectura y desduplicación en cada corrida.

### C. Liquidaciones forzadas (fuera de alcance)

- El endpoint público `GET /fapi/v1/allForceOrders` ya devuelve HTTP 404.
- El método `futures_liquidation_orders` de python-binance apunta a `/fapi/v1/forceOrders` con firma, es decir, a las órdenes forzadas de la propia cuenta, no al mercado.
- Por decisión del proyecto, no se capturan liquidaciones ni se generan columnas relacionadas.

## 2. Lógica del Pipeline y Control de Checkpoints

El pipeline resuelve dos cuellos de botella: la pérdida de conexión y el bucle de re-descargas innecesarias.

- **Ejecución exclusiva:** `auth.py` adquiere un bloqueo `flock` sobre `logs/pipeline.lock`. Si ya hay otra corrida activa, aborta con un mensaje de error.
- **Gestión de checkpoints bidireccional:** cada categoría y temporalidad mantiene un `checkpoint_<clave>.json` en `data/<symbol>/checkpoints/`. El estado registra `backfill_completado`, `ultimo_timestamp_reciente_ms` y `timestamp_mas_antiguo_ms`.
- **Modo Backfill:** cuando `backfill_completado = False`, el orquestador itera retrospectivamente desde la fecha actual hasta hace 3 años. Al finalizar, sella la bandera en `True`.
- **Modo Incremental:** si `backfill_completado = True`, calcula el delta desde `ultimo_timestamp_reciente_ms` hasta ahora y solicita únicamente los registros nuevos.
- **Pausas antifraude:** cada petición incorpora una pausa fija de 1 segundo (`PAUSA_SEGUNDOS = 1`). El consumo se mantiene muy por debajo del techo de 2,400 unidades por minuto.

## 3. Matriz de Ingesta: Datos Extraídos vs Fuentes

| Dataset | Granularidad | Fuente Primaria | Ventana Histórica | Estrategia de Descarga |
| --- | --- | --- | --- | --- |
| Klines (Velas Completas) | 15m y 12h | API REST | 3 años continuos | Paginación en lotes de 30 días (15m) y 180 días (12h) |
| Funding Rate (Tasa Fondeo) | 8 horas | API REST (`/fapi/v1/fundingRate`) | 3 años continuos | Paginación en bloques de 120 días (hasta 1,000 registros) |
| Open Interest Histórico | 15m y 12h | API REST (`/futures/data/openInterestHist`) | 28 días acumulados | Lotes de 7 días con `limit=500` |
| Global Long/Short Ratio | 15m y 12h | API REST (`/futures/data/globalLongShortAccountRatio`) | 28 días acumulados | Lotes de 7 días con `limit=500` |
| Top Trader Accounts Ratio | 15m y 12h | API REST (`/futures/data/topLongShortAccountRatio`) | 28 días acumulados | Lotes de 7 días con `limit=500` |
| Top Trader Positions Ratio | 15m y 12h | API REST (`/futures/data/topLongShortPositionRatio`) | 28 días acumulados | Lotes de 7 días con `limit=500` |
| Taker Long/Short Ratio | 15m y 12h | API REST (`/futures/data/takerlongshortRatio`) | 28 días acumulados | Lotes de 7 días con `limit=500` |

## 4. Proceso de Consolidación y Alineación Temporal

Para construir los datasets analíticos finales (`dataset_analisis_15m.csv` y `dataset_analisis_12h.csv`), el consolidador aplica estas operaciones:

1. **Klines desde la API:** lee `api_rest_klines_<tf>.csv`, deduplica por `open_time_ms` y ordena. Genera `klines_<tf>_master.csv`.
2. **Sentimiento con columnas explícitas:** antes del merge, renombra las columnas de cada métrica con prefijos (`global_ls_*`, `top_accounts_*`, `top_positions_*`, `oi_*`, `taker_*`) para evitar sufijos ambiguos `_x/_y`. Luego cruza las 5 métricas por `timestamp`.
3. **Propagación asíncrona del Funding Rate (`merge_asof`):** el Funding Rate se cobra cada 8 horas. Mediante un cruce retrospectivo (`direction="backward"`), cada vela hereda la última tasa vigente.
4. **Hora local:** cada archivo conserva `fecha_utc` y añade `fecha_local` en `America/Mexico_City` (ISO 8601 con offset). Las claves de cruce siguen en milisegundos UTC.
5. **Escritura segura:** los CSV se escriben primero en un archivo temporal y luego se reemplazan de forma atómica. Si existe un lock de LibreOffice (`.~lock.<archivo>#`), la consolidación de ese símbolo se omite con una advertencia.

**Salidas:** 7 archivos maestros por símbolo (2 de Klines, 1 de Funding, 2 de Sentimiento y 2 datasets analíticos). No se generan archivos de liquidaciones.
