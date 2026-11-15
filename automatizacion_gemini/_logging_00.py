"""_logging_00.py: Logger compartido de la automatización Gemini."""

import logging

NOMBRE_LOGGER = "binance_orquestador.gemini"


def obtener_logger() -> logging.Logger:
    logger = logging.getLogger(NOMBRE_LOGGER)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
