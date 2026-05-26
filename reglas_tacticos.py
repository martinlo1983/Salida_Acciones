"""
reglas_tacticos.py
------------------
Implementa los mecanismos de salida para posiciones Tácticas (Largo Acciones):

  T1 — Stop fijo desde PPP (solo Tipo B)
       Stop = PPP × (1 − X%)   donde X depende del tipo de empresa.
       Se desactiva cuando la ganancia supera +10% y entra T2.

  T2 — Trailing stop con ganancia (Tipo A y B)
       Se activa cuando ganancia sobre PPP > +10%.
       Stop = Máximo desde entrada × (1 − Y%)
       Y% se amplía según ganancia acumulada.
       Tope: 30% para todos los tipos.

  T3 — TIR objetivo (Tipo A y B)
       Solo aplica si se definió TIR objetivo y han pasado ≥ 90 días.
       Se evalúa contra la fase del modelo táctico (OUTPUT_FINAL).

  T4 — Señal del modelo táctico (Tipo A y B)
       Lee FASE y ACCION desde Analizador_Acciones OUTPUT_FINAL.
       DETERIORO → VENTA TOTAL. EUFORIA → reducción parcial.
"""

import io
import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ─── Tablas de stops ──────────────────────────────────────────────────────────

# T1: Stop fijo desde PPP (solo Tipo B)
X_STOP_FIJO = {
    "GROWTH":       0.15,
    "VALUE":        0.10,
    "CÍCLICA":      0.12,
    "TURNAROUND":   0.15,
    "ESPECULATIVA": 0.20,
}

# T2: Trailing stop — Y% base y escalas por ganancia
Y_TRAILING_BASE = {
    "GROWTH":       0.15,
    "VALUE":        0.10,
    "CÍCLICA":      0.15,
    "TURNAROUND":   0.18,
    "ESPECULATIVA": 0.22,
}

Y_TRAILING_30_60 = {
    "GROWTH":       0.225,
    "VALUE":        0.15,
    "CÍCLICA":      0.225,
    "TURNAROUND":   0.27,
    "ESPECULATIVA": 0.30,
}

Y_TRAILING_MAS_60 = {t: 0.30 for t in Y_TRAILING_BASE}  # tope 30% para todos

GANANCIA_T2_ACTIVA = 0.10   # T2 entra cuando ganancia > 10%
T3_DIAS_MINIMOS   = 90      # T3 no aplica antes de 90 días


# ─── Lectura del modelo desde Analizador_Acciones.xlsx ───────────────────────

def leer_modelo_acciones(xlsx_bytes: bytes) -> pd.DataFrame:
    """
    Lee la hoja OUTPUT_FINAL del Analizador de Acciones.
    Retorna DataFrame con las columnas relevantes para el sistema de salidas.
    """
    df = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name="OUTPUT_FINAL")
    df.columns = [str(c).strip() for c in df.columns]

    cols_necesarias = [
        "TICKER", "FASE", "ACCION", "TAMANO_POSICION_PCT",
        "FLAG_REVISION_TESIS", "CONTADOR_TRANSICION",
    ]
    # Solo tomar columnas que existan
    cols_presentes = [c for c in cols_necesarias if c in df.columns]
    df = df[cols_presentes].copy()

    # Tomar solo la fila más reciente por ticker (el CSV se va appendeando)
    if "TICKER" in df.columns:
        df = df.drop_duplicates(subset=["TICKER"], keep="last")

    logger.info("Modelo acciones cargado: %d tickers", len(df))
    return df


def leer_tipo_empresa(xlsx_bytes: bytes) -> pd.DataFrame:
    """
    Lee INPUT_MAN_TICKER del Analizador → tipo de empresa por ticker.
    """
    df = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name="INPUT_MAN_TICKER")
    df.columns = [str(c).strip() for c in df.columns]
    return df[["TICKER", "TYPE"]].rename(columns={"TICKER": "ticker", "TYPE": "tipo_empresa"})


# ─── T1 ───────────────────────────────────────────────────────────────────────

def calcular_t1(tipo: str, ppp_usd: float, precio_actual: float) -> dict:
    x = X_STOP_FIJO.get(tipo.upper(), None)
    if x is None:
        return {"stop_t1_usd": None, "t1_activo": False, "t1_activado": False,
                "t1_detalle": f"Tipo '{tipo}' no reconocido"}

    ganancia = (precio_actual / ppp_usd) - 1 if ppp_usd > 0 else 0
    nivel = ppp_usd * (1 - x)
    activo = ganancia < GANANCIA_T2_ACTIVA  # T1 solo activo antes de que entre T2
    activado = activo and (precio_actual <= nivel)

    return {
        "stop_t1_usd": round(nivel, 2),
        "t1_activo": activo,
        "t1_activado": activado,
        "t1_detalle": f"PPP={ppp_usd:.2f} × (1-{x:.0%}) = {nivel:.2f} | Precio={precio_actual:.2f} | Activo={activo}",
    }


# ─── T2 ───────────────────────────────────────────────────────────────────────

def calcular_t2(tipo: str, ppp_usd: float, precio_actual: float, maximo_usd: float) -> dict:
    ganancia = (precio_actual / ppp_usd) - 1 if ppp_usd > 0 else 0
    t2_activo = ganancia >= GANANCIA_T2_ACTIVA

    if not t2_activo:
        return {
            "stop_t2_usd": None,
            "t2_activo": False,
            "t2_activado": False,
            "y_pct": None,
            "t2_detalle": f"T2 inactivo — ganancia {ganancia:.1%} < {GANANCIA_T2_ACTIVA:.0%}",
        }

    tipo_up = tipo.upper()
    # Ganancia sobre PPP vigente (no sobre el máximo)
    gan_ppp = (precio_actual / ppp_usd) - 1

    if gan_ppp >= 0.60:
        y = Y_TRAILING_MAS_60.get(tipo_up, 0.30)
    elif gan_ppp >= 0.30:
        y = Y_TRAILING_30_60.get(tipo_up, 0.225)
    else:
        y = Y_TRAILING_BASE.get(tipo_up, 0.15)

    y = min(y, 0.30)  # tope duro
    nivel = maximo_usd * (1 - y)
    activado = precio_actual <= nivel

    return {
        "stop_t2_usd": round(nivel, 2),
        "t2_activo": True,
        "t2_activado": activado,
        "y_pct": round(y, 4),
        "t2_detalle": (
            f"Y={y:.1%} | Máx={maximo_usd:.2f} × (1-{y:.1%}) = {nivel:.2f} | "
            f"Precio={precio_actual:.2f} | Gan_PPP={gan_ppp:.1%}"
        ),
    }


# ─── T3 ───────────────────────────────────────────────────────────────────────

def evaluar_t3(
    tir_actual: Optional[float],
    tir_objetivo: Optional[float],
    fecha_primera_compra: date,
    fase_modelo: Optional[str],
) -> dict:
    """
    tir_actual, tir_objetivo: porcentaje anualizado (ej: 25.5 para 25.5%)
    """
    dias = (date.today() - fecha_primera_compra).days

    if tir_objetivo is None:
        return {"t3_aplica": False, "t3_estado": "Sin TIR objetivo definida"}

    if dias < T3_DIAS_MINIMOS:
        return {
            "t3_aplica": False,
            "t3_estado": f"T3 inhibida — solo {dias} días desde entrada (mín {T3_DIAS_MINIMOS})",
        }

    if tir_actual is None:
        return {"t3_aplica": False, "t3_estado": "TIR actual no disponible"}

    if tir_actual < tir_objetivo:
        proximidad = tir_actual / tir_objetivo if tir_objetivo > 0 else 0
        if proximidad >= 0.90:
            return {
                "t3_aplica": True,
                "t3_estado": f"🟡 PRÓXIMA — TIR actual {tir_actual:.1f}% ≥ 90% del objetivo {tir_objetivo:.1f}%",
            }
        return {
            "t3_aplica": False,
            "t3_estado": f"TIR actual {tir_actual:.1f}% < objetivo {tir_objetivo:.1f}%",
        }

    # TIR objetivo alcanzada
    fase = str(fase_modelo or "").upper()
    if any(f in fase for f in ["EUFORIA", "DETERIORO", "TRANSICION"]):
        accion = "Salida total"
    else:
        accion = "Reducción 50%"

    return {
        "t3_aplica": True,
        "t3_estado": f"🟠 TIR OBJETIVO ALCANZADA ({tir_actual:.1f}% ≥ {tir_objetivo:.1f}%) → {accion} | Fase modelo: {fase_modelo}",
    }


# ─── T4 ───────────────────────────────────────────────────────────────────────

def evaluar_t4(fila_modelo: Optional[pd.Series]) -> dict:
    if fila_modelo is None or (hasattr(fila_modelo, "empty") and fila_modelo.empty):
        return {
            "fase_modelo": None,
            "accion_modelo": None,
            "flag_revision": False,
            "t4_alerta": None,
            "t4_detalle": "Sin datos del modelo táctico",
        }

    fase = str(fila_modelo.get("FASE", "")).strip()
    accion = str(fila_modelo.get("ACCION", "")).strip()
    flag = bool(fila_modelo.get("FLAG_REVISION_TESIS", False))
    tamano = fila_modelo.get("TAMANO_POSICION_PCT", None)

    # Determinar alerta T4
    t4_alerta = None
    if "DETERIORO" in fase.upper() or "VENTA TOTAL" in accion.upper():
        t4_alerta = "🔴 SALIR — DETERIORO (T4)"
    elif "EUFORIA" in fase.upper():
        t4_alerta = f"🟠 REDUCIR — EUFORIA (T4) | Tamaño actual: {tamano}%"
    elif flag:
        t4_alerta = "🟡 REVISAR TESIS (T4) — FLAG_REVISION_TESIS activo"

    return {
        "fase_modelo": fase,
        "accion_modelo": accion,
        "flag_revision": flag,
        "tamano_posicion_pct": tamano,
        "t4_alerta": t4_alerta,
        "t4_detalle": f"Fase={fase} | Acción={accion} | Flag={flag} | Tamaño={tamano}%",
    }


# ─── Alerta consolidada ───────────────────────────────────────────────────────

def generar_alerta_tactico(
    ticker: str,
    tipo: str,
    t1: dict,
    t2: dict,
    t3: dict,
    t4: dict,
) -> tuple[str, str]:
    """
    Prioridad: T4 DETERIORO > T1 activado > T2 activado > T4 EUFORIA > T3 > T4 REVISION
    """
    # T4 deterioro / venta total — máxima prioridad
    if t4.get("t4_alerta") and "SALIR" in t4["t4_alerta"]:
        return ("🔴", t4["t4_alerta"])

    # T1 activado (stop fijo — Tipo B)
    if t1.get("t1_activado"):
        return ("🔴", f"STOP T1 ACTIVADO — precio ≤ ${t1['stop_t1_usd']:.2f} (stop fijo {tipo})")

    # T2 activado (trailing)
    if t2.get("t2_activado"):
        return ("🔴", f"STOP T2 ACTIVADO — precio ≤ ${t2['stop_t2_usd']:.2f} (trailing {t2['y_pct']:.1%})")

    # T4 euforia / reducción parcial
    if t4.get("t4_alerta") and "REDUCIR" in t4["t4_alerta"]:
        return ("🟠", t4["t4_alerta"])

    # T3 — TIR objetivo alcanzada o próxima
    t3_estado = t3.get("t3_estado", "")
    if t3.get("t3_aplica"):
        if "PRÓXIMA" in t3_estado:
            return ("🟡", t3_estado)
        return ("🟠", t3_estado)

    # T4 revisión de tesis
    if t4.get("t4_alerta") and "REVISAR" in t4["t4_alerta"]:
        return ("🟡", t4["t4_alerta"])

    # Sin alertas
    stop_activo = t2.get("stop_t2_usd") if t2.get("t2_activo") else t1.get("stop_t1_usd")
    stop_str = f" | Stop activo: ${stop_activo:.2f}" if stop_activo else ""
    fase = t4.get("fase_modelo") or "—"
    return ("🟢", f"MANTENER | Fase: {fase}{stop_str}")
