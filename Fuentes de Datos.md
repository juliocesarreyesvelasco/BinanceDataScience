> **Nota de alcance (2026-11-02):** este documento es una bitácora de investigación. El proyecto final **no incluye liquidaciones** (el endpoint público `allForceOrders` ya devuelve HTTP 404 y el método de python-binance consulta órdenes propias) y **Binance Vision quedó archivado** en `binance_vision/`. El pipeline usa solo API REST para Klines, Funding y Sentimiento. Ver `Proceso Arquitectura Binance.md`.

Existen tres vías principales provistas por Binance para extraer datos, cada una con un propósito y alcance distinto. Al estar autenticado, se desbloquean capacidades y límites de descarga superiores.

**Binance Vision (Repositorio Estático)**

* Consiste en archivos ZIP masivos consolidados por mes y día en `data.binance.vision`. No consume límites de tu API.
* Datos disponibles: Klines (velas de Spot y Futuros), Trades públicos, AggTrades (operaciones agrupadas por nivel de precio) y snapshots del Order Book (profundidad de mercado).
* Limitaciones: Carece de métricas de sentimiento (Open Interest, ratios Long/Short) y no almacena el historial de liquidaciones forzadas.

**API REST Autenticada (Endpoints Dinámicos)**

* Es el acceso a los servidores (ej. `fapi.binance.com`). Usar tu API Key te otorga mayor peso de peticiones por minuto y acceso a datos sensibles.
* Datos disponibles: Klines (hasta 3 años paginando), Funding Rates, Open Interest y ratios de cuentas/posiciones (estrictamente restringidos a 30 días históricos).
* Liquidaciones: El endpoint `allForceOrders` permite extraer el registro histórico de posiciones liquidadas. Al estar autenticado evitas bloqueos, pero Binance limita la ventana temporal por petición, obligando a iterar mediante paginación o fechas límite.

**WebSockets (Flujo de Datos en Vivo)**

* Conexiones persistentes para capturar eventos en el milisegundo en que ocurren.
* Datos disponibles: Actualizaciones del libro de órdenes, trades instantáneos y el canal `@forceOrder`, que transmite un mensaje cada vez que un usuario es liquidado en tiempo real. Es ideal para construir tu propia base de datos de liquidaciones hacia el futuro sin depender del historial de la API.

¿De estas tres fuentes y conjuntos de datos, cuáles decides integrar a tu proyecto para estructurar los siguientes módulos?

¿Te gustaría que revisemos los parámetros exactos que pide el endpoint de liquidaciones para comprobar hasta qué fecha histórica real nos permite retroceder la API?

###
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
###

Para garantizar que captures **toda la data disponible** y no únicamente el subconjunto recortado de tu script original (donde solo extraías 4 campos de klines y 1 registro de snapshots), aquí tienes el inventario completo clasificado por cada medio de ingesta:

### 1. Binance Vision (Repositorio Estático)

Descarga en bloques mensuales y diarios vía HTTP en `data.binance.vision`. No consume rate limits de API.

* **Klines Completas (12 campos estándar):** Tu script original solo guardaba 4 columnas (`open_time`, `open`, `volume`, `open_time_ms`). La data completa incluye:


* `Open time`, `Open`, `High`, `Low`, `Close`, `Volume`
* `Close time`
* `Quote asset volume` (volumen en USDT transaccionado)
* `Number of trades` (conteo de transacciones)
* `Taker buy base asset volume` (volumen de compra agresiva en BTC)
* `Taker buy quote asset volume` (volumen de compra agresiva en USDT)
* `Ignore`


* **AggTrades (Operaciones agrupadas por orden):**
* ID de trade agregado, Precio, Cantidad, Primer Trade ID, Último Trade ID, Timestamp, Flag si fue el comprador el creador de mercado (`isBuyerMaker`).


* **Book Ticker / Snapshots del Order Book:**
* Profundidad de las mejores órdenes de compra (bid) y venta (ask) con sus cantidades históricas diarias.

---

### 2. API REST Autenticada (`fapi.binance.com`)

Datos dinámicos y de derivados. Requiere autenticación con `X-MBX-APIKEY` y firma HMAC para elevar los límites y acceder a órdenes forzadas.

* **Funding Rate Histórico (`/fapi/v1/fundingRate`):**
* Retorna el historial completo de pagos de financiamiento cada 8 horas (no solo el snapshot actual que traía `premiumIndex`): `symbol`, `fundingRate`, `fundingTime`, `markPrice`.


* **Historial de Liquidaciones (`/fapi/v1/allForceOrders`):**
* Historial de posiciones liquidadas: `symbol`, `price`, `origQty` (cantidad liquidada), `executedQty`, `side` (SELL/BUY forzado), `type` (LIMIT/MARKET), `timeInForce`, `time`.


* **Métricas de Sentimiento (Ventana de 30 días continuos con límite hasta 500 registros por llamada):**
* **Open Interest Histórico (`/futures/data/openInterestHist`):** `sumOpenInterest` (en BTC), `sumOpenInterestValue` (en USDT), `timestamp`.


* **Global Long/Short Account Ratio (`/futures/data/globalLongShortAccountRatio`):** Ratio general de cuentas, `% de cuentas long`, `% de cuentas short`, `timestamp`.


* **Top Trader Long/Short Account Ratio (`/futures/data/topLongShortAccountRatio`):** Cuentas de traders institucionales/top, porcentajes y ratio.


* **Top Trader Long/Short Position Ratio (`/futures/data/topLongShortPositionRatio`):** Posiciones netas reales del top (no solo cuentas), porcentajes y ratio.


* **Taker Long/Short Ratio (`/futures/data/takerlongshortRatio`):** Volumen de compra agresivo vs venta agresiva en el mercado de derivados (`buyVol`, `sellVol`, `buySellRatio`).

---

### Ajuste en la Estrategia de Ingesta

Para no perder nada, el sistema debe estructurarse en dos capas complementarias:

1. **Capa Histórica Masiva (Binance Vision):**
* Descarga de Klines completas (con las 12 columnas intactas) y AggTrades para los 3 años.


2. **Capa de Métricas & Sentimiento (API Autenticada):**
* Paginación completa de los últimos 30 días para Open Interest, ratios Long/Short (con `limit=500` en lugar de `limit=1`).


* Extracción de todo el historial de Funding Rates disponible.
* Extracción paginada de Liquidaciones (`allForceOrders`).

¿Deseas que agreguemos a la descarga de Binance Vision los archivos de AggTrades (volumen agresivo tick-by-tick) además de las Klines completas?

###
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
###