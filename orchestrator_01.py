"""orchestrator_01.py: Orquestador Maestro del Proyecto."""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, "data_ingestion"))
sys.path.append(os.path.join(BASE_DIR, "automatizacion_gemini"))

import ingestion_orchestrator_01 as etl_pipeline

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def setup_master_logger():
    logger = logging.getLogger("master_orchestrator")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(name)s] - %(message)s")
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    return logger


def verificar_acceso_x11() -> bool:
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    env.setdefault("XAUTHORITY", f"{Path.home()}/.Xauthority")
    try:
        res = subprocess.run(["xset", "q"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Orquestador Maestro Binance + Gemini")
    parser.add_argument("--symbols", nargs="+", default=None, help="Símbolos a procesar")
    parser.add_argument("--data-dir", type=Path, default=None, help="Directorio base de datos (por defecto outputs/data)")
    parser.add_argument("--sin-export", dest="exportar", action="store_false", help="Desactivar exportación")
    parser.add_argument("--con-ui", action="store_true", help="Ejecutar la automatización de Chrome/Gemini al terminar la ingesta")
    parser.add_argument("--sin-ui", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    logger = setup_master_logger()
    logger.info("=== INICIANDO ORQUESTADOR MAESTRO ===")

    # ---------------------------------------------------------
    # FASE 1: INGESTA, CONSOLIDACIÓN Y EXPORTACIÓN (ETL)
    # ---------------------------------------------------------
    logger.info(">> FASE 1: Delegando ejecución al sub-orquestador de ingesta (ETL)...")
    try:
        exito_ingesta = etl_pipeline.ejecutar_pipeline(
            symbols=args.symbols,
            data_dir=args.data_dir,
            exportar=args.exportar,
            logger=logger
        )
    except Exception as e:
        logger.exception(f"Error crítico en el pipeline de datos: {e}")
        exito_ingesta = False

    if not exito_ingesta:
        logger.error("La Fase 1 falló o no procesó datos. Abortando.")
        sys.exit(1)

    # ---------------------------------------------------------
    # FASE 2: AUTOMATIZACIÓN DE NAVEGADOR (CONDICIONADA)
    # ---------------------------------------------------------
    if args.sin_ui:
        logger.info(">> FASE 2 Omitida: flag --sin-ui (compatibilidad).")
    elif not args.con_ui:
        logger.info(">> FASE 2 Omitida: no se indicó --con-ui.")
    elif args.exportar:
        logger.info(">> FASE 2: Evaluando estado del entorno gráfico para Google Chrome...")
        if verificar_acceso_x11():
            try:
                import browser_orchestator_01 as gemini_bot
                logger.info("[ORQUESTADOR] Pantalla activa detectada. Iniciando automatización visual...")
                exito_ui = gemini_bot.ejecutar_flujo_browser()
                if not exito_ui:
                    logger.warning("[ORQUESTADOR] La automatización UI concluyó con advertencias.")
            except Exception as e:
                logger.warning(f"[ORQUESTADOR] No se pudo completar la automatización UI: {e}")
        else:
            logger.warning("[ORQUESTADOR] Servidor X11 no alcanzable. Fase UI omitida de forma segura.")
    else:
        logger.info(">> FASE 2 Omitida: Flag --sin-export activo.")

    logger.info("=== FLUJO MAESTRO COMPLETADO CON ÉXITO ===")


if __name__ == "__main__":
    main()
