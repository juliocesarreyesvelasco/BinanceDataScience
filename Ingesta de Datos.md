# Documentación del Pipeline de Ingesta: Binance Data Science

**Arquitectura del Sistema**
El sistema opera mediante una arquitectura modular de cuatro componentes diseñados para sortear los límites de peticiones (rate limits) y restricciones históricas de Binance:
1. **Orquestador (`auth.py`)**: Coordina los ciclos temporales, gestiona las pausas (1 segundo) para proteger el límite de 2,400 de peso por minuto y administra los bloques de descarga según el límite de cada endpoint de la API.
2. **Motor de Extracción (`fetcher.py`)**: Ejecuta las peticiones HTTP. Descarga e ingesta en la memoria RAM (sin tocar el disco duro) los archivos ZIP estáticos de Binance Vision, y consume los endpoints REST autenticados para datos recientes y derivados.
3. **Almacenamiento y Estado (`storage.py`)**: Centraliza la escritura en disco. Deduplica cualquier dataset basándose en su campo de tiempo clave (ej. `open_time_ms`, `fundingTime`, `time`) y gestiona un archivo `checkpoint_*.json` para garantizar que el sistema pueda reanudar la ingesta exactamente donde fue interrumpido.
4. **Consolidador (`consolidator.py`)**: Procesa los datos crudos, unifica las zonas horarias a UTC, inyecta columnas de trazabilidad y calcula variaciones de volumen y rendimiento para entregar datasets listos para Machine Learning.

**Lógica de Extracción y Control de Estado**
La ingesta combina dos métodos para superar el límite institucional de Binance, el cual restringe la consulta de métricas de sentimiento a solo 30 días en el pasado. Para lograr una historia completa de 3 años, el sistema usa los repositorios estáticos para reconstruir el pasado lejano y la API en tiempo real para las ventanas recientes. Si un endpoint falla por error de límite de peticiones (HTTP 429) o rechazo de parámetros (ej. `limit=1000` en liquidaciones), el sistema guarda su progreso seguro en los checkpoints y avanza, permitiendo recuperar los huecos en la siguiente ejecución.

**Inventario de Datos Disponibles en Binance**
* **Binance Vision (Repositorio Estático HTTP)**: Almacena Klines (12 campos estándar), Trades públicos, AggTrades (volumen agresivo) y Snapshots de Order Book. Permite descargas históricas masivas sin consumir saldo de API.
* **API REST Autenticada (`fapi.binance.com`)**: Proporciona datos de derivados en vivo y hasta 30 días de historia profunda. Requiere firma criptográfica HMAC y otorga acceso al Funding Rate histórico, registro forzado de Liquidaciones (`allForceOrders`), Open Interest y Ratios Long/Short globales y de cuentas Top.
* **WebSockets**: Flujos persistentes para ingesta en tiempo real. Transmiten eventos en el milisegundo exacto (`@forceOrder`, `@bookTicker`), ideales para latencia ultrabaja pero inútiles para reconstrucción histórica.

**Datos Extraídos en este Proyecto**
* **Klines Completas (15m y 12h)**: 3 años de velas obtenidas combinando Binance Vision (historia profunda) y API REST (historia reciente).
* **Tasa de Financiamiento (Funding Rates)**: Historial completo extraído de la API, capturando el pago de fondeo cada 8 horas.
* **Liquidaciones (Force Orders)**: Órdenes liquidadas forzosamente extraídas vía API en bloques de 7 días, limitadas a 100 registros por petición.
* **Sentimiento de Mercado**: Open Interest, Global Long/Short Ratio, Top Accounts Long/Short Ratio, Top Positions Long/Short Ratio y Taker Long/Short Volume. Extraídos de la API en la máxima ventana permitida de 28 días hacia el pasado.
