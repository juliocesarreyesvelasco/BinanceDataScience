"""test_en_vivo_04.py: Verificación manual del flujo de automatización Gemini."""

import argparse
import sys

import browser_orchestator_01 as orchestrator
import chat_selector_03 as chat_selector
from _logging_00 import obtener_logger

LOGGER = obtener_logger()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prueba manual de la automatización de Chrome/Gemini.")
    parser.add_argument("--en-vivo", action="store_true", help="Ejecuta la automatización real (mueve el mouse y hace click).")
    args = parser.parse_args()

    x, y = chat_selector.obtener_coordenadas_chat()
    LOGGER.info("Coordenadas configuradas del chat: (%s, %s).", x, y)

    if not args.en_vivo:
        LOGGER.info("Modo seguro: no se mueve el mouse ni se abre Chrome. Usa --en-vivo para ejecutar.")
        return 0

    if not orchestrator.ejecutar_flujo_browser():
        LOGGER.error("El orquestador de navegador falló en uno de sus pasos.")
        return 1
    LOGGER.info("Flujo completo ejecutado satisfactoriamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
