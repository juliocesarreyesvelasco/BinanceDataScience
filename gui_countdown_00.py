"""gui_countdown_00.py: Notificación de inicio con soporte de pantalla principal y selección de modo."""

import os
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path


def obtener_geometria_pantalla_principal() -> dict:
    """Detecta la resolución y offset (+X+Y) de la pantalla principal vía xrandr."""
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    env.setdefault("XAUTHORITY", f"{Path.home()}/.Xauthority")
    try:
        salida = subprocess.check_output(["xrandr"], env=env).decode("utf-8")
        
        # 1. Prioridad: Monitor marcado como primary
        for linea in salida.splitlines():
            if " connected" in linea and "primary" in linea:
                match = re.search(r"(\d+)x(\d+)\+(\d+)\+(\d+)", linea)
                if match:
                    w, h, x, y = map(int, match.groups())
                    return {"w": w, "h": h, "x": x, "y": y}

        # 2. Respaldo: Monitor con origen en +0+0
        for linea in salida.splitlines():
            if " connected" in linea:
                match = re.search(r"(\d+)x(\d+)\+(\d+)\+(\d+)", linea)
                if match:
                    w, h, x, y = map(int, match.groups())
                    if x == 0 and y == 0:
                        return {"w": w, "h": h, "x": 0, "y": 0}
    except Exception as e:
        print(f"[GUI_COUNTDOWN] Advertencia detectando monitor con xrandr: {e}")

    # Fallback predeterminado
    return {"w": 1920, "h": 1080, "x": 0, "y": 0}


class CuentaRegresivaApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Iniciando Ingesta Binance")
        self.tiempo_restante = 10

        mon = obtener_geometria_pantalla_principal()

        ancho_ventana = 780
        alto_ventana = 360
        pos_x = mon["x"] + int((mon["w"] / 2) - (ancho_ventana / 2))
        pos_y = mon["y"] + int((mon["h"] / 2) - (alto_ventana / 2))

        self.root.geometry(f"{ancho_ventana}x{alto_ventana}+{pos_x}+{pos_y}")
        self.root.configure(bg="#1f1f1f")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.cancelar)

        lbl_titulo = tk.Label(
            self.root,
            text="El pipeline se ejecutará automáticamente en:",
            font=("Arial", 16, "bold"),
            bg="#1f1f1f",
            fg="#ffffff"
        )
        lbl_titulo.pack(pady=(25, 5))

        self.lbl_reloj = tk.Label(
            self.root,
            text=str(self.tiempo_restante),
            font=("Arial", 68, "bold"),
            bg="#1f1f1f",
            fg="#e0a96d"
        )
        self.lbl_reloj.pack(pady=(0, 10))

        frame_btn = tk.Frame(self.root, bg="#1f1f1f")
        frame_btn.pack(pady=10)

        # Botón 1: Flujo completo (Ingesta + UI Gemini)
        btn_completo = tk.Button(
            frame_btn,
            text="Iniciar Todo\n(Ingesta + Gemini)",
            font=("Arial", 11, "bold"),
            bg="#2e7d32",
            fg="white",
            cursor="hand2",
            width=18,
            height=2,
            relief="flat",
            command=self.iniciar_todo
        )
        btn_completo.pack(side=tk.LEFT, padx=10)

        # Botón 2: Exclusivo descarga de datos (Omitir Gemini)
        btn_solo_ingesta = tk.Button(
            frame_btn,
            text="Solo Descargar Datos\n(Saltar Gemini)",
            font=("Arial", 11, "bold"),
            bg="#0277bd",
            fg="white",
            cursor="hand2",
            width=18,
            height=2,
            relief="flat",
            command=self.solo_ingesta
        )
        btn_solo_ingesta.pack(side=tk.LEFT, padx=10)

        # Botón 3: Cancelar proceso
        btn_cancelar = tk.Button(
            frame_btn,
            text="Cancelar\nProceso",
            font=("Arial", 11, "bold"),
            bg="#c62828",
            fg="white",
            cursor="hand2",
            width=14,
            height=2,
            relief="flat",
            command=self.cancelar
        )
        btn_cancelar.pack(side=tk.LEFT, padx=10)

        self.actualizar_reloj()

    def actualizar_reloj(self):
        self.tiempo_restante -= 1
        if self.tiempo_restante <= 0:
            self.iniciar_todo()
        else:
            self.lbl_reloj.config(text=str(self.tiempo_restante))
            self.root.after(1000, self.actualizar_reloj)

    def iniciar_todo(self):
        self.root.destroy()
        sys.exit(0)

    def solo_ingesta(self):
        self.root.destroy()
        sys.exit(2)

    def cancelar(self):
        self.root.destroy()
        sys.exit(1)


if __name__ == "__main__":
    try:
        app = CuentaRegresivaApp()
        app.root.mainloop()
    except Exception as e:
        print(f"[GUI_COUNTDOWN] Error gráfico: {e}")
        sys.exit(0)
