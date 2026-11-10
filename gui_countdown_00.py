import tkinter as tk
import sys
import subprocess
import re

def obtener_monitores():
    """Detecta los monitores activos y sus coordenadas usando xrandr en Linux."""
    monitores = []
    try:
        salida = subprocess.check_output(['xrandr']).decode('utf-8')
        # Busca el patrón de resolución y offset: ej. "1920x1080+1920+0"
        patron = re.compile(r' (\d+)x(\d+)\+(\d+)\+(\d+)')
        for linea in salida.splitlines():
            if " connected" in linea:
                match = patron.search(linea)
                if match:
                    w, h, x, y = map(int, match.groups())
                    monitores.append({'w': w, 'h': h, 'x': x, 'y': y})
    except Exception as e:
        print(f"Error detectando monitores con xrandr: {e}")
        
    # Fallback de seguridad si xrandr falla (asume un solo monitor)
    if not monitores:
        root_temp = tk.Tk()
        monitores.append({'w': root_temp.winfo_screenwidth(), 'h': root_temp.winfo_screenheight(), 'x': 0, 'y': 0})
        root_temp.destroy()
        
    return monitores

class CuentaRegresivaApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw() # Ocultamos la ventana base invisible
        self.tiempo_restante = 10
        self.etiquetas_reloj = []
        
        monitores = obtener_monitores()
        
        # Generar una ventana clonada para cada monitor
        for mon in monitores:
            top = tk.Toplevel(self.root)
            top.title("Iniciando Ingesta Binance")
            
            # Cálculo de geometría centrado para ESTE monitor específico
            ancho_ventana = 800
            alto_ventana = 400
            pos_x = mon['x'] + int((mon['w'] / 2) - (ancho_ventana / 2))
            pos_y = mon['y'] + int((mon['h'] / 2) - (alto_ventana / 2))
            
            top.geometry(f"{ancho_ventana}x{alto_ventana}+{pos_x}+{pos_y}")
            top.configure(bg="#2b2b2b")
            top.attributes("-topmost", True)
            
            # Si el usuario presiona la 'X' nativa de la ventana, asume cancelación
            top.protocol("WM_DELETE_WINDOW", self.cancelar)
            
            lbl_titulo = tk.Label(top, text="El proceso de ingesta comenzará en:", font=("Arial", 24, "bold"), bg="#2b2b2b", fg="white")
            lbl_titulo.pack(pady=40)
            
            lbl_reloj = tk.Label(top, text=str(self.tiempo_restante), font=("Arial", 90, "bold"), bg="#2b2b2b", fg="#e0a96d")
            lbl_reloj.pack(pady=10)
            self.etiquetas_reloj.append(lbl_reloj)
            
            frame_btn = tk.Frame(top, bg="#2b2b2b")
            frame_btn.pack(pady=30)
            
            btn_aceptar = tk.Button(frame_btn, text="Aceptar (Iniciar ya)", font=("Arial", 16, "bold"), bg="#4caf50", fg="white", cursor="hand2", command=self.aceptar)
            btn_aceptar.pack(side=tk.LEFT, padx=30)
            
            btn_cancelar = tk.Button(frame_btn, text="Cancelar Proceso", font=("Arial", 16, "bold"), bg="#f44336", fg="white", cursor="hand2", command=self.cancelar)
            btn_cancelar.pack(side=tk.RIGHT, padx=30)
            
        self.actualizar_reloj()

    def actualizar_reloj(self):
        self.tiempo_restante -= 1
        if self.tiempo_restante <= 0:
            self.aceptar()
        else:
            # Sincroniza el tiempo en todas las ventanas activas
            for lbl in self.etiquetas_reloj:
                lbl.config(text=str(self.tiempo_restante))
            self.root.after(1000, self.actualizar_reloj)

    def aceptar(self):
        self.root.destroy()
        sys.exit(0)

    def cancelar(self):
        self.root.destroy()
        sys.exit(1)

if __name__ == "__main__":
    try:
        app = CuentaRegresivaApp()
        app.root.mainloop()
    except Exception as e:
        print(f"Error gráfico detectado: {e}")
        # En caso de fallo crítico de Tkinter, asume retorno 0 (Aceptar) 
        # para que el orquestador principal no se bloquee.
        sys.exit(0)
