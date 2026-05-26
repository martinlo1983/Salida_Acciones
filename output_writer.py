"""
output_writer.py
----------------
Genera el archivo SALIDAS_MONITOR.xlsx con dos hojas:
  - ESTADO_ACTUAL : snapshot completo de la corrida más reciente
  - HISTORIAL     : log acumulativo de cada corrida (una fila por posición por fecha)
"""

import io
import logging
from datetime import datetime

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

# Colores por alerta
COLOR_VERDE   = "C6EFCE"
COLOR_AMARILLO= "FFEB9C"
COLOR_NARANJA = "FFCC99"
COLOR_ROJO    = "FFC7CE"
COLOR_HEADER  = "2F4F8F"

EMOJI_COLOR = {
    "🟢": COLOR_VERDE,
    "🟡": COLOR_AMARILLO,
    "🟠": COLOR_NARANJA,
    "🔴": COLOR_ROJO,
}


def _apply_color(ws, row: int, col_start: int, col_end: int, hex_color: str):
    fill = PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")
    for col in range(col_start, col_end + 1):
        ws.cell(row=row, column=col).fill = fill


def _style_header(ws, n_cols: int):
    header_fill = PatternFill(start_color=COLOR_HEADER, end_color=COLOR_HEADER, fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for col in range(1, n_cols + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", wrap_text=True)


def _autofit(ws):
    for col in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=10)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 2, 50)


# ─── Columnas del output ──────────────────────────────────────────────────────

COLS_ESTADO = [
    "fecha_run", "ticker", "categoria", "tipo_empresa",
    "cantidad", "precio_compra_usd", "fecha_primera_compra",
    "precio_actual_usd", "maximo_desde_entrada_usd",
    "ganancia_pct", "sigma_mensual_12m",
    # Satélites
    "grupo_satelite", "rank_bruto", "rank_efectivo",
    "score_etf", "score_top5", "delta_momentum",
    "stop_s1_usd", "kxsigma",
    "s1_activado", "s2_decision", "s3_activado",
    # Tácticos
    "stop_t1_usd", "t1_activo", "t1_activado",
    "stop_t2_usd", "t2_activo", "t2_activado", "y_pct",
    "fase_modelo", "accion_modelo", "flag_revision", "tamano_posicion_pct",
    "t3_estado",
    # Alerta final
    "alerta_emoji", "alerta_texto",
]


def construir_fila(run_ts: datetime, datos: dict) -> dict:
    """
    Construye una fila normalizada para el Excel a partir del dict de resultados
    de una posición.
    """
    row = {"fecha_run": run_ts}
    for col in COLS_ESTADO[1:]:
        row[col] = datos.get(col)
    return row


def generar_excel(
    filas: list[dict],
    bytes_existente: bytes | None = None,
) -> bytes:
    """
    Genera o actualiza el SALIDAS_MONITOR.xlsx.

    - ESTADO_ACTUAL: siempre se sobreescribe con la corrida actual.
    - HISTORIAL: se appendea. Si el archivo no existía, se crea desde cero.

    Retorna los bytes del archivo resultante.
    """
    run_ts = datetime.now()
    df_actual = pd.DataFrame([construir_fila(run_ts, f) for f in filas])
    df_actual = df_actual.reindex(columns=COLS_ESTADO)

    # ── Cargar historial previo si existe ──────────────────────────────────
    if bytes_existente:
        try:
            df_hist = pd.read_excel(
                io.BytesIO(bytes_existente), sheet_name="HISTORIAL"
            )
        except Exception:
            df_hist = pd.DataFrame(columns=COLS_ESTADO)
    else:
        df_hist = pd.DataFrame(columns=COLS_ESTADO)

    df_hist = pd.concat([df_hist, df_actual], ignore_index=True)

    # ── Escribir a Excel ───────────────────────────────────────────────────
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_actual.to_excel(writer, sheet_name="ESTADO_ACTUAL", index=False)
        df_hist.to_excel(writer, sheet_name="HISTORIAL", index=False)

    buf.seek(0)
    wb = load_workbook(buf)

    # ── Estilo ESTADO_ACTUAL ───────────────────────────────────────────────
    ws = wb["ESTADO_ACTUAL"]
    _style_header(ws, len(COLS_ESTADO))

    # Columna de alerta_emoji para colorear filas
    emoji_col_idx = COLS_ESTADO.index("alerta_emoji") + 1

    for row_idx in range(2, ws.max_row + 1):
        emoji_cell = ws.cell(row=row_idx, column=emoji_col_idx)
        emoji = str(emoji_cell.value or "")
        color = EMOJI_COLOR.get(emoji, "FFFFFF")
        _apply_color(ws, row_idx, 1, len(COLS_ESTADO), color)

    _autofit(ws)
    ws.freeze_panes = "A2"

    # ── Estilo HISTORIAL ───────────────────────────────────────────────────
    ws_hist = wb["HISTORIAL"]
    _style_header(ws_hist, len(COLS_ESTADO))
    _autofit(ws_hist)
    ws_hist.freeze_panes = "A2"

    # ── Serializar ─────────────────────────────────────────────────────────
    out = io.BytesIO()
    wb.save(out)
    logger.info(
        "SALIDAS_MONITOR.xlsx generado: %d posiciones, %d filas historial",
        len(df_actual),
        len(df_hist),
    )
    return out.getvalue()
