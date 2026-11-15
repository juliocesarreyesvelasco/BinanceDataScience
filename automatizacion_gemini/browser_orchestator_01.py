"""browser_orchestator_01.py: Orquestador UI general para Gemini."""

import chrome_launcher_02 as launcher
import chat_selector_03 as chat_selector
from _logging_00 import obtener_logger

LOGGER = obtener_logger()


def ejecutar_flujo_browser() -> bool:
    """Ejecuta los pasos de automatización UI en orden secuencial."""
    LOGGER.info("=== INICIANDO FLUJO DE NAVEGADOR ===")

    LOGGER.info(">> [PASO 1] Lanzando y maximizando Google Chrome...")
    win_id, pantalla = launcher.abrir_y_maximizar_chrome()
    if not win_id:
        LOGGER.error("Fallo en Paso 1: no se pudo preparar la ventana.")
        return False

    LOGGER.info(">> [PASO 2] Seleccionando el chat fijado Operacion_Diaria_BTC...")
    try:
        chat_selector.click_chat_fijado(
            offset_x=pantalla["offset_x"],
            offset_y=pantalla["offset_y"],
            delay_espera=3.5,
        )
    except Exception as e:
        LOGGER.error("Fallo en Paso 2: %s", e)
        return False

    LOGGER.info("=== FLUJO DE NAVEGADOR COMPLETADO CON ÉXITO ===")
    return True


if __name__ == "__main__":
    ejecutar_flujo_browser()
