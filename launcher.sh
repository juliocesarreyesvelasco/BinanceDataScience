#!/usr/bin/env bash

# Rutas absolutas fijas
BOT_DIR="/home/julioc/Documentos/BinanceDataScience"
VENV_DIR="$BOT_DIR/venv"
REQ_FILE="$BOT_DIR/requirements.txt"
HASH_FILE="$BOT_DIR/logs/.requirements.hash"
MAIN_SCRIPT="$BOT_DIR/orchestrator_01.py"

mkdir -p "$BOT_DIR/logs"
exec >> "$BOT_DIR/logs/launcher.log" 2>&1

echo "================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] INICIO: systemd timer"

# --- NOTIFICACIÓN VISUAL (Zenity) ---
# Necesario para que systemd pueda dibujar la ventana en tu entorno XFCE
export DISPLAY=:0 

if command -v zenity >/dev/null 2>&1; then
    # zenity --question devuelve: 0 (Aceptar), 1 (Cancelar), 5 (Timeout)
    zenity --question \
        --title="Pipeline BinanceDataScience" \
        --text="El proceso de ingesta automática comenzará en 10 segundos.\n\n¿Deseas iniciarlo ahora mismo o cancelar esta corrida?" \
        --ok-label="Iniciar Ahora" \
        --cancel-label="Cancelar" \
        --timeout=10

    ZEN_STATUS=$?

    if [ $ZEN_STATUS -eq 1 ]; then
        echo "[CANCELADO] El usuario abortó la ejecución desde la ventana emergente."
        # Salimos con código 0 para que systemd no registre esto como un error del sistema
        exit 0
    fi
    echo "[PROCESANDO] Ventana aceptada o tiempo de espera concluido."
fi
# ------------------------------------

# 1. Preparar entorno virtual
if [ ! -d "$VENV_DIR" ]; then
    echo "[VENV] Creando entorno virtual en $VENV_DIR..."
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
    else
        echo "[PIP] Dependencias al día."
    fi
else
    echo "[WARN] No se encontró $REQ_FILE. Omitiendo actualización de pip."
fi

# 3. Validación de sintaxis
echo "[CHECK] Verificando sintaxis de $(basename "$MAIN_SCRIPT")..."
if ! "$VENV_DIR/bin/python3" -m py_compile "$MAIN_SCRIPT"; then
    echo "[ERROR] Fallo de sintaxis en $(basename "$MAIN_SCRIPT"). Abortando ejecución."
    exit 1
fi

# 4. Ejecución del orquestador
echo "[RUN] Ejecutando orquestador..."
"$VENV_DIR/bin/python3" "$MAIN_SCRIPT"

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "[FIN] Proceso terminado con éxito."
else
    echo "[ERROR] El orquestador finalizó con código de error $EXIT_CODE."
    exit $EXIT_CODE
fi
