# Diccionario de Datos: Archivos Consolidados

**Archivos Maestros de Klines (`klines_15m_master.csv`, `klines_12h_master.csv`)**

| Campo | Tipo de Dato | Descripción | Origen |
| :--- | :--- | :--- | :--- |
| `symbol` | String | Par de criptomonedas (ej. BTCUSDT) | Generado |
| `fecha_utc` | Datetime | Marca de tiempo estandarizada en UTC | Generado |
| `origen_datos` | String | Rastrea si la fila provino de `binance_vision` o `api_rest` | Generado |
| `fecha_procesamiento` | Datetime | Fecha en la que el consolidador generó el archivo | Generado |
| `open_time_ms` | Entero | Timestamp de apertura de la vela en milisegundos | Binance API/Vision |
| `open`, `high`, `low`, `close` | Flotante | Precios de apertura, máximo, mínimo y cierre de la vela | Binance API/Vision |
| `volume` | Flotante | Volumen total operado en el activo base (ej. BTC) | Binance API/Vision |
| `close_time_ms` | Entero | Timestamp de cierre de la vela en milisegundos | Binance API/Vision |
| `quote_asset_volume` | Flotante | Volumen total operado cotizado en dólares (USDT) | Binance API/Vision |
| `number_of_trades` | Entero | Número total de transacciones en la ventana de tiempo | Binance API/Vision |
| `taker_buy_base_asset_volume` | Flotante | Volumen comprador agresivo (market orders) en BTC | Binance API/Vision |
| `taker_buy_quote_asset_volume` | Flotante | Volumen comprador agresivo (market orders) en USDT | Binance API/Vision |
| `ignore` | Entero | Campo obsoleto del sistema antiguo de Binance | Binance API/Vision |

**Archivos Maestros de Sentimiento y Derivados (`sentimiento_master.csv`, `funding_rates_master.csv`, `liquidaciones_master.csv`)**

| Campo | Tipo de Dato | Descripción | Origen |
| :--- | :--- | :--- | :--- |
| `fundingTime` / `timestamp` | Entero | Milisegundos de reporte para tasas de fondeo o métricas de sentimiento | Binance API |
| `fundingRate` | Flotante | Porcentaje de la tasa de financiamiento cobrada/pagada a posiciones abiertas | Binance API |
| `origQty` / `price` | Flotante | Cantidad original de la orden liquidada y precio exacto de ejecución forzada | Binance API |
| `volumen_usd` | Flotante | Valor real en dólares de la posición liquidada (`origQty` * `price`) | Calculado |
| `side` | String | Lado de la orden de liquidación (BUY = Cierra un Short, SELL = Cierra un Long) | Binance API |
| `sumOpenInterest` | Flotante | Valor total de contratos de futuros abiertos, expresado en la moneda base (BTC) | Binance API |
| `longAccount` / `shortAccount` | Flotante | Porcentaje de cuentas con posiciones netas en Long o Short | Binance API |
| `longShortRatio` | Flotante | Proporción aritmética entre posiciones/cuentas Long versus Short | Binance API |
| `buySellRatio` | Flotante | Ratio entre el volumen Taker comprador y el volumen Taker vendedor | Binance API |

**Dataset Analítico Final (`dataset_analisis_15m.csv`, `dataset_analisis_12h.csv`)**

| Campo | Tipo de Dato | Descripción | Origen |
| :--- | :--- | :--- | :--- |
| `retorno_pct` | Flotante | Rendimiento porcentual de la vela actual `(close/open - 1) * 100` | Calculado |
| `rango_hl_pct` | Flotante | Volatilidad intra-vela porcentual `(high/low - 1) * 100` | Calculado |
| `taker_sell_quote_asset_volume` | Flotante | Volumen vendedor agresivo en USDT (`quote_asset_volume` - `taker_buy...`) | Calculado |
| `delta_vol_total_usd` | Flotante | Variación en dólares del volumen total respecto a la vela anterior | Calculado |
| `delta_vol_comprador_usd` | Flotante | Variación en dólares del volumen comprador respecto a la vela anterior | Calculado |
| `delta_vol_vendedor_usd` | Flotante | Variación en dólares del volumen vendedor respecto a la vela anterior | Calculado |
| `liq_shorts_usd` | Flotante | Suma en USD de posiciones Short liquidadas durante la vela (Forzados a BUY) | Calculado |
| `liq_longs_usd` | Flotante | Suma en USD de posiciones Long liquidadas durante la vela (Forzados a SELL) | Calculado |
