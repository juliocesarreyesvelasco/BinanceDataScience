#!/usr/bin/env bash

# Directorio base dinámico donde reside el script
BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$BOT_DIR/venv"
REQ_FILE="$BOT_DIR/requirements.txt"
HASH_FILE="$BOT_DIR/logs/.requirements.hash"

mkdir -p "$BOT_DIR/logs"
# Toda la salida del bash va a launcher.log (stdout y stderr)
exec >> "$BOT_DIR/logs/launcher.log" 2>&1

echo "================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] INICIO: systemd timer"

# 1. Preparar entorno virtual
if [ ! -d "$VENV_DIR" ]; then
    echo "[VENV] Creando entorno virtual en $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
fi

source "$VENV_DIR/bin/activate"

# 2. Instalación de dependencias (solo si requirements.txt cambia)
if [ -f "$REQ_FILE" ]; then
    CURRENT_HASH=$(md5sum "$REQ_FILE" | awk '{print $1}')
    PREV_HASH=""
    [ -f "$HASH_FILE" ] && PREV_HASH=$(cat "$HASH_FILE")

    if [ "$CURRENT_HASH" != "$PREV_HASH" ]; then
        echo "[PIP] Actualizando dependencias..."
        "$VENV_DIR/bin/pip" install --upgrade pip
        "$VENV_DIR/bin/pip" install -r "$REQ_FILE"
        echo "$CURRENT_HASH" > "$HASH_FILE"
    else
        echo "[PIP] Dependencias al día."
    fi
fi

# 3. Validación y Ejecución
echo "[CHECK] Verificando sintaxis de auth.py..."
if ! "$VENV_DIR/bin/python3" -m py_compile "$BOT_DIR/auth.py"; then
    echo "[ERROR] Fallo de sintaxis en auth.py. Abortando ejecución."
    exit 1
fi

echo "[RUN] Ejecutando orquestador..."
"$VENV_DIR/bin/python3" "$BOT_DIR/auth.py"
echo "[FIN] Proceso terminado."
