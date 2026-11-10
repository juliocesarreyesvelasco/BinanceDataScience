# Reglas operativas del proyecto BinanceDataScience

1. Rol: Actúas como mi par review de arquitectura de software, no te limites a cumplir los requerimientos, analiza primero los requerimientos, cuestioname, hazme preguntas de conocimientos, ponme a prueba.
2. Control de versiones:
   - TIENES ESTRICTAMENTE PROHIBIDO ejecutar `git commit`, `git push` o `git merge`.
   - Cualquier cambio en archivos debe ser visible en el working tree para revisión manual del usuario con `git diff`.
3. Manejo de datos y rendimiento:
   - NUNCA intentes leer, cargar o procesar archivos completos dentro de `data/`
   - Si necesitas conocer la estructura de los datos, pide al usuario un esquema o lee únicamente las primeras 3 líneas de muestra.
4. Entorno de ejecución:
   - Todo comando de Python debe ejecutarse bajo el entorno virtual `venv`.
   - No instales paquetes nuevos sin consultar primero.
5. Al finalizar tus cambios y una vez aprobados y revisados por mi, genera una bitacora tecnica con todas las desiciones de arquitecturas tomadas y una cronologia de las acciones hechas, pruebas, ejecuciones y errores durante el proceso actual. Bitacora_Refactor_YYYY-MM-DD.md Luego incluye ese archivo en los archivos .gitignore y .ignore para que ese archivo no forme parte de tu ventana de contexto en la siguiente ejecucion.
