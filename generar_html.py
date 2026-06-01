"""
generar_html.py — Dashboard HTML del Monitor de Salidas.

Look & feel: consistente con dashboard_acciones.html
  - Fondo claro #F5F4F0, header oscuro #2C2C2A
  - Tipografía sistema (-apple-system, Segoe UI, sans-serif)
  - Cards blancas con border sutil
  - Badges de fase con color semántico
  - Tooltip system global (fijo, viewport-aware)

Cambios respecto a la versión anterior:
  - Solo muestra activos en tenencia (resultados ya filtrados desde main.py,
    pero se filtra explícitamente cualquier posición sin precio ni PPP)
  - Todos los stops se muestran siempre, con estado claro:
      ACTIVO / PENDIENTE (ganancia < 10%) / NO APLICA (Tipo A o acción no táctica)
      SIN DATOS (falta info para calcularlo)
  - Tooltips ricos en encabezados, labels y valores importantes
"""

import json
from datetime import datetime


# ─── Tooltips ──────────────────────────────────────────────────────────────────

TOOLTIPS = {
    # Campos comunes
    "ticker": {
        "titulo": "Ticker (subyacente NYSE/NASDAQ)",
        "desc": "Símbolo del activo subyacente que cotiza en NYSE o NASDAQ. La señal de salida se calcula sobre este precio en USD, aunque la operación real ocurra en el CEDEAR en ARS.",
    },
    "categoria": {
        "titulo": "Categoría de posición",
        "desc": "Largo Satelites: ETFs diversificados que forman el núcleo de largo plazo. Largo Acciones: posiciones tácticas en acciones individuales.",
    },
    "tipo_ab": {
        "titulo": "Tipo A vs Tipo B",
        "desc": "Tipo A — Convicción fundamental: la caída de precio es oportunidad de acumular. No tiene stop fijo T1. La salida la determina el modelo (T4). Tipo B — Oportunidad táctica: tiene stop fijo T1 desde el día 1. Si el precio cae significativamente, el catalizador puede haber fallado.",
    },
    "tipo_empresa": {
        "titulo": "Tipo de empresa",
        "desc": "Determina los parámetros de stop: GROWTH (15% fijo, 15% trailing base) · VALUE (10% / 10%) · CÍCLICA (12% / 15%) · TURNAROUND (15% / 18%) · ESPECULATIVA (20% / 22%). Los stops se amplían con la ganancia acumulada.",
    },
    "ganancia_pct": {
        "titulo": "Ganancia % (Portfolio Performance)",
        "desc": "Retorno sobre el costo de compra, calculado por Portfolio Performance en USD. Se usa para determinar si T2 (trailing stop) ya está activo (requiere ganancia > 10%) y el multiplicador de holgura del stop.",
        "formula": "(valor_mercado − coste_compra) / coste_compra",
    },
    "ppp_equiv_usd": {
        "titulo": "PPP equivalente (precio promedio ponderado)",
        "desc": "Precio promedio ponderado del subyacente en USD, retrocomputado desde la ganancia de Portfolio Performance. Es el precio de referencia para calcular T1 y T2. Si acumulás más posición, el PPP se recalcula y los stops se ajustan automáticamente.",
        "formula": "precio_actual_USD / (1 + ganancia_PP)",
    },
    "fecha_primera_compra": {
        "titulo": "Fecha de primera compra (posición actual)",
        "desc": "Fecha desde la que se calcula el máximo histórico y la σ. Si la posición fue vendida y recomprada, esta es la fecha de la re-entrada, no de la compra original. Así el máximo y el stop son correctos para la posición vigente.",
    },
    "precio_actual_usd": {
        "titulo": "Precio actual (subyacente en USD)",
        "desc": "Último precio de cierre del subyacente en NYSE/NASDAQ, obtenido via yfinance. Es el precio sobre el que se evalúan todos los disparadores de salida. La ejecución real es en el CEDEAR en ARS.",
    },
    "maximo_desde_entrada_usd": {
        "titulo": "Máximo desde entrada",
        "desc": "Mayor precio de cierre alcanzado por el subyacente desde la fecha de primera compra. Nunca retrocede. Es la base del trailing stop: Stop = Máximo × (1 − distancia%). Cuando el precio sube, el máximo se actualiza y el stop sube con él.",
    },
    "sigma_mensual_12m": {
        "titulo": "Volatilidad mensual promedio (σ 12m)",
        "desc": "Desviación estándar de los 12 retornos mensuales del último año (cierre a cierre de cada mes). Se usa para calibrar el trailing stop S1 de satélites: a mayor σ, mayor holgura. Se recalcula mensualmente. Se expresa como % mensual.",
        "formula": "std(retornos mensuales últimos 12 meses)",
    },
    # Satélites
    "grupo_satelite": {
        "titulo": "Grupo temático del ETF",
        "desc": "Determina el k base del trailing stop S1: Índices amplios (k=1.5) · Tecnología/Growth (k=2.0) · Regiones (k=2.0) · Sectores (k=1.75) · Factores/Estilos (k=1.75) · Commodities (k=2.5). Los activos más volátiles necesitan más holgura.",
    },
    "rank_bruto": {
        "titulo": "Rank bruto (ranking de momentum)",
        "desc": "Posición en el ranking de momentum entre todos los ETFs del universo. Si cae por debajo del top 15 (rank > 15), se activa S3: salida total inmediata a parking, sin análisis adicional.",
    },
    "rank_efectivo": {
        "titulo": "Rank efectivo",
        "desc": "Posición considerando solo ETFs que pasaron filtros de calidad (momentum 3m positivo y precio sobre MM200). Top 5 → mantener automático. Posición 6-10 → evaluar Δ momentum. Fuera del top 10 → rotar.",
    },
    "delta_momentum": {
        "titulo": "Δ Momentum (diferencia relativa)",
        "desc": "Diferencia entre el score promedio del top 5 y el score del ETF en cartera, relativa al top 5. Si el ETF está en posición 6-10 y Δ > 20%, se debe rotar: hay algo significativamente mejor disponible.",
        "formula": "(Score_top5 − Score_ETF) / Score_top5",
    },
    "stop_s1_usd": {
        "titulo": "Stop S1 — Trailing stop dinámico",
        "desc": "Nivel de precio que dispara la salida del ETF satélite. Se recalcula mensualmente. Si el precio cae hasta este nivel, salida total a parking sin esperar confirmación adicional.",
        "formula": "Máximo_desde_entrada × (1 − k × σ_mensual_12m)",
    },
    "kxsigma": {
        "titulo": "k × σ (distancia porcentual al stop S1)",
        "desc": "Porcentaje de caída desde el máximo que activa el stop. Está topado al 25% máximo. k = k_base × multiplicador_ganancia (1.0x / 1.5x / 2.0x según ganancia acumulada). A mayor ganancia acumulada, más holgura para dejar correr.",
        "formula": "min(k_ajustado × σ_mensual_12m, 0.25)",
    },
    "s2_decision": {
        "titulo": "Decisión S2 — Rotación por momentum",
        "desc": "Evaluada mensualmente: MANTENER top 5 (automático) · MANTENER posición 6-10 si Δ_momentum ≤ 20% · ROTAR posición 6-10 si Δ_momentum > 20% · ROTAR fuera del top 10 (automático). La rotación no depende del tiempo en cartera, solo del momentum relativo.",
    },
    "s3_activado": {
        "titulo": "S3 — Salida a parking (top 15)",
        "desc": "Regla dura: si el ETF cae fuera del top 15 del ranking bruto en cualquier actualización, salida total inmediata a parking. Sin análisis, sin esperar confirmación. El capital se reasigna en la próxima ronda mensual.",
    },
    # Tácticos — T1
    "stop_t1_usd": {
        "titulo": "Stop T1 — Stop fijo desde PPP (solo Tipo B)",
        "desc": "Protección de capital desde el primer día para posiciones Tipo B. Nivel fijo calculado sobre el PPP actual. Se desactiva automáticamente cuando T2 entra en vigencia (ganancia ≥ 10%). Si promediás a la baja, el PPP baja y T1 también baja con él.",
        "formula": "PPP × (1 − X%)  donde X depende del tipo de empresa",
    },
    "t1_activo": {
        "titulo": "T1 vigente",
        "desc": "T1 solo está activo mientras la ganancia sobre PPP sea menor al 10%. Cuando la ganancia supera ese umbral, T2 entra en vigencia y T1 se desactiva permanentemente para esa posición.",
    },
    # Tácticos — T2
    "stop_t2_usd": {
        "titulo": "Stop T2 — Trailing stop con ganancia",
        "desc": "Se activa cuando la ganancia sobre PPP supera el +10%. Reemplaza a T1 en Tipo B; es el primer mecanismo de protección en Tipo A. El Y% se amplía con la ganancia acumulada para dejar correr posiciones ganadoras. Tope: 30% para todos los tipos.",
        "formula": "Máximo_desde_entrada × (1 − Y%)  donde Y depende del tipo y la ganancia",
    },
    "y_pct": {
        "titulo": "Y% (distancia trailing T2 al máximo)",
        "desc": "Porcentaje de caída desde el máximo que activa T2. Aumenta con la ganancia: base (ganancia < 30%) → ×1.5 (ganancia 30-60%) → ×2.0 (ganancia > 60%). Tope duro: 30%. A mayor ganancia acumulada, más espacio para no cortar la tendencia.",
    },
    # Tácticos — Modelo
    "fase_modelo": {
        "titulo": "Fase del modelo táctico",
        "desc": "Fase del análisis de calidad, earnings y valuación del Analizador de Acciones: EXPANSIÓN · RECUPERACIÓN · TRANSICIÓN · EUFORIA · DETERIORO. En Tipo A es el driver principal de salida (T4). En Tipo B es una capa adicional sobre los stops de precio.",
    },
    "accion_modelo": {
        "titulo": "Acción del modelo táctico",
        "desc": "Señal de acción del modelo: COMPRA PARCIAL / VENTA TOTAL / REDUCIR / etc. DETERIORO + VENTA TOTAL → salida total inmediata (aplica Tipo A y B). EUFORIA → reducción parcial según tamaño de posición.",
    },
    "flag_revision": {
        "titulo": "Flag de revisión de tesis",
        "desc": "Se activa cuando el modelo detecta deterioro por 2 corridas consecutivas sin mejora. Para Tipo A significa probable salida total. Requiere revisión activa de los fundamentals antes de la próxima corrida.",
    },
    "tamano_posicion_pct": {
        "titulo": "Tamaño sugerido de posición (%)",
        "desc": "Porcentaje del capital asignado que el modelo sugiere mantener. En señales de EUFORIA: posición 75-100% → reducir a 50%, posición 50% → reducir a 25%, posición 25% → mantener o salir total a criterio.",
    },
    "t3_estado": {
        "titulo": "T3 — Objetivo de rentabilidad (toma parcial)",
        "desc": "Se activa cuando el precio supera el objetivo % sobre PPP configurado en CONFIG. Aplica tanto a Tipo A como Tipo B. Acción según fase del modelo: EXPANSIÓN / RECUPERACIÓN → reducción 50% (seguís en la posición); EUFORIA / DETERIORO / TRANSICIÓN → salida total. Corre en paralelo con T2, el que se active primero manda.",
    },
    "tir_objetivo": {
        "titulo": "Objetivo de rentabilidad (%)",
        "desc": "Ganancia absoluta sobre el PPP que definiste como meta al entrar. Se configura en la hoja CONFIG del Excel. El precio objetivo es fijo: PPP × (1 + objetivo%). Cuando el precio lo supera, T3 se activa independientemente del tiempo transcurrido.",
        "formula": "Precio objetivo = PPP × (1 + objetivo%)",
    },
    "alerta_texto": {
        "titulo": "Alerta de salida",
        "desc": "🟢 MANTENER: sin disparadores activos · 🟡 VIGILAR: monitorear próxima evaluación · 🟠 ACCIÓN PRÓXIMA: TIR objetivo alcanzada o Euforia (reducción parcial) · 🔴 ACCIÓN INMEDIATA: stop activado, deterioro o salida a parking.",
    },
}


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _safe(v, decimals=2):
    if v is None:
        return None
    if isinstance(v, float) and v != v:   # NaN
        return None
    if isinstance(v, float):
        return round(v, decimals)
    return v


def _stop_estado_acciones(r: dict) -> dict:
    """
    Construye la info completa de los tres stops tácticos para mostrar siempre,
    independientemente de si están activos o no.

    Retorna dict con entradas t1, t2, t3, cada una con:
      {precio, activo, activado, estado, estado_label, nota}
    """
    es_tipo_a = str(r.get("tipo_ab") or "B").upper() == "A"
    tipo = str(r.get("tipo_empresa") or "").upper()
    gan = r.get("ganancia_pct")   # ya es % (ej: 25.3 para +25.3%)

    # T1
    t1_precio = r.get("stop_t1_usd")
    t1_activo = r.get("t1_activo")
    t1_activado = r.get("t1_activado")
    if es_tipo_a:
        t1_estado = "no_aplica"
        t1_nota = "Tipo A: la caída de precio es oportunidad de acumular, no señal de salida. Sin stop fijo."
    elif t1_precio is None:
        t1_estado = "sin_datos"
        t1_nota = "Sin datos suficientes para calcular T1 (falta PPP o tipo de empresa)."
    elif t1_activado:
        t1_estado = "activado"
        t1_nota = f"Stop T1 ACTIVADO — precio cayó por debajo del nivel de stop fijo."
    elif t1_activo:
        t1_estado = "vigente"
        t1_nota = f"Stop fijo activo. Se desactivará cuando ganancia sobre PPP supere el +10%."
    else:
        t1_estado = "reemplazado"
        t1_nota = "T1 reemplazado por T2 (ganancia ≥ +10%). T2 es permanente hasta la salida."

    # T2
    t2_precio = r.get("stop_t2_usd")
    t2_activo = r.get("t2_activo")
    t2_activado = r.get("t2_activado")
    y_pct = r.get("y_pct")
    if t2_activado:
        t2_estado = "activado"
        t2_nota = f"Trailing stop T2 ACTIVADO — precio cayó por debajo del nivel de stop."
    elif t2_activo and t2_precio is not None:
        t2_estado = "vigente"
        t2_nota = f"Trailing activo con holgura {round(y_pct*100,1) if y_pct else '?'}% desde el máximo."
    elif t2_precio is None and gan is not None and gan < 10:
        t2_estado = "pendiente"
        t2_nota = f"T2 se activará cuando la ganancia sobre PPP supere el +10% (ahora en {round(gan,1)}%)."
    elif t2_precio is None:
        t2_estado = "sin_datos"
        t2_nota = "Sin datos suficientes para calcular T2 (falta precio máximo o PPP)."
    else:
        t2_estado = "sin_datos"
        t2_nota = "Sin datos suficientes para calcular T2."

    # T3
    t3_estado_str = r.get("t3_estado") or ""
    if "ALCANZADA" in t3_estado_str.upper():
        t3_estado = "activado"
    elif "PRÓXIMA" in t3_estado_str.upper() or "PROXIMA" in t3_estado_str.upper():
        t3_estado = "proximo"
    elif "INHIBIDA" in t3_estado_str.upper() or "MESES" in t3_estado_str.upper() or "DÍAS" in t3_estado_str.upper():
        t3_estado = "inhibida"
    elif "SIN TIR" in t3_estado_str.upper() or "NO DISPONIBLE" in t3_estado_str.upper():
        t3_estado = "sin_objetivo"
    else:
        t3_estado = "ok"

    return {
        "t1": {
            "precio": t1_precio,
            "estado": t1_estado,
            "nota": t1_nota,
        },
        "t2": {
            "precio": t2_precio,
            "y_pct": y_pct,
            "estado": t2_estado,
            "nota": t2_nota,
        },
        "t3": {
            "estado": t3_estado,
            "texto": t3_estado_str,
        },
    }


# ─── Generador principal ────────────────────────────────────────────────────────

def generar_html(resultados: list, cambios: list, historial: list) -> str:
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Filtrar posiciones sin datos de mercado (sin tenencia real)
    resultados = [
        r for r in resultados
        if r.get("precio_actual_usd") is not None
        or r.get("ppp_equiv_usd") is not None
        or r.get("coste_compra_usd", 0) > 0
    ]

    data = {
        "estado":    [{k: _safe(v) for k, v in r.items()} for r in resultados],
        "cambios":   [{k: _safe(v) for k, v in c.items()} for c in cambios],
        "historial": [{k: _safe(v) for k, v in h.items()} for h in historial],
        "tooltips":  TOOLTIPS,
        "fecha":     fecha,
    }
    data_json = json.dumps(data, default=str, ensure_ascii=False)

    # ── CSS ──────────────────────────────────────────────────────────────────
    css = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#F5F4F0;color:#2C2C2A;font-size:13px;line-height:1.5}
a{color:inherit;text-decoration:none}

/* HEADER */
header{background:#2C2C2A;color:#F1EFE8;padding:13px 24px;display:flex;align-items:center;justify-content:space-between}
header h1{font-size:16px;font-weight:500;letter-spacing:-.2px}
header span{font-size:11px;opacity:.55}

/* TABS */
.tabs{display:flex;background:#2C2C2A;padding:0 24px}
.tab{padding:10px 18px;color:#B4B2A9;cursor:pointer;font-size:12px;font-weight:500;border-bottom:2px solid transparent;transition:color .15s}
.tab:hover{color:#F1EFE8}
.tab.active{color:#F1EFE8;border-bottom-color:#F1EFE8}

/* CONTENT AREAS */
.view{display:none;padding:16px 24px}.view.active{display:block}

/* FILTERS */
.filters-bar{background:#fff;border:1px solid #E0DDD5;border-radius:8px;padding:10px 14px;margin-bottom:12px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.fi{padding:5px 9px;border:1px solid #D3D1C7;border-radius:5px;font-size:12px;color:#2C2C2A;background:#fff;outline:none}
.fi:focus{border-color:#2C2C2A}
.fl{font-size:11px;color:#888780;font-weight:500}
.fb{padding:4px 11px;border:1px solid #D3D1C7;border-radius:5px;font-size:11px;background:#fff;cursor:pointer;color:#5F5E5A;transition:all .12s}
.fb:hover,.fb.on{background:#2C2C2A;color:#F1EFE8;border-color:#2C2C2A}

/* TABLE */
.tw{overflow-x:auto;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.07)}
table{width:100%;border-collapse:collapse;background:#fff;font-size:12px}
thead{background:#2C2C2A}
th{padding:9px 11px;text-align:left;color:#B4B2A9;font-weight:500;white-space:nowrap;cursor:pointer;font-size:11px;position:relative}
th:hover{color:#F1EFE8}
th.asc::after{content:" ↑"}th.desc::after{content:" ↓"}
td{padding:7px 11px;border-bottom:1px solid #F5F4F0;vertical-align:middle;white-space:nowrap}
tr:last-child td{border-bottom:none}
tr:hover td{background:#FAFAF8;cursor:pointer}
.ticker-cell{font-weight:600;font-size:13px}

/* ALERT ROW COLORS */
.rr td{background:#FEF2F2}.ro td{background:#FFF7ED}.ry td{background:#FEFCE8}.rg td{background:#F0FDF4}

/* VALUE COLORS */
.pos{color:#085041;font-weight:600}.neg{color:#791F1F;font-weight:600}.dim{color:#B4B2A9}
.ag{color:#085041}.ay{color:#856404}.ao{color:#9a3412}.ar{color:#791F1F}

/* BADGES */
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:500}
.fase-EXPANSION,.fase-EXPANSIÓN{background:#E1F5EE;color:#085041}
.fase-RECUPERACION,.fase-RECUPERACIÓN{background:#FAEEDA;color:#633806}
.fase-TRANSICION,.fase-TRANSICIÓN{background:#F1EFE8;color:#5F5E5A}
.fase-EUFORIA{background:#FAECE7;color:#712B13}
.fase-DETERIORO{background:#FCEBEB;color:#791F1F}

/* STOP STATUS BADGES */
.stop-badge{display:inline-block;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:600;letter-spacing:.03em}
.sb-activado{background:#FCEBEB;color:#791F1F;border:1px solid #FCA5A5}
.sb-vigente{background:#E1F5EE;color:#085041;border:1px solid #86EFAC}
.sb-pendiente{background:#FAEEDA;color:#633806;border:1px solid #FCD34D}
.sb-reemplazado{background:#F1EFE8;color:#5F5E5A;border:1px solid #D3D1C7}
.sb-no-aplica{background:#F5F4F0;color:#888780;border:1px solid #D3D1C7}
.sb-sin-datos{background:#FFF7ED;color:#9a3412;border:1px solid #FED7AA}
.sb-inhibida{background:#F1EFE8;color:#5F5E5A;border:1px solid #D3D1C7}
.sb-sin-objetivo{background:#F5F4F0;color:#888780;border:1px solid #D3D1C7}
.sb-proximo{background:#FAEEDA;color:#633806;border:1px solid #FCD34D}
.sb-ok{background:#F0FDF4;color:#085041;border:1px solid #86EFAC}

/* ── DETALLE LAYOUT ── */
.det-wrap{display:flex;height:calc(100vh - 118px)}
.det-sidebar{width:150px;flex-shrink:0;border-right:1px solid #E8E6E0;overflow-y:auto;padding:8px;background:#fff}
.tbtn{display:flex;justify-content:space-between;align-items:center;padding:7px 9px;border-radius:5px;border:1px solid transparent;cursor:pointer;font-size:11px;color:#5F5E5A;background:transparent;width:100%;margin-bottom:2px;font-family:inherit;gap:6px}
.tbtn:hover{background:#F5F4F0}
.tbtn.on{background:#F5F4F0;border-color:#D3D1C7;color:#2C2C2A;font-weight:600}
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.dg{background:#22c55e}.dy{background:#eab308}.do{background:#f97316}.dr_{background:#ef4444}

/* DETALLE MAIN */
.det-main{flex:1;overflow-y:auto;padding:20px 24px;min-width:0;background:#F5F4F0}
.det-hdr{display:flex;align-items:center;gap:10px;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid #E8E6E0;flex-wrap:wrap}
.det-ticker{font-size:28px;font-weight:600;color:#2C2C2A;letter-spacing:-.5px}
.tag{font-size:10px;color:#5F5E5A;background:#fff;padding:3px 9px;border-radius:4px;border:1px solid #E0DDD5}
.alert-pill{font-size:12px;padding:4px 12px;border-radius:5px;font-weight:500}
.ap-g{background:#E1F5EE;color:#085041;border:1px solid #86EFAC}
.ap-y{background:#FAEEDA;color:#633806;border:1px solid #FCD34D}
.ap-o{background:#FAECE7;color:#712B13;border:1px solid #FDBA74}
.ap-r{background:#FCEBEB;color:#791F1F;border:1px solid #FCA5A5}

/* METRIC CARDS */
.mcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(115px,1fr));gap:8px;margin-bottom:14px}
.mc{background:#fff;border:1px solid #E8E6E0;border-radius:7px;padding:10px 12px}
.mc-label{font-size:9px;color:#888780;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;display:flex;align-items:center;gap:4px}
.mc-val{font-size:16px;font-weight:500;color:#2C2C2A}
.mc-val.pos{color:#085041}.mc-val.neg{color:#791F1F}.mc-val.sm{font-size:12px}

/* PANELS */
.panel{background:#fff;border:1px solid #E8E6E0;border-radius:8px;padding:14px 16px;margin-bottom:12px}
.panel-title{font-size:10px;color:#888780;text-transform:uppercase;letter-spacing:.6px;margin-bottom:12px;font-weight:500;display:flex;align-items:center;gap:6px}

/* RULER */
.ruler-wrap{position:relative;height:36px;margin-bottom:0}
.ruler-track{position:absolute;top:16px;left:0;right:0;height:3px;background:#E8E6E0;border-radius:2px}
.ruler-zone{position:absolute;top:16px;height:3px;border-radius:3px;opacity:.5}
/* Legend table below ruler — siempre una fila, nunca se superpone */
.ruler-legend{display:flex;gap:0;margin-top:8px;border:1px solid #E8E6E0;border-radius:6px;overflow:hidden;background:#fff}
.ruler-leg-item{flex:1;padding:6px 8px;border-right:1px solid #E8E6E0;min-width:0}
.ruler-leg-item:last-child{border-right:none}
.ruler-leg-price{font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ruler-leg-label{font-size:9px;color:#888780;text-transform:uppercase;letter-spacing:.03em;margin-top:1px;display:flex;align-items:center;gap:3px}
.ruler-leg-dot{width:7px;height:7px;border-radius:50%;display:inline-block;flex-shrink:0}

/* STOPS TABLE */
.stops-grid{display:flex;flex-direction:column;gap:6px}
.stop-row{display:grid;grid-template-columns:110px 90px 1fr 90px 130px;align-items:center;gap:10px;padding:9px 12px;background:#FAFAF8;border-radius:6px;border:1px solid #E8E6E0}
.stop-row.activado{background:#FEF2F2;border-color:#FCA5A5}
.stop-row.pendiente{background:#FEFCE8;border-color:#FDE68A}
.stop-row.no-aplica{background:#F5F4F0;border-color:#E8E6E0;opacity:.7}
.stop-row.sin-datos{background:#FFF7ED;border-color:#FED7AA}
.stop-name{font-size:11px;font-weight:600;color:#2C2C2A}
.stop-price{font-size:13px;font-weight:500;color:#2C2C2A}
.stop-bar-bg{height:5px;background:#E8E6E0;border-radius:3px;position:relative}
.stop-bar-fill{height:100%;border-radius:3px;position:absolute;left:0;top:0}
.stop-cur{position:absolute;width:2px;height:11px;top:-3px;border-radius:1px;background:#2C2C2A;opacity:.4}
.stop-dist{font-size:11px;color:#5F5E5A}
.stop-nota{font-size:10px;color:#888780;white-space:normal;line-height:1.4}

/* CAMBIOS */
.chg-card{background:#fff;border:1px solid #E8E6E0;border-radius:8px;padding:12px 16px;margin-bottom:8px}
.chg-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.chg-ticker{font-size:17px;font-weight:600}
.chg-dir-e{font-size:10px;padding:2px 8px;border-radius:4px;background:#FCEBEB;color:#791F1F;border:1px solid #FCA5A5}
.chg-dir-m{font-size:10px;padding:2px 8px;border-radius:4px;background:#E1F5EE;color:#085041;border:1px solid #86EFAC}
.chg-boxes{display:flex;gap:8px}
.chg-box{flex:1;padding:8px 12px;background:#F5F4F0;border-radius:5px;border:1px solid #E8E6E0}
.chg-box-lbl{font-size:9px;color:#888780;text-transform:uppercase;margin-bottom:2px}
.chg-box-txt{font-size:11px;color:#5F5E5A}
.empty{color:#888780;font-size:12px;padding:40px;text-align:center;border:1px solid #E8E6E0;border-radius:8px;background:#fff}

/* ── TOOLTIP SYSTEM (fixed, viewport-aware) ── */
.tip-icon{display:inline-flex;align-items:center;justify-content:center;width:13px;height:13px;border-radius:50%;background:#E0DEDD;color:#6B6B68;font-size:8px;font-weight:700;cursor:help;flex-shrink:0;user-select:none;vertical-align:middle;margin-left:3px}
.tip-icon:hover{background:#C8C6C2}
#tooltip-popup{position:fixed;z-index:99999;background:#1E1E1C;color:#F1EFE8;border-radius:9px;padding:11px 14px;max-width:380px;min-width:240px;box-shadow:0 6px 24px rgba(0,0,0,.3);pointer-events:none;font-size:12px;line-height:1.5;display:none}
#tooltip-popup.vis{display:block}
.tp-title{font-weight:600;font-size:12px;margin-bottom:5px;color:#fff}
.tp-desc{margin-bottom:5px;color:#C8C6C2}
.tp-formula{font-family:'Courier New',monospace;font-size:10.5px;background:#2E2E2C;padding:4px 8px;border-radius:5px;margin-top:4px;color:#7FFFD4;word-break:break-word}
"""

    # ── JavaScript ────────────────────────────────────────────────────────────
    js = r"""
const D = window._DATA;
const EC = {'🟢':'g','🟡':'y','🟠':'o','🔴':'r'};
const EO = {'🔴':0,'🟠':1,'🟡':2,'🟢':3};
let SC = null, SD = 1;
let F = {cat:'all', tipo:'all', alert:'all'};

/* ── Tooltip engine ──────────────────────────────────────────────────── */
const TTP = document.getElementById('tooltip-popup');
let _tipV = false;
function showTip(el, data) {
  document.getElementById('tp-title').textContent = data.titulo || '';
  document.getElementById('tp-desc').textContent = data.desc || '';
  const fEl = document.getElementById('tp-formula');
  if (data.formula) { fEl.textContent = 'Fórmula: ' + data.formula; fEl.style.display = ''; }
  else { fEl.style.display = 'none'; }
  TTP.classList.add('vis'); _tipV = true;
  requestAnimationFrame(() => posTip(el));
}
function posTip(el) {
  if (!_tipV) return;
  const r = el.getBoundingClientRect();
  const tw = TTP.offsetWidth, th = TTP.offsetHeight;
  const vw = window.innerWidth, vh = window.innerHeight;
  let left = r.left + r.width / 2 - tw / 2;
  let top = r.bottom + 8;
  if (left + tw > vw - 8) left = vw - tw - 8;
  if (left < 8) left = 8;
  if (top + th > vh - 8) top = r.top - th - 8;
  if (top < 8) top = 8;
  TTP.style.left = left + 'px'; TTP.style.top = top + 'px';
}
function hideTip() { TTP.classList.remove('vis'); _tipV = false; }
document.addEventListener('scroll', hideTip, true);
window.addEventListener('resize', hideTip);

function makeTip(data) {
  if (!data) return '';
  const s = document.createElement('span');
  s.className = 'tip-icon'; s.textContent = '?';
  s.addEventListener('mouseenter', () => showTip(s, data));
  s.addEventListener('mouseleave', hideTip);
  return s;
}

/* ── Tab navigation ─────────────────────────────────────────────────── */
function switchTab(id) {
  ['estado','detalle','cambios','historial'].forEach((t, i) => {
    document.querySelectorAll('.tab')[i].classList.toggle('active', t === id);
    document.getElementById('t-' + t).classList.toggle('active', t === id);
  });
  if (id === 'detalle') initDetalle();
  if (id === 'cambios') renderCambios();
  if (id === 'historial') renderHistorial();
}

function setF(k, v, b) {
  F[k] = v;
  b.parentElement.querySelectorAll('.fb').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  renderEstado();
}

/* ── FORMAT helpers ─────────────────────────────────────────────────── */
function fmtPrice(v) { return v != null ? '$' + Number(v).toFixed(2) : '<span class="dim">—</span>'; }
function fmtPct(v, decimals) {
  if (v == null) return '<span class="dim">—</span>';
  const d = decimals != null ? decimals : 1;
  const cls = v >= 0 ? 'pos' : 'neg';
  return '<span class="' + cls + '">' + (v >= 0 ? '+' : '') + Number(v).toFixed(d) + '%</span>';
}
function fmtRank(v) { return v != null ? '#' + v : '<span class="dim">—</span>'; }
function fmtBool(v) { return v ? '<span class="ar">SÍ</span>' : '<span class="dim">no</span>'; }

function fmt(col, val) {
  if (val === null || val === undefined) return '<span class="dim">—</span>';
  if (col === 'ganancia_pct') return fmtPct(val);
  if (['precio_actual_usd','ppp_equiv_usd','maximo_desde_entrada_usd',
       'stop_s1_usd','stop_t1_usd','stop_t2_usd'].includes(col)) return fmtPrice(val);
  if (col === 'alerta_emoji') return '<span class="a' + (EC[val] || '') + '">' + val + '</span>';
  if (col === 'rank_efectivo') return fmtRank(val);
  if (typeof val === 'boolean') return fmtBool(val);
  if (col === 'kxsigma' || col === 'sigma_mensual_12m') return Number(val).toFixed(2) + '%';
  if (col === 'delta_momentum') return fmtPct(val * 100);
  return String(val);
}

/* ── ESTADO TABLE ───────────────────────────────────────────────────── */
const COLS = ['ticker','categoria','tipo_ab','tipo_empresa','ganancia_pct','precio_actual_usd',
  'ppp_equiv_usd','maximo_desde_entrada_usd','stop_s1_usd','stop_t1_usd','stop_t2_usd',
  'rank_efectivo','s2_decision','fase_modelo','alerta_emoji','alerta_texto'];
const LBL = {
  ticker:'Ticker', categoria:'Cat', tipo_ab:'Tipo', tipo_empresa:'Empresa',
  ganancia_pct:'Gan%', precio_actual_usd:'Precio', ppp_equiv_usd:'PPP',
  maximo_desde_entrada_usd:'Max', stop_s1_usd:'S1', stop_t1_usd:'T1', stop_t2_usd:'T2',
  rank_efectivo:'Rank', s2_decision:'S2', fase_modelo:'Fase', alerta_emoji:'', alerta_texto:'Alerta'
};

function fd() {
  const q = (document.getElementById('srch') || {value:''}).value.toLowerCase();
  return D.estado.filter(r => {
    if (q && !(r.ticker || '').toLowerCase().includes(q)) return false;
    if (F.cat === 'sat' && !r.categoria?.includes('Satelites')) return false;
    if (F.cat === 'acc' && !r.categoria?.includes('Acciones')) return false;
    if (F.tipo !== 'all' && r.tipo_ab !== F.tipo) return false;
    if (F.alert !== 'all' && r.alerta_emoji !== F.alert) return false;
    return true;
  });
}

let _thCreated = false;
function renderEstado() {
  const tips = D.tooltips;
  if (!_thCreated) {
    const thRow = document.getElementById('eh');
    thRow.innerHTML = '<tr>' + COLS.map((c, i) => {
      const tipData = tips[c];
      let tipHtml = '';
      // Build tooltip icon inline after header text (not as DOM node here)
      if (tipData) tipHtml = '<span class="tip-icon" data-tip="' + c + '">?</span>';
      return '<th onclick="sortBy(\'' + c + '\')" id="th-' + c + '">' + LBL[c] + tipHtml + '</th>';
    }).join('') + '</tr>';
    // Attach tooltip listeners to tip icons in header
    document.querySelectorAll('#eh .tip-icon').forEach(el => {
      const key = el.dataset.tip;
      const data = tips[key];
      if (data) {
        el.addEventListener('mouseenter', () => showTip(el, data));
        el.addEventListener('mouseleave', hideTip);
      }
    });
    _thCreated = true;
  }

  let rows = fd();
  if (SC) rows.sort((a, b) => { const av = a[SC] ?? '', bv = b[SC] ?? ''; return av < bv ? -SD : av > bv ? SD : 0; });
  else rows.sort((a, b) => (EO[a.alerta_emoji] ?? 9) - (EO[b.alerta_emoji] ?? 9));

  document.getElementById('eb').innerHTML = rows.map(r =>
    '<tr class="r' + (EC[r.alerta_emoji] || '') + '" onclick="switchTab(\'detalle\');setTimeout(()=>showT(\'' + r.ticker + '\'),50)">' +
    COLS.map(c => '<td' + (c === 'ticker' ? ' class="ticker-cell"' : '') + '>' + fmt(c, r[c]) + '</td>').join('') +
    '</tr>'
  ).join('');
}

function sortBy(c) {
  document.querySelectorAll('#eh th').forEach(th => th.classList.remove('asc','desc'));
  if (SC === c) SD *= -1; else { SC = c; SD = 1; }
  const thEl = document.getElementById('th-' + c);
  if (thEl) thEl.classList.add(SD === 1 ? 'asc' : 'desc');
  renderEstado();
}

/* ── DETALLE ────────────────────────────────────────────────────────── */
function initDetalle() {
  const sorted = [...D.estado].sort((a, b) => (EO[a.alerta_emoji] ?? 9) - (EO[b.alerta_emoji] ?? 9));
  document.getElementById('dlist').innerHTML = sorted.map(r =>
    '<button class="tbtn" onclick="showT(\'' + r.ticker + '\')" id="dbtn-' + r.ticker + '">' +
    '<span>' + r.ticker + '</span>' +
    '<div class="dot d' + (EC[r.alerta_emoji] || 'g') + (EC[r.alerta_emoji] === 'r' ? '_' : '') + '"></div>' +
    '</button>'
  ).join('');
  if (sorted.length) showT(sorted[0].ticker);
}

function ruler(r) {
  const vals = [r.ppp_equiv_usd, r.precio_actual_usd, r.maximo_desde_entrada_usd,
                r.stop_s1_usd, r.stop_t1_usd, r.stop_t2_usd, r.t3_precio_objetivo].filter(v => v != null && v > 0);
  if (!vals.length) return '<div class="dim" style="padding:16px 0;text-align:center">Sin datos de precio</div>';

  const mn = Math.min(...vals) * 0.93, mx = Math.max(...vals) * 1.05, rng = mx - mn;
  const pct = v => ((v - mn) / rng * 100).toFixed(2);

  // Precio objetivo T3 — viene calculado desde reglas_tacticos.py
  const precioT3 = r.t3_precio_objetivo || null;

  // Definir marcadores ordenados de menor a mayor valor
  const raw = [];
  if (r.stop_t1_usd) raw.push({ v: r.stop_t1_usd, color: '#DC2626', label: r.t1_activo ? 'Stop T1' : 'Stop T1 (ref)', big: false });
  if (r.stop_t2_usd && r.t2_activo) raw.push({ v: r.stop_t2_usd, color: '#B91C1C', label: 'Stop T2', big: false });
  if (r.stop_s1_usd) raw.push({ v: r.stop_s1_usd, color: '#EA580C', label: 'Stop S1', big: false });
  if (r.ppp_equiv_usd) raw.push({ v: r.ppp_equiv_usd, color: '#7C3AED', label: 'PPP compra', big: false });
  raw.push({ v: r.precio_actual_usd, color: '#1D4ED8', label: 'Precio actual', big: true });
  if (r.maximo_desde_entrada_usd) raw.push({ v: r.maximo_desde_entrada_usd, color: '#059669', label: 'Máximo', big: false });
  if (precioT3) raw.push({ v: precioT3, color: '#9333EA', label: 'Objetivo T3 (' + r.tir_objetivo + '%)', big: false });
  const markers = raw.filter(m => m.v != null && m.v > 0).sort((a, b) => a.v - b.v);

  const gan = r.ganancia_pct || 0;
  const zoneL = Math.min(+pct(r.ppp_equiv_usd || 0), +pct(r.precio_actual_usd || 0));
  const zoneW = Math.abs(+pct(r.ppp_equiv_usd || 0) - +pct(r.precio_actual_usd || 0));

  // ── Línea del ruler: solo puntos, sin texto encima/debajo ──────────────
  let html = '<div class="ruler-wrap"><div class="ruler-track"></div>';
  html += '<div class="ruler-zone" style="left:' + zoneL.toFixed(2) + '%;width:' + zoneW.toFixed(2) + '%;background:' + (gan >= 0 ? '#059669' : '#DC2626') + '"></div>';

  // track está a top:16px y tiene height:3px → centro de la línea = 17.5px
  // centramos cada dot sobre ese punto: top = 17.5 - size/2
  markers.forEach(m => {
    const p      = pct(m.v);
    const size   = m.big ? 16 : 9;
    const top    = Math.round(17.5 - size / 2);
    const border = m.big ? '3px solid #fff' : '2px solid #fff';
    const shadow = m.big ? ';box-shadow:0 0 0 2px ' + m.color + '55' : '';
    html += '<div style="position:absolute;left:' + p + '%;top:' + top + 'px;' +
            'width:' + size + 'px;height:' + size + 'px;border-radius:50%;' +
            'background:' + m.color + ';border:' + border + ';transform:translateX(-50%)' + shadow + '"></div>';
  });
  html += '</div>';

  // ── Leyenda debajo: tabla con una celda por marcador, nunca se superpone ──
  // Ordenar en tabla de izquierda a derecha (mismo orden que en el ruler)
  html += '<div class="ruler-legend">';
  markers.forEach(m => {
    const priceStr = '$' + Number(m.v).toFixed(2);
    const priceCls = m.big ? 'font-weight:700;color:' + m.color : 'color:' + m.color;
    html += '<div class="ruler-leg-item">' +
              '<div class="ruler-leg-price" style="' + priceCls + '">' + priceStr + '</div>' +
              '<div class="ruler-leg-label"><span class="ruler-leg-dot" style="background:' + m.color + '"></span>' + m.label + '</div>' +
            '</div>';
  });
  html += '</div>';
  return html;
}

function stopStatusBadge(estado) {
  const map = {
    'activado':    ['sb-activado',    '⚡ ACTIVADO'],
    'vigente':     ['sb-vigente',     '✓ Vigente'],
    'pendiente':   ['sb-pendiente',   '⏳ Pendiente ganancia'],
    'reemplazado': ['sb-reemplazado', '→ Reemplazado por T2'],
    'no_aplica':   ['sb-no-aplica',   '— No aplica (Tipo A)'],
    'sin_datos':   ['sb-sin-datos',   '⚠ Sin datos'],
    'inhibida':    ['sb-inhibida',    '⏱ Inhibida < 90 días'],
    'sin_objetivo':['sb-sin-objetivo','— Sin TIR objetivo'],
    'proximo':     ['sb-proximo',     '🔔 Próxima'],
    'ok':          ['sb-ok',          '✓ OK'],
    'activado_t3': ['sb-activado',    '⚡ Alcanzada'],
  };
  const [cls, label] = map[estado] || ['sb-no-aplica', '—'];
  return '<span class="stop-badge ' + cls + '">' + label + '</span>';
}

function stopRows(r) {
  const pr = r.precio_actual_usd, mx = r.maximo_desde_entrada_usd;
  const sat = r.categoria?.includes('Satelites');
  const allVals = [pr, mx, r.ppp_equiv_usd, r.stop_s1_usd, r.stop_t1_usd, r.stop_t2_usd, r.t3_precio_objetivo].filter(v => v != null && v > 0);
  if (!allVals.length) return '<div class="empty" style="padding:16px">Sin datos de precio disponibles</div>';
  const maxV = Math.max(...allVals);
  const curW = pr ? (pr / maxV * 100) : 0;
  const tips = D.tooltips;

  const rows = [];

  if (sat) {
    // ── Satélites: mostrar S1 siempre ──
    const s1 = r.stop_s1_usd;
    const activado = r.s1_activado;
    const rowCls = activado ? 'activado' : (s1 == null ? 'sin-datos' : '');
    const dist = (pr && s1) ? ((pr - s1) / pr * 100) : null;
    const distStr = dist != null ? (activado ? '<span class="neg">ACTIVADO</span>' : ('+' + dist.toFixed(1) + '% margen')) : '—';
    const fw = s1 ? (s1 / maxV * 100).toFixed(1) : 0;
    const kxStr = r.kxsigma != null ? ' (k×σ = ' + r.kxsigma + '%)' : '';
    const nota = s1 ? 'Stop = Máximo × (1 − k×σ)' + kxStr + '. Máx desde entrada: $' + (mx ? Number(mx).toFixed(2) : '—') : 'Sin datos suficientes para calcular S1 (falta grupo, PPP, σ o máximo).';

    rows.push(
      '<div class="stop-row ' + rowCls + '">' +
      '<div class="stop-name">Stop S1 — Trailing<span class="tip-icon" data-stopkey="stop_s1_usd">?</span></div>' +
      '<div class="stop-price">' + (s1 ? '$' + Number(s1).toFixed(2) : '<span class="dim">—</span>') + '</div>' +
      '<div class="stop-bar-bg">' +
        (s1 ? '<div class="stop-bar-fill" style="width:' + fw + '%;background:#EA580C;opacity:.5"></div>' : '') +
        '<div class="stop-cur" style="left:' + curW + '%"></div>' +
      '</div>' +
      '<div class="stop-dist">' + distStr + '</div>' +
      '<div class="stop-nota">' + nota + '</div>' +
      '</div>'
    );
  } else {
    // ── Acciones: mostrar T1, T2, T3 siempre ──
    const stops = computeStops(r);

    // T1
    const t1 = stops.t1;
    const t1rCls = t1.estado === 'activado' ? 'activado' : t1.estado === 'pendiente' ? '' :
                   (t1.estado === 'no_aplica' || t1.estado === 'reemplazado') ? 'no-aplica' :
                   t1.estado === 'sin_datos' ? 'sin-datos' : '';
    const t1Dist = (pr && t1.precio) ? ((pr - t1.precio) / pr * 100) : null;
    const t1DistStr = t1.estado === 'activado' ? '<span class="neg">ACTIVADO</span>' :
                      t1Dist != null ? ('+' + t1Dist.toFixed(1) + '% margen') : '—';
    const t1fw = t1.precio ? (t1.precio / maxV * 100).toFixed(1) : 0;
    rows.push(
      '<div class="stop-row ' + t1rCls + '">' +
      '<div class="stop-name">Stop T1 — Fijo<span class="tip-icon" data-stopkey="stop_t1_usd">?</span></div>' +
      '<div class="stop-price">' + (t1.precio ? '$' + Number(t1.precio).toFixed(2) : '<span class="dim">—</span>') + '</div>' +
      '<div class="stop-bar-bg">' +
        (t1.precio ? '<div class="stop-bar-fill" style="width:' + t1fw + '%;background:#DC2626;opacity:.4"></div>' : '') +
        '<div class="stop-cur" style="left:' + curW + '%"></div>' +
      '</div>' +
      '<div class="stop-dist">' + (t1.precio ? t1DistStr : stopStatusBadge(t1.estado)) + '</div>' +
      '<div class="stop-nota">' + t1.nota + '</div>' +
      '</div>'
    );

    // T2
    const t2 = stops.t2;
    const t2rCls = t2.estado === 'activado' ? 'activado' : t2.estado === 'pendiente' ? 'pendiente' :
                   t2.estado === 'sin_datos' ? 'sin-datos' : '';
    const t2Dist = (pr && t2.precio) ? ((pr - t2.precio) / pr * 100) : null;
    const t2DistStr = t2.estado === 'activado' ? '<span class="neg">ACTIVADO</span>' :
                      t2Dist != null ? ('+' + t2Dist.toFixed(1) + '% margen') : '—';
    const t2fw = t2.precio ? (t2.precio / maxV * 100).toFixed(1) : 0;
    const t2yStr = t2.y_pct ? ' (Y=' + (t2.y_pct * 100).toFixed(1) + '% desde máx)' : '';
    rows.push(
      '<div class="stop-row ' + t2rCls + '">' +
      '<div class="stop-name">Stop T2 — Trailing<span class="tip-icon" data-stopkey="stop_t2_usd">?</span></div>' +
      '<div class="stop-price">' + (t2.precio ? '$' + Number(t2.precio).toFixed(2) : '<span class="dim">—</span>') + '</div>' +
      '<div class="stop-bar-bg">' +
        (t2.precio ? '<div class="stop-bar-fill" style="width:' + t2fw + '%;background:#DC2626;opacity:.4"></div>' : '') +
        '<div class="stop-cur" style="left:' + curW + '%"></div>' +
      '</div>' +
      '<div class="stop-dist">' + (t2.precio ? t2DistStr + t2yStr : stopStatusBadge(t2.estado)) + '</div>' +
      '<div class="stop-nota">' + t2.nota + '</div>' +
      '</div>'
    );

    // T3
    const t3 = stops.t3;
    const t3rCls = t3.estado === 'activado' ? 'activado' : t3.estado === 'proximo' ? 'pendiente' : 'no-aplica';

    // Precio objetivo T3 — viene calculado desde reglas_tacticos.py
    let precioT3 = r.t3_precio_objetivo || null;
    const t3PriceStr = precioT3 ? '$' + precioT3.toFixed(2) : '<span class="dim">—</span>';
    const t3fw = (precioT3 && maxV) ? (precioT3 / maxV * 100).toFixed(1) : 0;
    const t3Dist = (pr && precioT3) ? ((precioT3 - pr) / pr * 100) : null;
    const t3DistStr = t3Dist != null
      ? (t3Dist >= 0 ? '+' : '') + t3Dist.toFixed(1) + '% hasta obj. · TIR ' + r.tir_objetivo + '%'
      : (r.tir_objetivo ? 'TIR obj: ' + r.tir_objetivo + '%' : '');
    const t3barColor = t3.estado === 'activado' ? '#DC2626' : '#9333EA';

    rows.push(
      '<div class="stop-row ' + t3rCls + '">' +
      '<div class="stop-name">T3 — Objetivo %<span class="tip-icon" data-stopkey="t3_estado">?</span></div>' +
      '<div class="stop-price">' + t3PriceStr + '</div>' +
      '<div class="stop-bar-bg">' +
        (precioT3 ? '<div class="stop-bar-fill" style="width:' + t3fw + '%;background:' + t3barColor + ';opacity:.4"></div>' : '') +
        '<div class="stop-cur" style="left:' + curW + '%"></div>' +
      '</div>' +
      '<div class="stop-dist">' + (t3DistStr || stopStatusBadge(t3.estado)) + '</div>' +
      '<div class="stop-nota">' + (t3.texto || 'No configurada para este ticker.') + '</div>' +
      '</div>'
    );
  }

  // Render and attach tooltip listeners
  const container = document.createElement('div');
  container.className = 'stops-grid';
  container.innerHTML = rows.join('');
  container.querySelectorAll('.tip-icon[data-stopkey]').forEach(el => {
    const key = el.dataset.stopkey;
    const tipData = D.tooltips[key];
    if (tipData) {
      el.addEventListener('mouseenter', () => showTip(el, tipData));
      el.addEventListener('mouseleave', hideTip);
    }
  });
  return container;
}

function computeStops(r) {
  const es_tipo_a = String(r.tipo_ab || 'B').toUpperCase() === 'A';
  const gan = r.ganancia_pct; // % (e.g. 25.3)

  // T1
  let t1 = { precio: r.stop_t1_usd, y_pct: null, estado: '', nota: '' };
  if (es_tipo_a) {
    t1.estado = 'no_aplica';
    t1.nota = 'Tipo A — la caída de precio es oportunidad de acumular, no señal de salida. T1 no aplica.';
  } else if (r.stop_t1_usd == null) {
    t1.estado = 'sin_datos';
    t1.nota = '⚠ Sin datos suficientes para calcular T1. Verificar que el PPP y tipo de empresa estén cargados.';
  } else if (r.t1_activado) {
    t1.estado = 'activado';
    t1.nota = 'Stop T1 ACTIVADO — el precio cayó por debajo del nivel de stop fijo. Evaluar salida total.';
  } else if (r.t1_activo) {
    t1.estado = 'vigente';
    t1.nota = 'Stop fijo activo. Se reemplazará por T2 cuando la ganancia sobre PPP supere el +10%.';
  } else {
    t1.estado = 'reemplazado';
    t1.nota = 'Reemplazado por T2 (ganancia ≥ +10%). T2 es permanente hasta la salida.';
  }

  // T2
  let t2 = { precio: r.stop_t2_usd, y_pct: r.y_pct, estado: '', nota: '' };
  if (r.t2_activado) {
    t2.estado = 'activado';
    t2.nota = 'Trailing stop T2 ACTIVADO — precio cayó por debajo del nivel. Evaluar salida total.';
  } else if (r.t2_activo && r.stop_t2_usd != null) {
    t2.estado = 'vigente';
    const yStr = r.y_pct ? (r.y_pct * 100).toFixed(1) + '%' : '?';
    t2.nota = 'Trailing activo. Holgura: ' + yStr + ' desde el máximo histórico. El stop sube con el precio, nunca retrocede.';
  } else if (r.stop_t2_usd == null && gan != null && gan < 10) {
    t2.estado = 'pendiente';
    t2.nota = '⏳ T2 se activa cuando la ganancia sobre PPP supere el +10% (actual: ' + (gan >= 0 ? '+' : '') + Number(gan).toFixed(1) + '%). Completar la ganancia faltante para activarlo.';
  } else if (r.stop_t2_usd == null) {
    t2.estado = 'sin_datos';
    t2.nota = '⚠ Sin datos suficientes para calcular T2. Verificar precio máximo y PPP.';
  } else {
    t2.estado = 'sin_datos';
    t2.nota = '⚠ Sin datos suficientes.';
  }

  // T3
  const t3txt = r.t3_estado || '';
  let t3estado = 'sin_objetivo';
  if (t3txt.toUpperCase().includes('ALCANZADA')) t3estado = 'activado';
  else if (t3txt.toUpperCase().includes('PRÓXIMA') || t3txt.toUpperCase().includes('PROXIMA')) t3estado = 'proximo';
  else if (t3txt.toUpperCase().includes('INHIBIDA') || t3txt.toUpperCase().includes('DÍAS')) t3estado = 'inhibida';
  else if (t3txt.toUpperCase().includes('SIN TIR') || t3txt.toUpperCase().includes('NO DISPONIBLE')) t3estado = 'sin_objetivo';
  else if (t3txt) t3estado = 'ok';

  return { t1, t2, t3: { estado: t3estado, texto: t3txt } };
}

function showT(ticker) {
  document.querySelectorAll('.tbtn').forEach(b => b.classList.toggle('on', b.id === 'dbtn-' + ticker));
  const r = D.estado.find(x => x.ticker === ticker);
  if (!r) return;
  const ec = EC[r.alerta_emoji] || 'g';
  const sat = r.categoria?.includes('Satelites');
  const gan = r.ganancia_pct;
  const ganStr = gan != null ? ((gan >= 0 ? '+' : '') + Number(gan).toFixed(1) + '%') : '—';
  const ganCls = gan != null && gan >= 0 ? 'pos' : 'neg';
  const tips = D.tooltips;

  function mkCard(label, val, cls, tipKey) {
    const tip = tipKey ? makeTip(tips[tipKey]) : '';
    const el = document.createElement('div');
    el.className = 'mc';
    const lDiv = document.createElement('div');
    lDiv.className = 'mc-label';
    lDiv.innerHTML = label;
    if (tip) lDiv.appendChild(tip);
    const vDiv = document.createElement('div');
    vDiv.className = 'mc-val' + (cls ? ' ' + cls : '');
    vDiv.innerHTML = val;
    el.appendChild(lDiv); el.appendChild(vDiv);
    return el;
  }

  const hdr = document.createElement('div');
  hdr.className = 'det-hdr';
  hdr.innerHTML =
    '<span class="det-ticker">' + ticker + '</span>' +
    '<span class="tag">' + (r.categoria || '') + '</span>' +
    (r.tipo_ab ? '<span class="tag">Tipo ' + r.tipo_ab + '</span>' : '') +
    (r.tipo_empresa ? '<span class="tag">' + r.tipo_empresa + '</span>' : '') +
    '<span class="alert-pill ap-' + ec + '">' + (r.alerta_emoji || '') + ' ' + (r.alerta_texto || '') + '</span>';

  const cards = document.createElement('div');
  cards.className = 'mcards';
  cards.appendChild(mkCard('Ganancia PP', '<span class="' + ganCls + '">' + ganStr + '</span>', '', 'ganancia_pct'));
  cards.appendChild(mkCard('Precio actual', r.precio_actual_usd ? '$' + Number(r.precio_actual_usd).toFixed(2) : '—', '', 'precio_actual_usd'));
  cards.appendChild(mkCard('PPP equiv', r.ppp_equiv_usd ? '$' + Number(r.ppp_equiv_usd).toFixed(2) : '—', '', 'ppp_equiv_usd'));
  cards.appendChild(mkCard('Máx desde entrada', r.maximo_desde_entrada_usd ? '$' + Number(r.maximo_desde_entrada_usd).toFixed(2) : '—', '', 'maximo_desde_entrada_usd'));
  cards.appendChild(mkCard('σ mensual 12m', r.sigma_mensual_12m ? Number(r.sigma_mensual_12m).toFixed(2) + '%' : '—', '', 'sigma_mensual_12m'));
  cards.appendChild(mkCard('Desde', r.fecha_primera_compra || '—', 'sm', 'fecha_primera_compra'));

  if (sat) {
    cards.appendChild(mkCard('Rank bruto', r.rank_bruto ? '#' + r.rank_bruto : '—', '', 'rank_bruto'));
    cards.appendChild(mkCard('Rank efectivo', r.rank_efectivo ? '#' + r.rank_efectivo : '—', '', 'rank_efectivo'));
    const dCls = r.delta_momentum > 0.2 ? 'neg' : '';
    cards.appendChild(mkCard('Δ Momentum', r.delta_momentum != null ? '<span class="' + dCls + '">' + (r.delta_momentum * 100).toFixed(1) + '%</span>' : '—', '', 'delta_momentum'));
    cards.appendChild(mkCard('Score ETF', r.score_etf != null ? (r.score_etf * 100).toFixed(1) + '%' : '—', ''));
  } else {
    cards.appendChild(mkCard('Fase modelo', r.fase_modelo ? '<span class="badge fase-' + r.fase_modelo + '">' + r.fase_modelo + '</span>' : '—', 'sm', 'fase_modelo'));
    cards.appendChild(mkCard('Acción modelo', r.accion_modelo || '—', 'sm', 'accion_modelo'));
    cards.appendChild(mkCard('Tamaño pos.', r.tamano_posicion_pct != null ? r.tamano_posicion_pct + '%' : '—', '', 'tamano_posicion_pct'));
    const flagCls = r.flag_revision ? 'neg' : '';
    cards.appendChild(mkCard('Flag revisión', '<span class="' + flagCls + '">' + (r.flag_revision ? 'SÍ ⚠' : 'No') + '</span>', '', 'flag_revision'));
    if (r.tir_objetivo != null) {
      cards.appendChild(mkCard('Objetivo rentab.', r.tir_objetivo + '% sobre PPP', 'sm', 'tir_objetivo'));
    }
  }

  // Ruler panel
  const rulerPanel = document.createElement('div');
  rulerPanel.className = 'panel';
  const pt1 = document.createElement('div');
  pt1.className = 'panel-title';
  pt1.textContent = 'Niveles de precio — referencia visual';
  rulerPanel.appendChild(pt1);
  rulerPanel.innerHTML += ruler(r);

  // Stops panel
  const stopsPanel = document.createElement('div');
  stopsPanel.className = 'panel';
  const pt2 = document.createElement('div');
  pt2.className = 'panel-title';
  if (sat) {
    pt2.innerHTML = 'Stops activos — Satélites (S1 trailing · S2 rotación · S3 parking) ';
  } else {
    pt2.innerHTML = 'Stops tácticos — <span style="font-style:normal">T1 fijo · T2 trailing · T3 objetivo %</span> ';
  }
  const tipPanelKey = sat ? 'stop_s1_usd' : 'stop_t1_usd';
  pt2.appendChild(makeTip(tips[tipPanelKey]));
  stopsPanel.appendChild(pt2);
  stopsPanel.appendChild(stopRows(r));

  // Sat extra info
  let satExtra = null;
  if (sat) {
    satExtra = document.createElement('div');
    satExtra.className = 'panel';
    satExtra.innerHTML = '<div class="panel-title">Decisión de rotación (S2 / S3)</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
      '<div style="flex:1;min-width:160px;padding:10px;background:#F5F4F0;border-radius:6px;border:1px solid #E8E6E0">' +
        '<div style="font-size:9px;color:#888780;text-transform:uppercase;margin-bottom:4px">DECISIÓN S2</div>' +
        '<div style="font-size:12px">' + (r.s2_decision || '—') + '</div>' +
      '</div>' +
      '<div style="flex:1;min-width:160px;padding:10px;background:#F5F4F0;border-radius:6px;border:1px solid #E8E6E0">' +
        '<div style="font-size:9px;color:#888780;text-transform:uppercase;margin-bottom:4px">S3 — PARKING</div>' +
        '<div style="font-size:12px" class="' + (r.s3_activado ? 'neg' : 'pos') + '">' + (r.s3_activado ? 'ACTIVADO — Salir a parking' : 'No activado') + '</div>' +
      '</div>' +
      '<div style="flex:1;min-width:160px;padding:10px;background:#F5F4F0;border-radius:6px;border:1px solid #E8E6E0">' +
        '<div style="font-size:9px;color:#888780;text-transform:uppercase;margin-bottom:4px">k×σ (distancia stop S1)</div>' +
        '<div style="font-size:12px">' + (r.kxsigma != null ? r.kxsigma + '%' : '—') + '</div>' +
      '</div>' +
      '</div>';
  }

  const main = document.getElementById('dmain');
  main.innerHTML = '';
  main.appendChild(hdr);
  main.appendChild(cards);
  main.appendChild(rulerPanel);
  main.appendChild(stopsPanel);
  if (satExtra) main.appendChild(satExtra);
}

/* ── CAMBIOS ────────────────────────────────────────────────────────── */
function renderCambios() {
  const w = document.getElementById('clist');
  if (!D.cambios || !D.cambios.length) {
    w.innerHTML = '<div class="empty">Sin cambios registrados aún.</div>'; return;
  }
  const sorted = [...D.cambios].sort((a, b) =>
    (b.fecha_cambio || '').toString().localeCompare((a.fecha_cambio || '').toString()));
  w.innerHTML = sorted.map(c => {
    const ec = EC[c.alerta_nueva] || 'g';
    const dir = c.direccion === 'EMPEORÓ' ? 'chg-dir-e' : 'chg-dir-m';
    return '<div class="chg-card">' +
      '<div class="chg-head">' +
        '<div style="display:flex;align-items:center;gap:10px">' +
          '<span class="chg-ticker">' + c.ticker + '</span>' +
          '<span class="' + dir + '">' + (c.direccion || '') + '</span>' +
          '<span style="font-size:12px;color:#5F5E5A">' + (c.alerta_anterior || '') + ' → <span class="a' + ec + '">' + (c.alerta_nueva || '') + '</span></span>' +
        '</div>' +
        '<span style="font-size:10px;color:#888780">' + (c.fecha_cambio || '').toString().slice(0, 16) + '</span>' +
      '</div>' +
      '<div class="chg-boxes">' +
        '<div class="chg-box"><div class="chg-box-lbl">Antes</div><div class="chg-box-txt">' + (c.texto_anterior || '—') + '</div></div>' +
        '<div class="chg-box" style="border-color:' + (ec === 'r' ? '#FCA5A5' : ec === 'o' ? '#FDBA74' : '#E8E6E0') + '"><div class="chg-box-lbl">Ahora</div><div class="chg-box-txt a' + ec + '">' + (c.texto_nuevo || '—') + '</div></div>' +
      '</div>' +
    '</div>';
  }).join('');
}

/* ── HISTORIAL ──────────────────────────────────────────────────────── */
function renderHistorial() {
  const q = (document.getElementById('hs') || {value:''}).value.toLowerCase();
  const rows = D.historial.filter(r => !q || (r.ticker || '').toLowerCase().includes(q));
  document.getElementById('hc').textContent = rows.length + ' registros';
  const cols = ['fecha_run','ticker','categoria','alerta_emoji','alerta_texto','ganancia_pct','precio_actual_usd','fase_modelo','s2_decision'];
  const labs = {fecha_run:'Fecha',ticker:'Ticker',categoria:'Cat',alerta_emoji:'',alerta_texto:'Alerta',ganancia_pct:'Gan%',precio_actual_usd:'Precio',fase_modelo:'Fase',s2_decision:'S2'};
  document.getElementById('hh').innerHTML = '<tr>' + cols.map(c => '<th>' + labs[c] + '</th>').join('') + '</tr>';
  const sorted = [...rows].sort((a, b) => (b.fecha_run || '').toString().localeCompare((a.fecha_run || '').toString()));
  document.getElementById('hb').innerHTML = sorted.slice(0, 300).map(r =>
    '<tr class="r' + (EC[r.alerta_emoji] || '') + '">' + cols.map(c => '<td>' + fmt(c, r[c]) + '</td>').join('') + '</tr>'
  ).join('');
}

/* ── INIT ───────────────────────────────────────────────────────────── */
renderEstado();
"""

    # ── HTML body ────────────────────────────────────────────────────────────
    body = (
        '<div id="tooltip-popup">'
        '<div class="tp-title" id="tp-title"></div>'
        '<div class="tp-desc" id="tp-desc"></div>'
        '<div class="tp-formula" id="tp-formula" style="display:none"></div>'
        '</div>'

        '<header>'
        '<h1>Monitor de Salidas — Satélites y Tácticos</h1>'
        '<span>Actualizado: ' + fecha + '</span>'
        '</header>'

        '<div class="tabs">'
        '<div class="tab active" onclick="switchTab(\'estado\')">Estado actual</div>'
        '<div class="tab" onclick="switchTab(\'detalle\')">Detalle por ticker</div>'
        '<div class="tab" onclick="switchTab(\'cambios\')">Cambios</div>'
        '<div class="tab" onclick="switchTab(\'historial\')">Historial</div>'
        '</div>'

        # ─ Estado ─────────────────────────────────────────────────────────
        '<div id="t-estado" class="view active">'
        '<div class="filters-bar">'
        '<span class="fl">Buscar:</span>'
        '<input class="fi" id="srch" placeholder="ticker..." oninput="renderEstado()" style="width:120px">'
        '<span class="fl">Cat:</span>'
        '<button class="fb on" onclick="setF(\'cat\',\'all\',this)">Todos</button>'
        '<button class="fb" onclick="setF(\'cat\',\'sat\',this)">Satélites</button>'
        '<button class="fb" onclick="setF(\'cat\',\'acc\',this)">Acciones</button>'
        '<span class="fl">Tipo:</span>'
        '<button class="fb on" onclick="setF(\'tipo\',\'all\',this)">A+B</button>'
        '<button class="fb" onclick="setF(\'tipo\',\'A\',this)">Tipo A</button>'
        '<button class="fb" onclick="setF(\'tipo\',\'B\',this)">Tipo B</button>'
        '<span class="fl">Alerta:</span>'
        '<button class="fb on" onclick="setF(\'alert\',\'all\',this)">Todas</button>'
        '<button class="fb ar" onclick="setF(\'alert\',\'🔴\',this)">🔴 Acción ya</button>'
        '<button class="fb ao" onclick="setF(\'alert\',\'🟠\',this)">🟠 Acción próxima</button>'
        '<button class="fb ay" onclick="setF(\'alert\',\'🟡\',this)">🟡 Vigilar</button>'
        '<button class="fb ag" onclick="setF(\'alert\',\'🟢\',this)">🟢 Mantener</button>'
        '</div>'
        '<div class="tw">'
        '<table><thead id="eh"></thead><tbody id="eb"></tbody></table>'
        '</div>'
        '</div>'

        # ─ Detalle ────────────────────────────────────────────────────────
        '<div id="t-detalle" class="view" style="padding:0">'
        '<div class="det-wrap">'
        '<div class="det-sidebar" id="dlist"></div>'
        '<div class="det-main" id="dmain"><div class="empty">Seleccioná un ticker de la lista</div></div>'
        '</div>'
        '</div>'

        # ─ Cambios ────────────────────────────────────────────────────────
        '<div id="t-cambios" class="view"><div id="clist"></div></div>'

        # ─ Historial ──────────────────────────────────────────────────────
        '<div id="t-historial" class="view">'
        '<div class="filters-bar">'
        '<span class="fl">Ticker:</span>'
        '<input class="fi" id="hs" placeholder="filtrar..." oninput="renderHistorial()" style="width:120px">'
        '</div>'
        '<div id="hc" style="font-size:11px;color:#888780;margin-bottom:10px"></div>'
        '<div class="tw"><table><thead id="hh"></thead><tbody id="hb"></tbody></table></div>'
        '</div>'
    )

    return (
        '<!DOCTYPE html>\n'
        '<html lang="es">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>Monitor de Salidas</title>\n'
        '<style>' + css + '</style>\n'
        '<script>window._DATA=' + data_json + ';</script>\n'
        '</head>\n'
        '<body>\n'
        + body +
        '\n<script>' + js + '</script>\n'
        '</body>\n'
        '</html>\n'
    )
