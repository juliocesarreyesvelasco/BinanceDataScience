"""chrome_launcher_02.py: Detección multimonitor, lanzamiento y maximizado de Chrome."""

import os
import re
import subprocess
import time
from pathlib import Path

from _logging_00 import obtener_logger

LOGGER = obtener_logger()
TIMEOUT_VENTANA_SEGUNDOS = 15
CHROME_BIN = os.getenv("CHROME_BIN", "google-chrome")
TITULOS_VENTANA = ("Gemini", "Google Chrome")


def _get_gui_env() -> dict:
    env_gui = os.environ.copy()
    env_gui.setdefault("DISPLAY", ":0")
    env_gui.setdefault("XAUTHORITY", f"{Path.home()}/.Xauthority")
    return env_gui


def obtener_geometria_pantalla_principal() -> dict:
    """Detecta la resolución y offset (+X+Y) de la pantalla principal vía xrandr."""
    env_gui = _get_gui_env()
    try:
        salida = subprocess.check_output(["xrandr"], env=env_gui).decode("utf-8")
        for linea in salida.splitlines():
            if " connected" in linea and "primary" in linea:
                match = re.search(r"(\d+)x(\d+)\+(\d+)\+(\d+)", linea)
                if match:
                    w, h, x, y = map(int, match.groups())
                    return {"width": w, "height": h, "offset_x": x, "offset_y": y}
        for linea in salida.splitlines():
            if " connected" in linea:
                match = re.search(r"(\d+)x(\d+)\+(\d+)\+(\d+)", linea)
                if match:
                    w, h, x, y = map(int, match.groups())
                    if x == 0 and y == 0:
                        return {"width": w, "height": h, "offset_x": 0, "offset_y": 0}
    except Exception as e:
        LOGGER.warning("No se pudo consultar xrandr: %s", e)

    return {"width": 1920, "height": 1080, "offset_x": 0, "offset_y": 0}


def _listar_ventanas() -> list[tuple[str, str]]:
    try:
        salida = subprocess.check_output(["wmctrl", "-l"], env=_get_gui_env()).decode("utf-8")
    except Exception as e:
        LOGGER.warning("No se pudo listar ventanas con wmctrl: %s", e)
        return []
    ventanas = []
    for linea in salida.splitlines():
        partes = linea.split(None, 3)
        if len(partes) >= 4:
            ventanas.append((partes[0], partes[3]))
    return ventanas


def _buscar_ventana_x11(patrones: tuple[str, ...] = TITULOS_VENTANA) -> str | None:
    """Devuelve la primera ventana cuyo título coincida con algún patrón, en orden de prioridad."""
    ventanas = _listar_ventanas()
    for patron in patrones:
        for win_id, titulo in reversed(ventanas):
            if patron.lower() in titulo.lower():
                LOGGER.info("Ventana detectada por '%s': %s (%s)", patron, titulo, win_id)
                return win_id
    return None


def _posicionar_y_maximizar(window_id: str, pantalla: dict) -> None:
    env_gui = _get_gui_env()
    ox, oy = pantalla["offset_x"], pantalla["offset_y"]
    try:
        subprocess.run(["wmctrl", "-ir", window_id, "-b", "remove,maximized_vert,maximized_horz"], env=env_gui, check=False)
        time.sleep(0.15)
        subprocess.run(["wmctrl", "-ir", window_id, "-e", f"0,{ox},{oy},1280,800"], env=env_gui, check=False)
        time.sleep(0.15)
        subprocess.run(["wmctrl", "-ir", window_id, "-b", "add,maximized_vert,maximized_horz"], env=env_gui, check=False)
        time.sleep(0.15)
        subprocess.run(["wmctrl", "-ia", window_id], env=env_gui, check=False)
    except Exception as e:
        LOGGER.warning("No se pudo posicionar la ventana con wmctrl: %s", e)


def _lanzar_chrome() -> bool:
    env_gui = _get_gui_env()
    try:
        subprocess.Popen(
            [CHROME_BIN],
            env=env_gui,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        LOGGER.info("Chrome lanzado con '%s'.", CHROME_BIN)
        return True
    except FileNotFoundError:
        LOGGER.warning("No se encontró '%s'; se intenta con la tecla Super.", CHROME_BIN)
    except OSError as e:
        LOGGER.warning("No se pudo lanzar '%s' (%s); se intenta con la tecla Super.", CHROME_BIN, e)

    try:
        import pyautogui

        pyautogui.press("win")
        time.sleep(0.6)
        pyautogui.write("google-chrome", interval=0.05)
        time.sleep(0.3)
        pyautogui.press("enter")
        return True
    except Exception as e:
        LOGGER.error("Fallo en el lanzamiento alternativo de Chrome: %s", e)
        return False


def abrir_y_maximizar_chrome(timeout: int = TIMEOUT_VENTANA_SEGUNDOS) -> tuple[str | None, dict]:
    """Abre Chrome y garantiza la ventana maximizada en la pantalla principal."""
    pantalla = obtener_geometria_pantalla_principal()
    LOGGER.info(
        "Pantalla principal: %sx%s en offset (+%s+%s).",
        pantalla["width"], pantalla["height"], pantalla["offset_x"], pantalla["offset_y"],
    )

    if not _lanzar_chrome():
        return None, pantalla

    LOGGER.info("Esperando registro de ventana en X11...")
    inicio = time.time()
    window_id = None
    while time.time() - inicio < timeout:
        window_id = _buscar_ventana_x11()
        if window_id:
            break
        time.sleep(0.4)

    if not window_id:
        LOGGER.error("Ventana no detectada tras %ss.", timeout)
        return None, pantalla

    LOGGER.info("Maximizando ventana %s en la pantalla principal...", window_id)
    _posicionar_y_maximizar(window_id, pantalla)
    LOGGER.info("Chrome maximizado. Esperando 5 s para la carga del DOM...")
    time.sleep(5)
    return window_id, pantalla
