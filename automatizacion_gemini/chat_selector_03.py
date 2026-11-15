"""chat_selector_03.py: Selección del chat fijado Operacion_Diaria_BTC."""

import os
import time

from _logging_00 import obtener_logger

LOGGER = obtener_logger()

# Coordenadas relativas por defecto, calibradas para 1920x1080 maximizado.
COORD_REL_X = 85
COORD_REL_Y = 478


def _coord_env(nombre: str, defecto: int) -> int:
    valor = os.getenv(nombre)
    if valor is None:
        return defecto
    try:
        return max(0, int(valor))
    except ValueError:
        LOGGER.warning("Valor inválido en %s=%r; se usa %s.", nombre, valor, defecto)
        return defecto


def obtener_coordenadas_chat() -> tuple[int, int]:
    """Devuelve la posición relativa del chat, configurable por entorno."""
    return _coord_env("GEMINI_CHAT_X", COORD_REL_X), _coord_env("GEMINI_CHAT_Y", COORD_REL_Y)


def click_chat_fijado(offset_x: int = 0, offset_y: int = 0, delay_espera: float = 3.0) -> None:
    """Mueve el cursor hacia Operacion_Diaria_BTC y hace click."""
    import pyautogui

    rel_x, rel_y = obtener_coordenadas_chat()
    destino_x = offset_x + rel_x
    destino_y = offset_y + rel_y

    LOGGER.info("Esperando %.1f s para estabilizar el DOM...", delay_espera)
    time.sleep(delay_espera)
    LOGGER.info("Desplazando cursor a (%s, %s)...", destino_x, destino_y)
    pyautogui.moveTo(destino_x, destino_y, duration=0.8)
    time.sleep(0.2)
    pyautogui.click()
    LOGGER.info("Click ejecutado sobre Operacion_Diaria_BTC.")
