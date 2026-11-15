# Ingesta de datos — visión de negocio

> Documento de negocio. Arquitectura técnica: `proceso_arquitectura_binance.md`. Campos y linaje: `diccionario_datos.md`.

## 1. Qué hace la plataforma

Convierte datos públicos de futuros perpetuos de Binance en datasets listos para analizar microestructura, posicionamiento y presión de apalancamiento.

- 5 activos: BNB, ETH, XRP, SOL y BTC.
- 3 temporalidades: 5 minutos, 15 minutos y 12 horas.
- Cobertura de precio y funding: 3 años.
- Cobertura de sentimiento: 28 días de API, acumulados en maestros propios.
- Dos productos: historia completa para investigación y snapshots recientes de BTC para análisis asistido por IA.

## 2. Preguntas de negocio que responde

- ¿Dónde se está acumulando el apalancamiento?
- ¿Quién está posicionado: retail, cuentas VIP o ballenas?
- ¿El funding está castigando a un lado del mercado?
- ¿Quién está agrediendo el mercado: compradores o vendedores?
- ¿El precio y el posicionamiento están alineados o divergen?
- ¿En qué fase del ciclo parece estar el mercado: acumulación, markup, distribución o purga?

## 3. Fuentes y valor

| Fuente | Qué aporta | Pregunta que ayuda a responder | Frecuencia o límite |
|---|---|---|---|
| Klines | Precio, volumen, volatilidad y liquidez por vela | Contexto y estructura del mercado | 3 años |
| Funding | Costo de mantener una posición apalancada | ¿Quién paga por estar dentro? | Cada 8 h |
| Open Interest | Valor del apalancamiento abierto | ¿El movimiento tiene combustible? | 28 días de API |
| Global Long/Short | Posicionamiento de la masa minorista | ¿Dónde está el consenso retail? | 28 días de API |
| Top Accounts | Posicionamiento de cuentas top-trader | ¿Qué hacen las cuentas grandes? | 28 días de API |
| Top Positions | Posicionamiento de las mayores posiciones | ¿Qué hacen las ballenas? | 28 días de API |
| Taker Volume | Volumen agresor comprador y vendedor | ¿Quién cruza el libro? | 28 días de API |

## 4. Qué significa cada familia de datos

### Precio y liquidez

Las Klines describen qué hizo el precio, con cuánto volumen y en qué rango. Son la base para medir retorno, volatilidad, actividad y absorción.

### Apalancamiento

El Open Interest mide cuánto capital está comprometido. Un OI creciente con precio lateral sugiere acumulación de apalancamiento; una caída violenta sugiere purga.

### Posicionamiento

Los ratios long/short separan tres lecturas:

- **Global:** masa minorista.
- **Top accounts:** cuentas grandes.
- **Top positions:** posiciones grandes, proxy de ballenas.

La divergencia entre estos ratios es más informativa que un ratio aislado.

### Flujo agresor

El volumen taker distingue compradores y vendedores que consumen liquidez. Sirve para validar rupturas, absorción y trampas.

### Costo de mantener

El funding es el peaje periódico de las posiciones perpetuas. Un funding alto castiga a los largos; uno negativo, a los cortos.

## 5. Transformaciones y su impacto

| Transformación | Qué hace | Por qué importa |
|---|---|---|
| Consolidación por timestamp | Une precio, sentimiento y funding en una sola línea temporal | Permite comparar fuentes en la misma vela |
| Alineación exacta de sentimiento | Asigna cada observación a su vela | Evita inventar datos donde no hay observación |
| Funding heredado | Cada vela recibe la última tasa vigente | Refleja el costo real de mantener la posición |
| Retorno y rango | Mide dirección y volatilidad de la vela | Resume el comportamiento del precio |
| Volumen vendedor | Deriva la parte vendedora del volumen taker | Completa la lectura de agresión |
| Deltas de volumen | Mide cambio frente a la vela anterior | Detecta aceleración o freno de actividad |
| Hora local | Añade la referencia de México | Facilita lectura operativa |
| Proyección de 17 columnas | Selecciona las variables relevantes para IA | Reduce ruido sin alterar las velas |

## 6. Cobertura e implicaciones

| Dato | Cobertura | Implicación |
|---|---|---|
| Klines | 3 años | Historia suficiente para contexto y modelos |
| Funding | 3 años | Permite reconstruir el costo de posiciones |
| Sentimiento | 28 días de API + acumulado | No hay histórico previo al inicio de la plataforma |
| Snapshot 5m | Últimas 144 velas | 12 horas de contexto reciente |
| Snapshot 15m | Últimas 96 velas | 24 horas de contexto reciente |
| Snapshot 12h | Últimas 28 velas | 14 días de contexto reciente |
| Liquidaciones | No disponible | No se puede medir purga por liquidación directa |
| Order book / trades individuales | No disponible | No se puede reconstruir intención por orden |

## 7. Productos de datos

### Historia completa

En `outputs/data/<símbolo>/consolidado/` se generan 7 archivos por cada una de las 5 criptos:

- 3 datasets analíticos, uno por temporalidad.
- 3 maestros de sentimiento, uno por temporalidad.
- 1 maestro de funding, compartido por las tres temporalidades.

Estos archivos contienen la historia completa y alimentan el estado incremental. Son la fuente para investigación, backtesting y reconstrucción.

### Snapshots de BTC

En `outputs/btcusdt/` se generan solo los snapshots compactos de BTC. Ninguna otra cripto produce carpeta en `outputs/`.

| Archivo | Timeframe | Filas | Cobertura |
|---|---|---:|---|
| `data_ddmmyy_5.csv` | 5m | 144 | 12 horas |
| `data_ddmmyy_15.csv` | 15m | 96 | 24 horas |
| `data_ddmmyy_720.csv` | 12h | 28 | 14 días |

- `ddmmyy` es la fecha local de México del momento de exportación.
- Cada archivo contiene velas nativas, sin muestreo ni bloques reciente/histórico.
- Las 17 columnas son una proyección del dataset completo.
- Se excluye la vela en formación antes de recortar las filas.
- La exportación lee solo la cola del dataset, no la historia completa.
- Al inicio de la exportación se eliminan los snapshots previos de los tres timeframes; si no hay datos de BTC, la carpeta queda vacía.
- Una segunda corrida del mismo día sobrescribe el archivo de ese timeframe.
- No se genera archivo de resumen; el resultado se registra en el log.

### Paso opcional de Gemini

Con `--con-ui`, al terminar la exportación la plataforma abre Chrome y deja seleccionado el chat fijo `Operacion_Diaria_BTC` para el análisis manual. No lee, transforma ni valida datos; requiere sesión gráfica y su fallo no invalida la ingesta.

## 8. Limitaciones para interpretar

- El sentimiento histórico es limitado: la API solo permite recuperar 28 días hacia atrás y los maestros acumulan desde la primera corrida.
- Las columnas de sentimiento pueden quedar vacías en velas antiguas.
- El funding se hereda; no se suman todos los pagos dentro de una vela de 12 h.
- Los huecos históricos no se reparan de forma efectiva en la implementación actual.
- La última vela del dataset puede estar en formación.
- El snapshot es una ventana reciente: no sirve para calcular cobertura histórica ni para backtesting de largo plazo.
- Solo BTC tiene snapshot; las otras criptos solo existen en la historia completa.
- El snapshot sobrescribe el archivo del día; no hay versionado por hora.
- Al inicio de la exportación se borran los snapshots previos; si el proceso falla después, la carpeta puede quedar vacía o incompleta.
- Los ratios son agregados; no identifican traders individuales.
- El funding indica costo, no dirección futura del precio.

## 9. Casos de uso

- Detectar acumulación de apalancamiento y riesgo de purga.
- Comparar posicionamiento retail contra ballenas.
- Identificar fases de acumulación, markup, distribución y markdown.
- Validar rupturas con flujo taker.
- Medir estrés de funding en posiciones largas o cortas.
- Analizar el contexto reciente de BTC con un archivo acotado.
- Construir variables de entrada para modelos predictivos con la historia completa.

## 10. Glosario de negocio

| Término | Definición |
|---|---|
| Kline | Vela de precio con apertura, máximo, mínimo, cierre y volumen. |
| Funding | Pago periódico entre largos y cortos para acercar el perpetuo al spot. |
| Open Interest | Capital abierto en posiciones de futuros. |
| Long/Short Ratio | Relación entre posicionamiento largo y corto. |
| Top Trader | Cuenta o posición clasificada como grande por Binance. |
| Taker | Orden que consume liquidez del libro. |
| Mark Price | Precio de referencia para funding y liquidaciones. |
| Snapshot | Archivo con las últimas N velas nativas de un timeframe. |
| Microestructura | Estudio de liquidez, flujo y posicionamiento en el corto plazo. |

## 11. Referencias

- `documentacion/proceso_arquitectura_binance.md`
- `documentacion/diccionario_datos.md`
- `motor_cuantitativo_de_microestructura.md`
- `ciclos_de_microestructura_y_fases_del_mercado.md`
