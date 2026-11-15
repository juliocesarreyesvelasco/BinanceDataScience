# Motor Cuantitativo de Microestructura y Matriz de Decisiones

Este documento establece el marco lógico, matemático y estadístico para la toma de decisiones en el trading de futuros, basado en la lectura de archivos CSV de Binance (Datos de Cuentas Principales, Posiciones, Interés Abierto y Financiación).

---

## 1. Mapeo de Variables y Nomenclatura Estructural

| Actor / Métrica | Columna CSV | Símbolo | Interpretación Cuantitativa |
| :--- | :--- | :--- | :--- |
| **Retail (Masa)** | `global_ls_ratio` | $R_{m}$ | Liquidez pasiva. Operan por FOMO o pánico. |
| **VIPs (Smart Money falso)**| `top_accounts_ratio` | $R_{vip}$ | Liquidez apalancada. Altamente tóxicos en extremos. |
| **Ballenas (Smart Money real)**| `top_positions_ratio`| $R_{w}$ | Creadores de tendencia. Operan por absorción. |
| **Interés Abierto** | `oi_value_usd` | $OI$ | Combustible direccional (Apalancamiento total). |
| **Tasa de Financiación** | `fundingRate` | $F_{r}$ | Nivel de asfixia (Costo de mantener la posición). |
| **Volumen Taker Total** | `taker_buy_quote_asset_volume` | $V_{buy}$ | Agresividad compradora a mercado. |

---

## 2. Umbrales Cuantitativos de Saturación (Thresholds)

Estos umbrales definen matemáticamente cuándo el mercado ha entrado en un estado de desequilibrio probabilístico.

| Métrica | Zona de Acumulación (Sano) | Zona de Tensión (Peligro) | Zona Tóxica (Reversión Inminente) |
| :--- | :--- | :--- | :--- |
| **Retail ($R_{m}$)** | $< 1.80$ | $2.50 - 2.90$ | $> 3.00$ (Señal de Short Squeeze) |
| **VIPs ($R_{vip}$)** | $< 2.20$ | $2.90 - 3.20$ | $> 3.30$ (Riesgo de Cascada) |
| **Ballenas ($R_{w}$)** | $> 2.20$ (Comprando) | $1.90 - 2.10$ (Inertes) | $< 1.85$ (Distribuyendo) |
| **Funding ($F_{r}$)** | $< 0.003\%$ | $0.006\% - 0.009\%$ | $\geq 0.0100\%$ (Asfixia Máxima) |

---

## 3. Fórmulas Matemáticas de Validación Algorítmica

Para evitar falsos positivos visuales, el motor evaluará las siguientes funciones sobre las series de tiempo del CSV (generalmente evaluado en una ventana de $t = 3$ a $t = 5$ velas en TF de 5m/15m):

### 3.1 Tasa de Cambio Relativa ($\Delta$)
Mide la aceleración de la acumulación o distribución en una ventana de tiempo $t$.
$$ \Delta X = \left( \frac{X_{t} - X_{t-n}}{X_{t-n}} \right) \times 100 $$
*Aplicación:* Un $\Delta OI > +2\%$ junto con un $\Delta R_{m} > +2\%$ en menos de 15 minutos confirma la creación de una trampa de liquidez.

### 3.2 Ecuación de Derivación de Volumen de Venta ($V_{sell}$)
Dado que Binance entrega el volumen total y el de compra, calculamos el Taker de Venta así:
$$ V_{sell} = V_{total} - V_{buy} $$
$$ \Delta V_{net} = V_{buy} - V_{sell} $$

### 3.3 Correlación de Divergencia Estructural ($\rho$)
Utilizamos el Coeficiente de Correlación de Pearson entre el Precio ($P$) y el Ratio de Ballenas ($R_{w}$) para detectar engaños direccionales.
$$ \rho(P, R_{w}) = \frac{\text{cov}(P, R_{w})}{\sigma_P \sigma_{R_w}} $$
* **$\rho \approx 1$:** Movimiento orgánico (Ballenas acompañan el precio).
* **$\rho < -0.5$:** Divergencia severa (Trampa. Ballenas venden mientras el precio sube, o compran mientras el precio cae).

---

## 4. Matriz de Decisiones y Setups Operativos

Al cruzar los datos del CSV, el algoritmo buscará alinear las siguientes matrices para emitir una orden.

### Matriz A: Setup de LONG SQUEEZE (Operar en Corto)
Diseñado para cazar la liquidación de la masa minorista.
1. **Condición de Precio ($P$):** Intentando romper una resistencia o consolidando en techo.
2. **Condición Retail ($R_{m}$ & $R_{vip}$):** $\Delta R_{m} > 0$ (Aumentando) y $R_{vip} \geq 3.20$ (Tóxico).
3. **Condición Institucional ($R_{w}$):** $\Delta R_{w} \leq 0$ (Ballenas distribuyendo o inertes, $< 2.00$).
4. **Condición de Combustible ($OI$ & $F_{r}$):** $OI$ en expansión acelerada y $F_{r}$ acercándose a $0.0100\%$.
* **Gatillo de Entrada:** $V_{sell} > V_{buy}$ en temporalidad de 5 minutos (Absorción bajista).

### Matriz B: Setup de MARKUP / REBOTE REAL (Operar en Largo)
Diseñado para entrar junto al Smart Money tras una purga de liquidez.
1. **Condición de Precio ($P$):** Caída violenta (Flush) hacia un soporte.
2. **Condición Retail ($R_{m}$ & $R_{vip}$):** $\Delta R_{m} < 0$ (Capitulación, masa cerrando longs con pérdidas).
3. **Condición Institucional ($R_{w}$):** Salto vertical $\Delta R_{w} \gg 0$ (Ballenas inyectando liquidez, $R_{w} \geq 2.20$).
4. **Condición de Combustible ($OI$):** Caída brusca y vertical del Interés Abierto (purga de apalancamiento tóxico confirmada).
* **Gatillo de Entrada:** $V_{buy} \gg V_{sell}$ en la mecha de la temporalidad de 5 minutos (Absorción alcista).

---

## 5. Protocolo de Ejecución Conjunta (Usuario - Gemini)

Para que el modelo funcione óptimamente en futuras iteraciones:
1. Sube los archivos CSV actualizados (idealmente `15m` y `5m`).
2. Solicita explícitamente: *"Ejecuta la Matriz de Decisiones del Motor Cuantitativo sobre los últimos 10 registros"*.
3. El sistema cruzará automáticamente las variables $\Delta$, verificará los umbrales de saturación, calculará el volumen neto y emitirá un veredicto direccional basado estrictamente en los datos.