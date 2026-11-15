# Arquitectura técnica — BinanceDataScience

> Documento técnico para ingeniería. Visión de negocio: `ingesta_datos.md`. Campos y linaje: `diccionario_datos.md`.

## 1. Objetivo y alcance

Plataforma ETL para construir datasets de microestructura de futuros perpetuos de Binance.

- Símbolos por defecto: `BNBUSDT`, `ETHUSDT`, `XRPUSDT`, `SOLUSDT`, `BTCUSDT`.
- Timeframes: `5m`, `15m`, `12h`.
- Fuente: API REST de Binance Futures.
- Persistencia: 7 CSV por símbolo en `outputs/data/<símbolo en minúsculas>/consolidado/`.
- Exportación: snapshots de BTC en `outputs/btcusdt/`; ningún otro símbolo genera carpeta en `outputs/`.
- Fuera de alcance: Binance Vision automático, liquidaciones forzadas y datos crudos.

## 2. Capas

| Capa | Responsable | Salida |
|---|---|---|
| Presentación | `launcher.sh`, `gui_countdown_00.py`, `gui_progress_banner_0.py` | Selección de modo y progreso |
| Orquestación | `orchestrator_01.py`, `ingestion_orchestrator_01.py` | Coordinación y deltas |
| Extracción | `fetcher_02.py` | Datos en memoria |
| Consolidación | `data_consolidator_03.py` | Datasets y maestros |
| Persistencia | `core_storage_04.py` | CSV atómicos |
| Exportación | `export_outputs_05.py` | Snapshots de BTC |
| Automatización | `automatizacion_gemini/` | Chrome/Gemini; no transforma datos |
| Respaldo | `recovery_vision_06.py` | Archivo manual archivado |

## 3. Topología

```text
launcher.sh
  ├── gui_countdown_00.py        selecciona modo
  ├── valida entorno y dependencias
  └── orchestrator_01.py
        ├── ingestion_orchestrator_01.py
        │     ├── fetcher_02.py
        │     ├── data_consolidator_03.py
        │     └── core_storage_04.py
        ├── export_outputs_05.py
        └── automatizacion_gemini/  (opcional)
```

## 4. Orquestadores

### 4.1 `orchestrator_01.py`

Orquestador maestro. Ejecuta dos fases:

1. **ETL:** delega en `ingestion_orchestrator_01.ejecutar_pipeline()`.
2. **UI opcional:** solo si se pasa `--con-ui`, hay X11 y la exportación está activa, ejecuta `browser_orchestator_01.ejecutar_flujo_browser()`.

Flags:

| Flag | Efecto |
|---|---|
| `--symbols` | Limita los símbolos. |
| `--data-dir` | Cambia la ruta base de datos. |
| `--sin-export` | Omite exportación y automatización UI. |
| `--con-ui` | Ejecuta Chrome/Gemini al terminar la ingesta; desactivado por defecto. |
| `--sin-ui` | Oculto; compatibilidad. Ya no es necesario. |

- Si la fase ETL no procesa ningún símbolo, termina con código 1.
- La comprobación X11 usa `xset q` con `DISPLAY` y `XAUTHORITY`.
- La automatización UI solo se evalúa con `--con-ui` y exportación activa.
- `--con-ui` sin exportación no lanza Chrome, porque la UI consume los CSV exportados.

### 4.2 `ingestion_orchestrator_01.py`

Sub-orquestador ETL:

- Configura símbolos, timeframes, ventanas y pausas.
- Crea una `requests.Session` para sentimiento y un `Client` de python-binance para Klines y funding.
- Calcula pasos de progreso: `len(symbols) * (1 + len(timeframes)) + exportación`.
- Omite un símbolo si encuentra locks `.~lock.*#` en su directorio.
- Por símbolo:
  1. Actualiza funding.
  2. Por timeframe: lee estado, pide Klines, actualiza sentimiento, construye dataset, escribe y audita.
- Al final exporta los snapshots de BTC, aunque BTC no se haya procesado en esa corrida.
- Libera DataFrames con `del` y `gc.collect()`.

## 5. Extracción: `fetcher_02.py`

| Fuente | Función | Endpoint | Parámetros |
|---|---|---|---|
| Klines | `obtener_klines_api` | `/fapi/v1/klines` | `symbol`, `interval`, `start_str`, `end_str` |
| Funding | `obtener_funding_rates` | `/fapi/v1/fundingRate` | `symbol`, `startTime`, `endTime`, `limit=1000` |
| Sentimiento | `obtener_metricas_sentimiento` | 5 endpoints `/futures/data/*` | `symbol`, `period`, `startTime`, `endTime`, `limit=500` |

- Klines y funding usan el cliente autenticado de python-binance.
- Sentimiento usa HTTP directo con `X-MBX-APIKEY`.
- Reintentos solo en sentimiento: hasta 3 intentos; backoff exponencial ante HTTP 418/429.
- Klines y funding delegan los reintentos al cliente de python-binance.
- Respuesta no JSON o error persistente: se registra y se continúa con datos disponibles.
- Klines se normalizan a un diccionario con nombres internos; el elemento `k[11]` se descarta.

## 6. Consolidación: `data_consolidator_03.py`

### Klines

- `normalizar_klines()`: convierte tipos, deduplica por `open_time_ms`, ordena.
- `cargar_estado_klines()`: conserva solo Klines y `fecha_procesamiento`.
- `combinar_klines()`: agrega filas con `open_time_ms > max` existente.
- No persiste Klines crudas.

### Funding

- `_normalizar_funding()`: `int64`, deduplicación por `fundingTime`, fechas y numéricos.
- `actualizar_master_funding()`: agrega solo `fundingTime > max`.

### Sentimiento

- `_normalizar_metricas_sentimiento()`: renombra las cinco métricas y las une por `timestamp`.
- `_preparar_master_sentimiento()`: metadatos, tipos y esquema de 21 columnas.
- `actualizar_master_sentimiento()`: agrega solo `timestamp > max`.

### Dataset

- `construir_dataset()`:
  1. Metadatos y fechas.
  2. Derivadas: retorno, rango, volumen vendedor y deltas.
  3. `merge` exacto de sentimiento por `open_time_ms = timestamp`.
  4. `merge_asof` retrospectivo de funding.
  5. Reindexado a 38 columnas.

### Lectura

- Usa `pandas.read_csv(engine="pyarrow")` y cae a `low_memory=False` si PyArrow no está disponible.

## 7. Persistencia y estado

```text
outputs/data/<símbolo>/consolidado/
├── funding_rates_master.csv          9 columnas
├── sentimiento_5m_master.csv        21 columnas
├── sentimiento_15m_master.csv       21 columnas
├── sentimiento_12h_master.csv       21 columnas
├── dataset_analisis_5m.csv          38 columnas
├── dataset_analisis_15m.csv         38 columnas
└── dataset_analisis_12h.csv         38 columnas
```

- `core_storage_04.escribir_csv()`: escribe `.tmp` y reemplaza con `os.replace()`.
- `archivo_bloqueado()`: detecta `.~lock.<archivo>#`.
- No hay checkpoints JSON ni maestros de Klines.
- El estado se infiere del máximo de `open_time_ms`, `fundingTime` y `timestamp`.

## 8. Exportación: `export_outputs_05.py`

- Exporta únicamente `BTCUSDT`; el resto de símbolos no genera carpeta en `outputs/`.
- Origen: `outputs/data/btcusdt/consolidado/dataset_analisis_<tf>.csv`.
- Lee solo la cola del CSV: encabezado + ventana de 1 MiB desde el final, ampliada hasta reunir las filas necesarias.
- Ordena la cola por `open_time_ms`, excluye la vela en formación y conserva las últimas N filas:

| Timeframe | Minutos | Filas | Cobertura |
|---|---:|---:|---|
| `5m` | 5 | 144 | 12 h |
| `15m` | 15 | 96 | 24 h |
| `12h` | 720 | 28 | 14 días |

- Proyecta las 17 columnas del preset `COLUMNAS_COMPACTAS`; registra en el log las columnas ausentes.
- Escribe con `.tmp` + `os.replace()`.
- Nombre: `data_<ddmmyy>_<minutos>.csv`, con `ddmmyy` en `America/Mexico_City` al momento de exportar.
- Salida: `outputs/btcusdt/data_ddmmyy_5.csv`, `_15.csv` y `_720.csv`.
- Antes de generar los snapshots, elimina los archivos previos que cumplen `^data_\d{6}_(5|15|720)\.csv$`. Si falta el dataset de BTC, la carpeta queda vacía.
- No hay muestreo, bloques reciente/histórico, presupuesto de tokens ni corte por bytes.
- La exportación es de solo lectura sobre los datasets operativos y no crea archivo de resumen.

## 9. Interfaz y operación

- `launcher.sh`: prepara venv, sincroniza dependencias por hash, configura X11, ejecuta la cuenta regresiva y lanza el orquestador.
- `gui_countdown_00.py`: 10 segundos; botones “Iniciar todo”, “Solo descargar datos” y “Cancelar”. Códigos: 0 completo, 2 solo ingesta, 1 cancelar. El launcher traduce 0 a `--con-ui` y 2 a ejecución sin UI.
- `gui_progress_banner_0.py`: proceso Tkinter con `multiprocessing.Queue`; actualiza cada 100 ms; ventana topmost.
- `automatizacion_gemini/`: abre Chrome, maximiza la ventana y selecciona el chat fijado; ver sección 10.
- Logs: `logs/pipeline.log`.
- El launcher está preparado para un timer de systemd; las unidades viven en `linux_services/`, fuera del alcance versionado.

## 10. Automatización Gemini: `automatizacion_gemini/`

Solo se ejecuta con `--con-ui`, exportación activa y X11 alcanzable. No transforma datos: deja Chrome abierto en el chat de operación.

| Archivo | Función |
|---|---|
| `browser_orchestator_01.py` | Ejecuta los dos pasos en secuencia y devuelve éxito o fallo. |
| `chrome_launcher_02.py` | Detecta la pantalla principal, lanza Chrome y maximiza la ventana. |
| `chat_selector_03.py` | Hace click en el chat fijado `Operacion_Diaria_BTC`. |
| `_logging_00.py` | Logger compartido `binance_orquestador.gemini`. |
| `test_en_vivo_04.py` | Prueba manual; sin `--en-vivo` solo valida la configuración. |

Flujo:

1. `xrandr` obtiene la resolución y el offset del monitor primario.
2. `subprocess.Popen([CHROME_BIN])` lanza Chrome; si el binario no existe, usa la tecla Super como respaldo.
3. `wmctrl -l` busca una ventana con título `Gemini` y luego `Google Chrome`, durante 15 s.
4. `wmctrl` posiciona la ventana en el monitor principal y la maximiza.
5. `pyautogui` mueve el cursor a las coordenadas configuradas y hace click.

| Variable | Defecto | Efecto |
|---|---|---|
| `CHROME_BIN` | `google-chrome` | Binario de Chrome. |
| `GEMINI_CHAT_X` | `85` | Coordenada relativa X del chat. |
| `GEMINI_CHAT_Y` | `478` | Coordenada relativa Y del chat. |

- Las coordenadas relativas requieren recalibración si cambia la resolución, el zoom o el tema.
- Los títulos de ventana son heurísticos; puede ser necesario ajustarlos.
- Un fallo de UI se registra como advertencia y no invalida el ETL.
- Requiere `xrandr`, `wmctrl`, `pyautogui` y una sesión gráfica con `DISPLAY` y `XAUTHORITY`.

## 11. Errores, límites y rendimiento

- Sentimiento HTTP 418/429: reintento con `Retry-After` o backoff exponencial.
- Fallo de endpoint: se conserva el maestro y se continúa.
- Fallo de exportación: se registra; la ingesta se conserva.
- Lock de editor: se omite el símbolo.
- Pausas: 1 s entre lotes de Klines/funding; 0.25 s entre lotes de sentimiento.
- Memoria: lectura con PyArrow, `del` explícito y `gc.collect()`.

## 12. Deuda técnica y discrepancias

| Tema | Estado |
|---|---|
| Ruta de datos | El pipeline y el CLI de exportación usan `outputs/data/`; Vision usa `data/` por defecto. |
| Huecos de Klines | Se solicitan, pero `combinar_klines()` descarta timestamps ≤ máximo. |
| Huecos de sentimiento | Se solicitan, pero el maestro descarta timestamps ≤ máximo. |
| Maestros | Append-only; no corrigen valores existentes. |
| Última vela | Puede quedar parcial porque las filas existentes no se actualizan. |
| Snapshot único por día | El nombre solo incluye `ddmmyy`; una segunda corrida del día reemplaza el archivo del timeframe. |
| Limpieza inicial | Es destructiva: si la exportación falla tras borrar, no quedan snapshots hasta la siguiente corrida. |
| Símbolos del snapshot | Solo BTC; las otras cuatro criptos no generan carpeta en `outputs/`. |
| `fecha_procesamiento` | Las filas históricas conservan la marca de la corrida en que se escribieron; no se actualiza. |
| Automatización UI | Coordenadas y títulos de ventana dependen de calibración manual. |

## 13. Dependencias

| Librería | Uso |
|---|---|
| `python-binance` | Cliente de Klines y funding. |
| `pandas` | DataFrames, merges y CSV. |
| `numpy` | Soporte numérico. |
| `pyarrow` | Lectura rápida de CSV. |
| `requests` | Endpoints de sentimiento. |
| `python-dotenv` | Credenciales desde `.env`. |
| `tkinter` | Cuenta regresiva y banner. |
| `multiprocessing` | Proceso del banner. |
| `zoneinfo` | Hora de `America/Mexico_City`. |
| `dateutil` | Paginación mensual en Binance Vision. |
| `pyautogui` | Automatización de Chrome. |

Herramientas de sistema para la automatización: `xrandr` y `wmctrl`.

## 14. Referencias

- `documentacion/ingesta_datos.md`: visión de negocio.
- `documentacion/diccionario_datos.md`: campos y linaje.
- `data_ingestion/`: implementación.
