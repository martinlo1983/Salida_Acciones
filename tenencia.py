"""
tenencia.py
-----------
Lee el CSV de tenencia de Portfolio Performance y el CSV de todas las
transacciones, ambos desde Google Drive. Devuelve un DataFrame con las
posiciones activas de 'Largo Satelites' y 'Largo Acciones', enriquecidas
con la fecha de primera compra real (respetando re-entradas tras salida total).
"""

import re
import io
import logging
import pandas as pd

logger = logging.getLogger(__name__)


# ─── Constantes ───────────────────────────────────────────────────────────────

CATEGORIAS_OBJETIVO = {"Largo Satelites", "Largo Acciones"}

# Nombres de activos a excluir aunque caigan en las categorías objetivo
EXCLUIR_ACTIVOS = {
    "FCI - Superfondo RFD Parking Largo",
    "FCI - Superfondo RFD Parking Tactico",
    "USD REFUGIO LP",
    "BTC",          # no tiene subyacente en NYSE para calcular stops en USD
}


# ─── Parseo de nombres → ticker limpio ────────────────────────────────────────

def extract_ticker(name: str) -> str | None:
    """
    Extrae el ticker del subyacente a partir del nombre largo de PP.

    Patrones reconocidos:
      CEDEAR ETF - SAT/TAC/CORE - TICKER - Descripción
      CEDEAR - SAT/TAC/CORE - TICKER - Descripción
      CEDEAR - TICKER - Descripción
      ON CODIGO - Descripción
    Devuelve None si no puede parsearlo (FCI, bonos, etc.).
    """
    name = str(name).strip()

    # Patrón 1: con categoría intermedia (SAT, TAC, CORE)
    m = re.search(
        r"CEDEAR(?:\s+ETF)?\s*-\s*(?:SAT|TAC|CORE)\s*-\s*([A-Z0-9]{2,6})\s*-",
        name,
    )
    if m:
        return m.group(1)

    # Patrón 2: CEDEAR directo sin categoría
    m = re.search(r"CEDEAR\s*-\s*([A-Z0-9]{2,6})\s*-", name)
    if m:
        return m.group(1)

    # Patrón 3: obligaciones negociables "ON CODIGO - ..."
    m = re.search(r"^ON\s+([A-Z0-9]+)\s*-", name)
    if m:
        return m.group(1)

    return None  # FCI, bonos, BTC, etc.


# ─── Parseo numérico (formato español: 1.234,56) ─────────────────────────────

def parse_num(val) -> float:
    if pd.isna(val):
        return 0.0
    s = str(val).strip()
    # Eliminar prefijos de moneda (ARS, USD)
    s = re.sub(r"^[A-Z$\s]+", "", s)
    # Quitar separadores de miles y convertir decimal
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


# ─── Fecha de primera compra real (respeta re-entradas) ──────────────────────

def calcular_fechas_entrada(df_tx: pd.DataFrame) -> pd.DataFrame:
    """
    Dado el DataFrame de transacciones, calcula por ticker la fecha de primera
    compra de la posición ACTUAL, respetando la regla:

      Si en algún momento la posición llegó a 0 (o negativa), la fecha de
      entrada válida es la primera compra POSTERIOR a esa salida total.

    Retorna un DataFrame con columnas [ticker, fecha_primera_compra].
    """
    ops = df_tx[df_tx["Tipo"].isin(["Compra", "Venta"])].copy()
    ops["ticker"] = ops["Activo"].apply(extract_ticker)
    ops = ops.dropna(subset=["ticker"])
    ops["qty"] = ops["Títulos"].apply(parse_num)
    ops["qty_signed"] = ops.apply(
        lambda r: r["qty"] if r["Tipo"] == "Compra" else -r["qty"], axis=1
    )

    def _primera_entrada(group):
        group = group.sort_values("Fecha")
        running = 0.0
        last_zero_idx = None
        for i, row in group.iterrows():
            running += row["qty_signed"]
            running = round(running, 8)
            if running <= 0:
                last_zero_idx = i
        buys = group[group["Tipo"] == "Compra"]
        if last_zero_idx is None:
            return buys["Fecha"].min() if not buys.empty else pd.NaT
        buys_after = buys[buys.index > last_zero_idx]
        return buys_after["Fecha"].min() if not buys_after.empty else pd.NaT

    result = (
        ops.groupby("ticker")
        .apply(_primera_entrada)
        .reset_index()
    )
    result.columns = ["ticker", "fecha_primera_compra"]
    result["fecha_primera_compra"] = pd.to_datetime(
        result["fecha_primera_compra"]
    ).dt.date
    return result.dropna(subset=["fecha_primera_compra"])


# ─── Lectura principal ────────────────────────────────────────────────────────

def leer_tenencia(
    csv_balance_bytes: bytes,
    csv_rendimiento_bytes: bytes,
    csv_transacciones_bytes: bytes,
) -> pd.DataFrame:
    """
    Parámetros
    ----------
    csv_balance_bytes       : contenido del archivo PP_Balance_de_activos.csv
    csv_rendimiento_bytes   : contenido de PP_Valores_y_rendimiento_...csv
    csv_transacciones_bytes : contenido de Todas_las_transacciones.csv

    Retorna
    -------
    DataFrame con columnas:
        ticker, nombre_pp, categoria, cantidad, precio_compra_usd,
        fecha_primera_compra
    """
    # 1. Leer CSV de rendimiento → filtrar categorías objetivo
    df_rend = pd.read_csv(
        io.BytesIO(csv_rendimiento_bytes), sep=None, engine="python"
    )
    df_rend = df_rend[
        df_rend["Plazo de Inversion (Nivel 1)"].isin(CATEGORIAS_OBJETIVO)
    ].copy()

    # 2. Extraer ticker y precio compra USD
    df_rend["ticker"] = df_rend["Nombre"].apply(extract_ticker)
    df_rend["precio_compra_usd"] = df_rend["Precio de compra"].apply(parse_num)
    df_rend["cantidad"] = df_rend["Nº de títulos"].apply(parse_num)

    # 3. Leer CSV de balance → para tener el símbolo limpio como referencia
    df_bal = pd.read_csv(
        io.BytesIO(csv_balance_bytes), sep=None, engine="python"
    )
    # Quitar filas de subtotales (sin símbolo individual)
    df_bal = df_bal.dropna(subset=["Símbolo"])
    df_bal["ticker_bal"] = df_bal["Símbolo"].str.replace(r"\.BA$", "", regex=True)

    # 4. Calcular fechas de primera compra desde transacciones
    df_tx = pd.read_csv(
        io.BytesIO(csv_transacciones_bytes), sep=None, engine="python"
    )
    df_tx["Fecha"] = pd.to_datetime(df_tx["Fecha"])
    df_fechas = calcular_fechas_entrada(df_tx)

    # 5. Armar DataFrame final
    cols_rend = ["Nombre", "Plazo de Inversion (Nivel 1)", "ticker",
                 "precio_compra_usd", "cantidad"]
    df = df_rend[cols_rend].rename(columns={
        "Nombre": "nombre_pp",
        "Plazo de Inversion (Nivel 1)": "categoria",
    })

    # Excluir activos no relevantes para el análisis de salidas
    df = df[~df["nombre_pp"].isin(EXCLUIR_ACTIVOS)]
    df = df.dropna(subset=["ticker"])  # descarta FCI, bonos sin ticker

    # 6. Join con fechas de entrada
    df = df.merge(df_fechas, on="ticker", how="left")

    missing_dates = df[df["fecha_primera_compra"].isna()]["ticker"].tolist()
    if missing_dates:
        logger.warning(
            "Sin fecha de primera compra para: %s. "
            "Verificar que estén en el CSV de transacciones.",
            missing_dates,
        )

    df = df.reset_index(drop=True)
    logger.info(
        "Tenencia cargada: %d posiciones (%s)",
        len(df),
        df["categoria"].value_counts().to_dict(),
    )
    return df


# ─── Validación rápida (ejecución directa para debugging) ────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 4:
        print("Uso: python tenencia.py <balance.csv> <rendimiento.csv> <transacciones.csv>")
        sys.exit(1)

    paths = sys.argv[1:4]
    raw = [open(p, "rb").read() for p in paths]
    df = leer_tenencia(*raw)
    print(df.to_string(index=False))
