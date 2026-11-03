# Diccionario de Datos: Archivos Consolidados

Este catálogo documenta los **7 archivos CSV** generados por `consolidator.py` dentro de `data/<symbol>/consolidado/`. Las liquidaciones forzadas quedaron fuera del alcance del proyecto.

Los timestamps de negocio se guardan en dos formatos:
- `fecha_utc`: fecha legible en UTC, sin zona horaria (`YYYY-MM-DD HH:MM:SS`).
- `fecha_local`: fecha legible en hora de Ciudad de México (`America/Mexico_City`), en formato ISO 8601 con offset (`YYYY-MM-DD HH:MM:SS-06:00`).

`fecha_procesamiento` también se escribe en hora local con offset.

---

## 1. Catálogo a Nivel de Tabla

| Nombre del Archivo | Descripción del Conjunto de Datos | Granularidad Temporal | Volumen Aprox. (3 Años) | Llave Primaria / Clave de Cruce |
| :--- | :--- | :--- | :--- | :--- |
| `klines_15m_master.csv` | Historial de velas de 15 minutos extraído de la API REST. | 15 minutos | ~106,800 filas | `open_time_ms` |
| `klines_12h_master.csv` | Historial de velas de 12 horas extraído de la API REST. | 12 horas | ~2,500 filas | `open_time_ms` |
| `funding_rates_master.csv` | Historial de pagos de la tasa de financiamiento. | 8 horas | ~3,600 filas | `fundingTime` |
| `sentimiento_15m_master.csv` | Cruce horizontal de las 5 métricas de futuros en 15m. | 15 minutos | ~2,800 filas (28 días acumulados) | `timestamp` |
| `sentimiento_12h_master.csv` | Cruce horizontal de las 5 métricas de futuros en 12h. | 12 horas | ~62 filas (28 días acumulados) | `timestamp` |
| `dataset_analisis_15m.csv` | **Dataset de entrenamiento primario:** Klines 15m enriquecidas con sentimiento, funding y deltas. | 15 minutos | ~106,800 filas | `open_time_ms` |
| `dataset_analisis_12h.csv` | **Dataset de visión macro:** Klines 12h integradas con variables de derivados agregadas. | 12 horas | ~2,500 filas | `open_time_ms` |

---

## 2. Diccionario a Nivel de Campo

### A. Tablas de Klines Maestras (`klines_15m_master.csv`, `klines_12h_master.csv`)

| Columna | Tipo de Dato | Unidad | Nullable | Descripción y Regla de Negocio |
| :--- | :--- | :--- | :--- | :--- |
| `symbol` | String | Texto | No | Par negociado en futuros de Binance (ej. `BTCUSDT`). |
| `fecha_utc` | Datetime | UTC | No | Marca temporal humana de apertura en UTC. |
| `fecha_local` | Datetime | America/Mexico_City | No | Marca temporal humana de apertura en hora local, ISO 8601 con offset. |
| `open_time_ms` | Int64 | Milisegundos | No | Timestamp Unix del inicio de la vela. Llave primaria temporal. |
| `open` | Float64 | USDT | No | Precio de apertura del contrato en el intervalo. |
| `high` | Float64 | USDT | No | Precio máximo alcanzado en el intervalo. |
| `low` | Float64 | USDT | No | Precio mínimo alcanzado en el intervalo. |
| `close` | Float64 | USDT | No | Precio de cierre del contrato en el intervalo. |
| `volume` | Float64 | Contratos Base | No | Cantidad total del activo base operada en la vela. |
| `close_time_ms` | Int64 | Milisegundos | No | Timestamp Unix del cierre de la vela. |
| `quote_asset_volume` | Float64 | USDT | No | Volumen total negociado expresado en dólares (USDT). |
| `number_of_trades` | Int64 | Conteo | No | Total de transacciones individuales ejecutadas en la vela. |
| `taker_buy_base_asset_volume` | Float64 | Contratos Base | No | Volumen comprado a mercado (agresivo) en el activo base. |
| `taker_buy_quote_asset_volume` | Float64 | USDT | No | Volumen comprado a mercado (agresivo) expresado en USDT. |
| `origen_datos` | String | Texto | No | Trazabilidad del origen. Para este proyecto: `api_rest`. |
| `fecha_procesamiento` | Datetime | Local | No | Momento de consolidación en hora local con offset. |

---

### B. Tabla de Funding Rates (`funding_rates_master.csv`)

| Columna | Tipo de Dato | Unidad | Nullable | Descripción y Regla de Negocio |
| :--- | :--- | :--- | :--- | :--- |
| `symbol` | String | Texto | No | Identificador del par de futuros (ej. `BTCUSDT`). |
| `fecha_utc` | Datetime | UTC | No | Fecha y hora legible en UTC en que se aplicó el fondeo. |
| `fecha_local` | Datetime | America/Mexico_City | No | Fecha y hora legible en hora local, ISO 8601 con offset. |
| `fundingTime` | Int64 | Milisegundos | No | Timestamp Unix del pago de la tasa de financiamiento. |
| `fundingRate` | Float64 | Ratio | No | Tasa porcentual (ej. `0.0001` = 0.01%). Positivo: Longs pagan a Shorts. Negativo: Shorts pagan a Longs. |
| `markPrice` | Float64 | USDT | Sí | Precio de marca oficial al momento del cobro del financiamiento. |
| `rateType` | String | Texto | Sí | Tipo de tasa reportado por Binance (por ejemplo, `Regular`). |
| `origen_datos` | String | Texto | No | Indicador de procedencia: `api_funding`. |
| `fecha_procesamiento` | Datetime | Local | No | Momento de consolidación en hora local con offset. |

---

### C. Tablas de Sentimiento (`sentimiento_15m_master.csv`, `sentimiento_12h_master.csv`)

Las columnas se renombraron con prefijos por métrica para eliminar la ambigüedad que generaba el merge (`longAccount_x`, `longAccount_y`, etc.).

| Columna | Tipo de Dato | Unidad | Nullable | Descripción y Regla de Negocio |
| :--- | :--- | :--- | :--- | :--- |
| `symbol` | String | Texto | No | Identificador del par analizado. |
| `fecha_utc` | Datetime | UTC | No | Marca temporal sincronizada en UTC. |
| `fecha_local` | Datetime | America/Mexico_City | No | Marca temporal en hora local, ISO 8601 con offset. |
| `timestamp` | Int64 | Milisegundos | No | Timestamp Unix del snapshot de sentimiento. |
| `oi_sum_open_interest` | Float64 | Contratos Base | Sí | Total de contratos abiertos vigentes. |
| `oi_value_usd` | Float64 | USDT | Sí | Valor nocional total del interés abierto en dólares. |
| `oi_cmc_circulating_supply` | Float64 | Unidades | Sí | Suministro circulante reportado por CMC en el snapshot. |
| `global_ls_long_account` | Float64 | Porcentaje (0-1) | Sí | % de cuentas globales con posiciones netas compradoras (Long). |
| `global_ls_short_account` | Float64 | Porcentaje (0-1) | Sí | % de cuentas globales con posiciones netas vendedoras (Short). |
| `global_ls_ratio` | Float64 | Ratio | Sí | Ratio global de cuentas: `global_ls_long_account / global_ls_short_account`. |
| `top_accounts_long_account` | Float64 | Porcentaje (0-1) | Sí | % de cuentas de Traders Top con posiciones netas Long. |
| `top_accounts_short_account` | Float64 | Porcentaje (0-1) | Sí | % de cuentas de Traders Top con posiciones netas Short. |
| `top_accounts_ratio` | Float64 | Ratio | Sí | Ratio de cuentas de Traders Top. |
| `top_positions_long_account` | Float64 | Porcentaje (0-1) | Sí | % de posiciones Long de Traders Top reportado por el endpoint de posiciones. |
| `top_positions_short_account` | Float64 | Porcentaje (0-1) | Sí | % de posiciones Short de Traders Top reportado por el endpoint de posiciones. |
| `top_positions_ratio` | Float64 | Ratio | Sí | Ratio de posiciones de Traders Top. |
| `taker_buy_sell_ratio` | Float64 | Ratio | Sí | Ratio de volumen agresivo: `buyVol / sellVol`. |
| `taker_sell_vol` | Float64 | Contratos Base | Sí | Volumen vendedor agresivo taker operado en la ventana. |
| `taker_buy_vol` | Float64 | Contratos Base | Sí | Volumen comprador agresivo taker operado en la ventana. |
| `origen_datos` | String | Texto | No | Indicador de procedencia: `api_sentimiento`. |
| `fecha_procesamiento` | Datetime | Local | No | Momento de consolidación en hora local con offset. |

---

### D. Datasets Analíticos Finales (`dataset_analisis_15m.csv`, `dataset_analisis_12h.csv`)

Estos datasets combinan las columnas de Klines, Sentimiento y Funding, más las siguientes **variables calculadas**:

| Columna | Tipo de Dato | Unidad | Nullable | Fórmula / Definición |
| :--- | :--- | :--- | :--- | :--- |
| `retorno_pct` | Float64 | Porcentaje | No | Rendimiento porcentual de la vela: `((close / open) - 1) * 100`. |
| `rango_hl_pct` | Float64 | Porcentaje | No | Volatilidad porcentual máxima: `((high / low) - 1) * 100`. |
| `taker_sell_quote_asset_volume` | Float64 | USDT | No | Volumen agresivo vendedor: `quote_asset_volume - taker_buy_quote_asset_volume`. |
| `delta_vol_total_usd` | Float64 | USDT | Sí (fila 1) | Cambio en volumen operado respecto a la vela anterior: `quote_asset_volume.diff()`. |
| `delta_vol_comprador_usd` | Float64 | USDT | Sí (fila 1) | Cambio en volumen agresivo comprador respecto a la vela anterior. |
| `delta_vol_vendedor_usd` | Float64 | USDT | Sí (fila 1) | Cambio en volumen agresivo vendedor respecto a la vela anterior. |
| `fundingRate` | Float64 | Ratio | Sí (>28d) | Tasa de fondeo vigente durante la vela (propagada vía `merge_asof`). |

**Notas de alcance:**
- No existen columnas de liquidaciones (`liq_shorts_usd`, `liq_longs_usd`); esa fuente quedó fuera del proyecto.
- Las métricas de sentimiento solo están disponibles desde que comenzó su captura (ventana de 28 días). Las filas anteriores quedan como `NaN`.
- `fecha_local` se conserva en el dataset para análisis y presentación; las claves de cruce siguen siendo `open_time_ms` y `timestamp` en milisegundos UTC.
