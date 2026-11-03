# Binance Vision (archivado)

Este directorio conserva la descarga histórica de Klines desde `data.binance.vision`.
**Ya no forma parte del pipeline diario.**

## ¿Por qué se archivó?

- La API REST ya reconstruyó el histórico completo de Klines y es la fuente que usa el consolidador.
- En las pruebas, el 100% de las filas de Binance Vision estaba contenido en el archivo de la API.
- Mantenerlo en el flujo diario obligaba a leer y desduplicar ~209.000 filas por símbolo y timeframe en cada corrida.

## ¿Cuándo usarlo?

Solo para recuperación manual:

- Si se pierde o corrompe `data/<symbol>/raw/api_rest/api_rest_klines_*.csv`.
- Si necesitas un respaldo independiente de la API y sus rate limits.
- Si quieres reconstruir historia anterior a la que conserva la API.

## Uso

```bash
./binance_env/bin/python binance_vision/backfill_vision.py --years 3
```

Parámetros opcionales:

- `--symbols BTCUSDT ETHUSDT`
- `--timeframes 15m 12h`
- `--years 3`
- `--data-dir data`
- `--pause 0`

El script escribe en `data/<symbol>/raw/binance_vision/binance_vision_klines_<tf>.csv`, igual que antes.
Es autónomo: no necesita el resto del pipeline ni credenciales de API.

> Nota: los CSV que ya existen en `data/*/raw/binance_vision/` se conservan como archivo frío.
> El consolidador actual los ignora.
