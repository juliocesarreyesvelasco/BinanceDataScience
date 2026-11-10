#!/usr/bin/env bash

# Rutas absolutas fijas según la especificación
BOT_DIR="/home/julioc/Documentos/BinanceDataScience"
VENV_DIR="$BOT_DIR/venv"
REQ_FILE="$BOT_DIR/requirements.txt"
HASH_FILE="$BOT_DIR/logs/.requirements.hash"
MAIN_SCRIPT="$BOT_DIR/orchestrator_01.py"
GUI_SCRIPT="$BOT_DIR/gui_countdown_00.py"

mkdir -p "$BOT_DIR/logs"
exec >> "$BOT_DIR/logs/launcher.log" 2>&1

echo "================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] INICIO: systemd timer"

# 1. Preparar entorno virtual
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
fi

source "$VENV_DIR/bin/activate"

# 2. Instalación de dependencias
if [ -f "$REQ_FILE" ]; then
    CURRENT_HASH=$(md5sum "$REQ_FILE" | awk '{print $1}')
    PREV_HASH=""
    [ -f "$HASH_FILE" ] && PREV_HASH=$(cat "$HASH_FILE")

    if [ "$CURRENT_HASH" != "$PREV_HASH" ]; then
        echo "[PIP] Actualizando dependencias..."
        "$VENV_DIR/bin/pip" install --upgrade pip
        "$VENV_DIR/bin/pip" install -r "$REQ_FILE"
        echo "$CURRENT_HASH" > "$HASH_FILE"
    fi
fi

# 3. INTERFAZ GRÁFICA: Cuenta regresiva
echo "[GUI] Mostrando notificación de inicio..."
if ! "$VENV_DIR/bin/python3" "$GUI_SCRIPT"; then
    echo "[INFO] Proceso CANCELADO por el usuario desde la interfaz gráfica."
    # Salimos con 0 para no generar una alerta de fallo crítico en systemd
    exit 0 
fi

# 4. Validación de sintaxis
echo "[CHECK] Verificando sintaxis de $(basename "$MAIN_SCRIPT")..."
if ! "$VENV_DIR/bin/python3" -m py_compile "$MAIN_SCRIPT"; then
    echo "[ERROR] Fallo de sintaxis. Abortando."
    exit 1
fi

# 5. Ejecución del orquestador
echo "[RUN] Ejecutando orquestador..."
"$VENV_DIR/bin/python3" "$MAIN_SCRIPT"

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "[FIN] Proceso terminado con éxito."
else
    echo "[ERROR] Falló con código $EXIT_CODE."
    exit $EXIT_CODE
fi
