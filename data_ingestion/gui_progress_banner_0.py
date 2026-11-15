"""gui_progress_banner_0.py: Banner visual con barra de progreso para la Ingesta de Datos."""

import multiprocessing as mp
import tkinter as tk
from tkinter import ttk
import os
from pathlib import Path


class _ProgressWindowApp:
    def __init__(self, queue: mp.Queue, total_steps: int):
        self.queue = queue
        self.total_steps = max(1, total_steps)
        self.current_step = 0

        self.root = tk.Tk()
        self.root.title("Progreso de Ingesta Binance")

        ancho, alto = 650, 180
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        pos_x = int((screen_w / 2) - (ancho / 2))
        pos_y = int((screen_h / 2) - (alto / 2))

        self.root.geometry(f"{ancho}x{alto}+{pos_x}+{pos_y}")
        self.root.configure(bg="#1e1e1e")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor="#2b2b2b",
            background="#4caf50",
            thickness=22
        )

        self.lbl_title = tk.Label(
            self.root,
            text="Descargando y consolidando datasets...",
            font=("Arial", 14, "bold"),
            bg="#1e1e1e",
            fg="#ffffff"
        )
        self.lbl_title.pack(pady=(20, 10))

        self.lbl_status = tk.Label(
            self.root,
            text="Iniciando conexión con Binance...",
            font=("Arial", 10),
            bg="#1e1e1e",
            fg="#cccccc"
        )
        self.lbl_status.pack(pady=(0, 10))

        self.progress = ttk.Progressbar(
            self.root,
            style="Custom.Horizontal.TProgressbar",
            orient="horizontal",
            length=550,
            mode="determinate",
            maximum=100
        )
        self.progress.pack(pady=5)

        self.lbl_pct = tk.Label(
            self.root,
            text="0%",
            font=("Arial", 10, "bold"),
            bg="#1e1e1e",
            fg="#e0a96d"
        )
        self.lbl_pct.pack(pady=(5, 0))

        self.root.after(100, self._check_queue)

    def _check_queue(self):
        try:
            while not self.queue.empty():
                msg = self.queue.get_nowait()
                if msg == "STOP":
                    self.root.destroy()
                    return
                elif isinstance(msg, dict):
                    status_text = msg.get("status", "")
                    step_increment = msg.get("increment", 1)
                    
                    self.current_step += step_increment
                    pct = int(min(100, (self.current_step / self.total_steps) * 100))
                    
                    self.progress["value"] = pct
                    self.lbl_pct.config(text=f"{pct}%")
                    if status_text:
                        self.lbl_status.config(text=status_text)
        except Exception:
            pass

        self.root.after(100, self._check_queue)

    def run(self):
        self.root.mainloop()


def _worker_process(queue: mp.Queue, total_steps: int):
    os.environ.setdefault("DISPLAY", ":0")
    os.environ.setdefault("XAUTHORITY", f"{Path.home()}/.Xauthority")
    app = _ProgressWindowApp(queue, total_steps)
    app.run()


class IngestionProgressBanner:
    def __init__(self, total_steps: int):
        self.queue = mp.Queue()
        self.process = mp.Process(target=_worker_process, args=(self.queue, total_steps))
        self.process.daemon = True
        self.process.start()

    def update(self, status: str, increment: int = 1):
        self.queue.put({"status": status, "increment": increment})

    def close(self):
        self.queue.put("STOP")
        self.process.join(timeout=1.0)
        if self.process.is_alive():
            self.process.terminate()
