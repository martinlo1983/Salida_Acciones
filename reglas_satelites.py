"""
reglas_satelites.py
-------------------
Implementa los tres mecanismos de salida para ETFs Satélites:

  S1 — Trailing stop dinámico
       Stop = Máximo desde entrada × (1 − k × σ_mensual_12m)
       k varía por grupo temático y por ganancia acumulada.
       Tope máximo: k × σ nunca supera 0.25 (25%).

  S2 — Rotación por ranking de momentum
       Evalúa mensualmente la posición en el ranking vs. el top 5.
       Δ_momentum = (Score_top5 − Score_ETF) / Score_top5
       Si posición 6-10 y Δ > 20% → ROTAR.
       Si posición > 10 → ROTAR automáticamente.

  S3 — Salida a parking por pérdida de top 15
       Si posición en ranking > 15 → SALIDA TOTAL inmediata.
"""

import logging
import io
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ─── Tabla de k base por grupo temático ──────────────────────────────────────

K_BASE = {
    "Índices amplios":    1.5,
    "Tecnología / Growth": 2.0,
    "Regiones":           2.0,
    "Sectores":           1.75,
    "Factores / Estilos": 1.75,
    "Commodities":        2.5,
}
K_MAX = 5.0
STOP_MAX_DISTANCIA = 0.25   # tope duro: stop nunca a más del 25% del máximo


# ─── Ajuste de k según ganancia acumulada sobre PPP ──────────────────────────

def _multiplicador_k(ganancia_pct: float) -> float:
    """
    ganancia_pct: fracción decimal (ej: 0.15 = +15%)
    """
    if ganancia_pct < 0.10:
        return 1.0
    elif ganancia_pct < 0.30:
        return 1.5
    else:
        return 2.0


# ─── S1: Trailing stop ───────────────────────────────────────────────────────

def calcular_stop_s1(
    grupo: str,
    ppp_usd: float,
    precio_actual_usd: float,
    maximo_usd: float,
    sigma: float,
) -> dict:
    """
    Calcula el nivel de stop S1 y si está activado.

    Retorna dict con:
        k_base, k_ajustado, kxsigma, stop_nivel_usd, stop_activado, detalle
    """
    if not grupo or grupo not in K_BASE:
        return {
            "k_base": None,
            "k_ajustado": None,
            "kxsigma": None,
            "stop_s1_usd": None,
            "s1_activado": False,
            "s1_detalle": f"Grupo '{grupo}' no reconocido — S1 no calculable",
        }

    ganancia = (precio_actual_usd / ppp_usd) - 1 if ppp_usd > 0 else 0
    k_base = K_BASE[grupo]
    mult = _multiplicador_k(ganancia)
    k_ajustado = min(k_base * mult, K_MAX)

    kxsigma = k_ajustado * sigma
    kxsigma = min(kxsigma, STOP_MAX_DISTANCIA)  # tope duro

    stop_nivel = maximo_usd * (1 - kxsigma)
    activado = precio_actual_usd <= stop_nivel

    detalle = (
        f"k_base={k_base} × mult={mult} = k={k_ajustado:.2f} | "
        f"σ={sigma:.4f} | k×σ={kxsigma:.4f} | "
        f"Stop={stop_nivel:.2f} | Precio={precio_actual_usd:.2f} | "
        f"Máx={maximo_usd:.2f} | Gan={ganancia:.1%}"
    )

    return {
        "k_base": k_base,
        "k_ajustado": k_ajustado,
        "kxsigma": round(kxsigma, 4),
        "stop_s1_usd": round(stop_nivel, 2),
        "s1_activado": activado,
        "s1_detalle": detalle,
    }


# ─── Lectura del ranking desde ETFs_Satelites.xlsx ───────────────────────────

def leer_ranking(xlsx_bytes: bytes) -> pd.DataFrame:
    """
    Lee la hoja RANKING del Excel de satélites.
    Retorna DataFrame con columnas: [ticker, grupo, rank_bruto, rank_efectivo, score]
    """
    df = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name="RANKING", header=3)

    # Los headers reales están en fila 2 (0-indexed)
    # Columnas esperadas: Rank Bruto, Rank Efect., Ticker, Grupo, Mom 12m, Mom 3m, Score, ...
    df.columns = [str(c).strip() for c in df.columns]

    # Renombrar para trabajar más cómodo
    rename_map = {
        "Rank Bruto":   "rank_bruto",
        "Rank Efect.":  "rank_efectivo",
        "Ticker":       "ticker",
        "Grupo":        "grupo",
        "Mom 12m":      "mom_12m",
        "Mom 3m":       "mom_3m",
        "Score":        "score",
        "Estado":       "estado",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # Limpiar ticker (puede tener ★)
    df["ticker"] = df["ticker"].astype(str).str.replace("★", "").str.strip()

    # Convertir score a float (puede venir como "90.1%")
    def parse_pct(val):
        if pd.isna(val):
            return None
        s = str(val).replace("%", "").replace(",", ".").strip()
        try:
            v = float(s)
            return v / 100 if v > 1 else v
        except:
            return None

    df["score"] = df["score"].apply(parse_pct)
    df["rank_bruto"] = pd.to_numeric(df["rank_bruto"], errors="coerce")
    df["rank_efectivo"] = pd.to_numeric(df["rank_efectivo"], errors="coerce")

    df = df.dropna(subset=["ticker"])
    df = df[df["ticker"] != "nan"]

    logger.info("Ranking cargado: %d ETFs", len(df))
    return df[["ticker", "grupo", "rank_bruto", "rank_efectivo", "score"]].copy()


# ─── S2 y S3: Rotación y parking ─────────────────────────────────────────────

def evaluar_s2_s3(ticker: str, df_ranking: pd.DataFrame) -> dict:
    """
    Evalúa S2 (rotación por momentum) y S3 (salida a parking) para un ETF.

    Retorna dict con:
        rank_efectivo, score_etf, score_top5, delta_momentum,
        s2_decision, s3_activado, ranking_detalle
    """
    fila = df_ranking[df_ranking["ticker"] == ticker]

    if fila.empty:
        return {
            "rank_bruto": None,
            "rank_efectivo": None,
            "score_etf": None,
            "score_top5": None,
            "delta_momentum": None,
            "s2_decision": "SIN_DATOS",
            "s3_activado": False,
            "ranking_detalle": f"{ticker} no encontrado en el ranking",
        }

    row = fila.iloc[0]
    rank_bruto = row.get("rank_bruto")
    rank_ef = row.get("rank_efectivo")
    score_etf = row.get("score")

    # Score promedio top 5 (rank_efectivo 1-5 con score válido)
    top5 = df_ranking[
        df_ranking["rank_efectivo"].between(1, 5)
    ]["score"].dropna()
    score_top5 = float(top5.mean()) if not top5.empty else None

    # S3: fuera del top 15 en rank bruto
    s3_activado = bool(rank_bruto is not None and rank_bruto > 15)

    # S2: solo aplica si hay rank efectivo (ETFs que pasaron filtros)
    delta = None
    s2_decision = "MANTENER"

    # rank_ef puede ser None o float('nan') dependiendo del origen del dato
    import math
    rank_ef_vacio = rank_ef is None or (isinstance(rank_ef, float) and math.isnan(rank_ef))

    if s3_activado:
        s2_decision = "N/A (S3 activo)"
    elif rank_ef_vacio:
        # ETF no pasó filtros (momentum negativo o bajo MM200) pero está en top 15 bruto
        s2_decision = "VIGILAR — filtros no cumplidos"
    elif score_etf is not None and score_top5 is not None and score_top5 > 0:
        delta = (score_top5 - score_etf) / score_top5
        if rank_ef <= 5:
            s2_decision = "MANTENER — top 5"
        elif rank_ef <= 10:
            if delta > 0.20:
                s2_decision = "ROTAR — Δ_momentum > 20%"
            else:
                s2_decision = "MANTENER — Δ_momentum ≤ 20%"
        else:
            s2_decision = "ROTAR — fuera del top 10"

    score_etf_str  = f"{score_etf:.4f}"  if score_etf  is not None else "N/A"
    score_top5_str = f"{score_top5:.4f}" if score_top5 is not None else "N/A"
    delta_str      = f"{delta:.1%}"      if delta      is not None else "N/A"
    detalle = (
        f"Rank bruto={rank_bruto} | Rank ef.={rank_ef} | "
        f"Score={score_etf_str} | Score top5={score_top5_str} | Δ={delta_str}"
    )

    return {
        "rank_bruto": rank_bruto,
        "rank_efectivo": rank_ef,
        "score_etf": round(score_etf, 4) if score_etf else None,
        "score_top5": round(score_top5, 4) if score_top5 else None,
        "delta_momentum": round(delta, 4) if delta is not None else None,
        "s2_decision": s2_decision,
        "s3_activado": s3_activado,
        "ranking_detalle": detalle,
    }


# ─── Alerta consolidada ───────────────────────────────────────────────────────

def generar_alerta_satelite(
    ticker: str,
    s1: dict,
    s2s3: dict,
) -> tuple[str, str]:
    """
    Combina S1, S2, S3 y retorna (emoji_alerta, texto_alerta).
    El primero en activarse gana.
    """
    # Sin datos de ranking — ticker no encontrado en el universo
    if s2s3.get("s2_decision") == "SIN_DATOS":
        return ("🟡", f"VIGILAR — {ticker} sin datos en ranking, verificar manualmente")

    # S3 — salida dura a parking
    if s2s3.get("s3_activado"):
        return ("🔴", f"SALIR A PARKING — {ticker} fuera del top 15 del ranking")

    # S1 — trailing stop activado
    if s1.get("s1_activado"):
        return ("🔴", f"TRAILING STOP ACTIVADO — precio cayó hasta ${s1['stop_s1_usd']:.2f} (stop S1)")

    # S2 — rotar
    s2 = s2s3.get("s2_decision", "")
    if "ROTAR" in s2:
        delta = s2s3.get("delta_momentum")
        delta_str = f" (Δ={delta:.1%})" if delta else ""
        return ("🔴", f"ROTAR — momentum insuficiente{delta_str} | {s2}")

    # Vigilar (momentum negativo o filtros no cumplidos, rank bruto ≤ 15)
    if "VIGILAR" in s2:
        rank_ef = s2s3.get("rank_efectivo")
        rank_br = s2s3.get("rank_bruto")
        return ("🟡", f"VIGILAR — rank bruto {rank_br}, filtros no cumplidos (momentum negativo o bajo MM200)")

    # Todo ok
    stop_s1 = s1.get("stop_s1_usd")
    stop_str = f" | Stop S1: ${stop_s1:.2f}" if stop_s1 else ""
    rank_ef = s2s3.get("rank_efectivo")
    return ("🟢", f"MANTENER — rank {rank_ef}{stop_str}")
