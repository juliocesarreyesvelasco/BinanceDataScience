#!/usr/bin/env bash

BOT_DIR="/home/julioc/Documentos/BinanceDataScience"
VENV_DIR="$BOT_DIR/venv"
REQ_FILE="$BOT_DIR/requirements.txt"
HASH_FILE="$BOT_DIR/logs/.requirements.hash"
MAIN_SCRIPT="$BOT_DIR/orchestrator_01.py"
GUI_SCRIPT="$BOT_DIR/gui_countdown_00.py"
UNIFIED_LOG="$BOT_DIR/logs/pipeline.log"

mkdir -p "$BOT_DIR/logs"
exec >> "$UNIFIED_LOG" 2>&1

echo "================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] INICIO: systemd timer"

export DISPLAY=":0"

if [ -r "/home/julioc/.Xauthority" ]; then
    export XAUTHORITY="/home/julioc/.Xauthority"
else
    AUTH_TMP=$(find /tmp -maxdepth 2 -name "xauth_*" -user julioc 2>/dev/null | head -n 1)
    [ -n "$AUTH_TMP" ] && export XAUTHORITY="$AUTH_TMP"
fi

# 1. Entorno virtual
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
fi

source "$VENV_DIR/bin/activate"

# 2. Dependencias
if [ -f "$REQ_FILE" ]; then
    CURRENT_HASH=$(md5sum "$REQ_FILE" | awk '{print $1}')
    PREV_HASH=""
    [ -f "$HASH_FILE" ] && PREV_HASH=$(cat "$HASH_FILE")

    if [ "$CURRENT_HASH" != "$PREV_HASH" ]; then
        echo "[PIP] Actualizando dependencias..."
        "$VENV_DIR/bin/pip" install --upgrade pip
        if "$VENV_DIR/bin/pip" install -r "$REQ_FILE"; then
            echo "$CURRENT_HASH" > "$HASH_FILE"
            echo "[PIP] Dependencias sincronizadas correctamente."
        else
            echo "[ERROR] Falló la instalación de dependencias con pip."
            exit 1
        fi
    fi
fi

# 3. INTERFAZ GRÁFICA: Cuenta regresiva (Tolerante con 3 opciones)
EXTRA_FLAGS=""
echo "[GUI] Evaluando disponibilidad de pantalla para cuenta regresiva..."
if [ -n "$DISPLAY" ] && xset q >/dev/null 2>&1; then
    "$VENV_DIR/bin/python3" "$GUI_SCRIPT"
    GUI_CODE=$?

    if [ $GUI_CODE -eq 1 ]; then
        echo "[INFO] Proceso cancelado por el usuario desde la interfaz gráfica."
        exit 0
    elif [ $GUI_CODE -eq 2 ]; then
        echo "[INFO] Modo seleccionado: SOLO INGESTA DE DATOS (Saltando automatización Gemini)."
        EXTRA_FLAGS=""
    else
        echo "[INFO] Modo seleccionado: INGESTA COMPLETA + GEMINI."
        EXTRA_FLAGS="--con-ui"
    fi
else
    echo "[GUI] Servidor X11 no accesible. Continuando automáticamente en modo backend..."
fi

# 4. Verificación de sintaxis
echo "[CHECK] Verificando sintaxis de $(basename "$MAIN_SCRIPT")..."
if ! "$VENV_DIR/bin/python3" -m py_compile "$MAIN_SCRIPT"; then
    echo "[ERROR] Fallo de sintaxis. Abortando."
    exit 1
fi

# 5. Ejecución del orquestador maestro
echo "[RUN] Ejecutando orquestador maestro con flags: ${EXTRA_FLAGS:-ninguno}..."
"$VENV_DIR/bin/python3" "$MAIN_SCRIPT" $EXTRA_FLAGS

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "[FIN] Proceso terminado con éxito."
else
    echo "[ERROR] Falló con código $EXIT_CODE."
    exit $EXIT_CODE
fi
