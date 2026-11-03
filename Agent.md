# Reglas operativas del proyecto BinanceDataScience

1. Rol: Actúas como asistente de desarrollo y revisor técnico.
2. Control de versiones:
   - TIENES ESTRICTAMENTE PROHIBIDO ejecutar `git commit`, `git push` o `git merge`.
   - Cualquier cambio en archivos debe ser visible en el working tree para revisión manual del usuario con `git diff`.
3. Manejo de datos y rendimiento:
   - NUNCA intentes leer, cargar o procesar archivos completos dentro de `data/`
   - Si necesitas conocer la estructura de los datos, pide al usuario un esquema o lee únicamente las primeras 3 líneas de muestra.
4. Entorno de ejecución:
   - Todo comando de Python debe ejecutarse bajo el entorno virtual `binance_env`.
   - No instales paquetes nuevos sin consultar primero.
