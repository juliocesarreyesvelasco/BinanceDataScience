# Binance Vision (archivado)

Este directorio conserva la descarga histórica de Klines desde `data.binance.vision`.
**No forma parte del pipeline diario ni de la consolidación.**

## ¿Por qué se archivó?

- La API REST reconstruye el histórico completo de Klines y es la fuente que usa el pipeline.
- En las pruebas, el 100% de las filas de Binance Vision estaba contenido en la API.
- Mantenerlo en el flujo diario obligaba a leer y desduplicar ~209.000 filas por símbolo y timeframe en cada corrida.

## ¿Cuándo usarlo?

Como respaldo manual e independiente de la API y de sus rate limits:

- Si necesitas un archivo frío de Klines históricas.
- Si quieres reconstruir historia anterior a la que conserva la API.
- Si la API no está disponible y necesitas descargar los ZIP mensuales.

## Uso

```bash
./binance_env/bin/python binance_vision/backfill_vision.py --years 3
```

Parámetros opcionales:

- `--symbols BTCUSDT ETHUSDT`
- `--timeframes 5m 15m 12h` (por defecto `15m` y `12h`)
- `--years 3`
- `--data-dir data`
- `--pause 0`

El script escribe en `data/<symbol>/raw/binance_vision/binance_vision_klines_<tf>.csv`.
Es autónomo: no necesita credenciales de API.

> **Importante:** el pipeline no lee estos CSV. Para incorporar su contenido a los datasets
> habría que importarlos manualmente o volver a descargar la historia con `auth.py` (API REST).
> Este script tampoco escribe en `raw/api_rest/`, no crea checkpoints y no siembra el pipeline.
