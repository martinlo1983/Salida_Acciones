"""
main.py
-------
Orquestador principal del sistema de monitoreo de salidas.

Flujo:
  1. Descarga los 5 archivos fuente desde Google Drive.
  2. Lee tenencia (Satélites + Acciones) y fechas de primera compra.
  3. Para cada posición:
       - Obtiene datos de mercado desde yfinance.
       - Aplica las reglas de salida del documento.
       - Genera la alerta correspondiente.
  4. Sube SALIDAS_MONITOR.xlsx a Drive (crea o actualiza).
  5. Imprime resumen en stdout (visible en el log de GitHub Actions).

Variables de entorno requeridas:
  GOOGLE_SA_JSON    : contenido JSON de la service account
  DRIVE_FOLDER_ID   : (opcional) ID de carpeta en Drive para buscar/crear archivos
"""

import json
import logging
import os
import sys
from datetime import date

import pandas as pd

from drive_reader import DriveClient
from tenencia import leer_tenencia
from market_data import get_datos_mercado
from reglas_satelites import (
    leer_ranking,
    calcular_stop_s1,
    evaluar_s2_s3,
    generar_alerta_satelite,
)
from reglas_tacticos import (
    leer_modelo_acciones,
    leer_tipo_empresa,
    calcular_t1,
    calcular_t2,
    evaluar_t3,
    evaluar_t4,
    generar_alerta_tactico,
)
from output_writer import generar_excel
from generar_html import generar_html

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


# ─── TIR objetivo por ticker (completar manualmente) ─────────────────────────
# Si no querés que aplique T3 para un ticker, no lo incluyas aquí.
# Valor en % anualizado (ej: 30 = 30% TIR anual objetivo).

TIR_OBJETIVO = {
    # "ORCL": 25,
    # "ADBE": 30,
    # "OXY":  20,
}


# ─── Función principal ────────────────────────────────────────────────────────

def main():
    # 1. Conectar a Drive
    sa_json = os.environ.get("GOOGLE_SA_JSON")
    if not sa_json:
        logger.error("Variable de entorno GOOGLE_SA_JSON no definida.")
        sys.exit(1)

    drive = DriveClient(sa_json)

    # 2. Descargar archivos
    logger.info("Descargando archivos desde Google Drive...")
    bytes_rendimiento   = drive.download("rendimiento")
    bytes_transacciones = drive.download("transacciones")
    bytes_satelites     = drive.download("satelites")
    bytes_acciones      = drive.download("acciones")

    # Intentar bajar el monitor existente (para el historial)
    try:
        bytes_monitor_prev = drive.download("monitor")
    except FileNotFoundError:
        logger.info("SALIDAS_MONITOR.xlsx no existe aún — se creará desde cero.")
        bytes_monitor_prev = None

    # Leer hoja CONFIG de SALIDAS_MONITOR (tipo A/B, objetivo de rentabilidad y comentarios)
    tipo_posicion = {}
    try:
        df_config = drive.download_sheet("monitor", "CONFIG")
        df_config.columns = [str(c).strip().lower() for c in df_config.columns]
        if "ticker" in df_config.columns:
            df_config = df_config.dropna(subset=["ticker"])
            tickers = df_config["ticker"].str.strip().str.upper()

            # Tipo A/B
            if "tipo" in df_config.columns:
                tipos_validos = df_config["tipo"].notna()
                tipo_posicion = dict(zip(
                    tickers[tipos_validos],
                    df_config.loc[tipos_validos, "tipo"].str.strip().str.upper()
                ))

            # Objetivo de rentabilidad % desde CONFIG
            if "tir_objetivo" in df_config.columns:
                for _, row in df_config.iterrows():
                    t = str(row["ticker"]).strip().upper()
                    val = row["tir_objetivo"]
                    if pd.notna(val) and str(val).strip() not in ("", "nan"):
                        try:
                            TIR_OBJETIVO[t] = float(val)
                        except (ValueError, TypeError):
                            logger.warning("tir_objetivo inválido para %s: %s", t, val)

            logger.info("CONFIG cargada — tipos: %s | Objetivos rentab.: %s", tipo_posicion, TIR_OBJETIVO)
        else:
            logger.warning("Hoja CONFIG no tiene columna 'ticker' — se ignora")
    except Exception as e:
        logger.warning("No se pudo leer CONFIG desde SALIDAS_MONITOR: %s", e)

    # 3. Leer tenencia
    logger.info("Leyendo tenencia de Portfolio Performance...")
    df_tenencia = leer_tenencia(bytes_rendimiento, bytes_transacciones)
    logger.info("Posiciones a analizar: %d", len(df_tenencia))

    # 4. Leer fuentes de enriquecimiento
    df_ranking   = leer_ranking(bytes_satelites)
    df_modelo    = leer_modelo_acciones(bytes_acciones)
    df_tipos     = leer_tipo_empresa(bytes_acciones)

    # Index de modelo por ticker para lookup rápido
    modelo_idx = df_modelo.set_index("TICKER") if "TICKER" in df_modelo.columns else pd.DataFrame()
    tipos_idx  = df_tipos.set_index("ticker")

    # 5. Procesar cada posición
    resultados = []
    errores    = []

    for _, pos in df_tenencia.iterrows():
        ticker        = pos["ticker"]
        cat           = pos["categoria"]
        ganancia_pp   = pos["ganancia_pct_pp"]   # ratio decimal desde PP (ej: 0.25)
        fecha_entrada = pos["fecha_primera_compra"]

        if pd.isna(fecha_entrada):
            logger.warning("%s: sin fecha de primera compra — saltado", ticker)
            errores.append(ticker)
            continue

        logger.info("Procesando %s (%s)...", ticker, cat)

        # Datos de mercado del subyacente (NYSE)
        mercado = get_datos_mercado(ticker, fecha_entrada)
        precio_actual = mercado["precio_actual_usd"]
        maximo        = mercado["maximo_desde_entrada_usd"]
        sigma         = mercado["sigma_mensual_12m"]

        if precio_actual is None:
            logger.warning("%s: precio actual no disponible — saltado", ticker)
            errores.append(ticker)
            continue

        # Precio compra equivalente del subyacente (retrocomputado desde ganancia PP)
        # ppp_equiv = precio_actual_subyacente / (1 + ganancia_pp)
        ppp_equiv = (precio_actual / (1 + ganancia_pp)) if ganancia_pp is not None else None

        # Máximo equivalente desde entrada (mismo ratio aplicado al máximo histórico)
        # No es exacto pero es la mejor aproximación sin historial de compras en USD subyacente
        maximo_equiv = maximo  # el máximo ya está en USD del subyacente

        # Base del resultado
        resultado = {
            "ticker":                   ticker,
            "categoria":                cat,
            "cantidad":                 pos.get("cantidad"),
            "coste_compra_usd":         round(pos["coste_compra_usd"], 2),
            "valor_mercado_usd":        round(pos["valor_mercado_usd"], 2),
            "ganancia_pct":             round(ganancia_pp * 100, 2) if ganancia_pp is not None else None,
            "ppp_equiv_usd":            round(ppp_equiv, 2) if ppp_equiv else None,
            "fecha_primera_compra":     fecha_entrada,
            "precio_actual_usd":        round(precio_actual, 2),
            "maximo_desde_entrada_usd": round(maximo, 2) if maximo else None,
            "sigma_mensual_12m":        round(sigma * 100, 2) if sigma else None,
        }

        # ── Satélites ──────────────────────────────────────────────────────
        if cat == "Largo Satelites":
            # Grupo temático del ranking
            fila_ranking = df_ranking[df_ranking["ticker"] == ticker]
            grupo = fila_ranking["grupo"].iloc[0] if not fila_ranking.empty else None

            resultado["grupo_satelite"] = grupo
            resultado["tipo_empresa"]   = None

            if sigma and maximo and ppp_equiv:
                s1 = calcular_stop_s1(grupo, ppp_equiv, precio_actual, maximo, sigma)
            else:
                s1 = {"stop_s1_usd": None, "s1_activado": False,
                      "s1_detalle": "Sin datos suficientes para S1"}

            s2s3 = evaluar_s2_s3(ticker, df_ranking)
            emoji, texto = generar_alerta_satelite(ticker, s1, s2s3)

            resultado.update({
                "stop_s1_usd":       s1.get("stop_s1_usd"),
                "kxsigma":           s1.get("kxsigma"),
                "s1_activado":       s1.get("s1_activado"),
                "rank_bruto":        s2s3.get("rank_bruto"),
                "rank_efectivo":     s2s3.get("rank_efectivo"),
                "score_etf":         s2s3.get("score_etf"),
                "score_top5":        s2s3.get("score_top5"),
                "delta_momentum":    s2s3.get("delta_momentum"),
                "s2_decision":       s2s3.get("s2_decision"),
                "s3_activado":       s2s3.get("s3_activado"),
                "alerta_emoji":      emoji,
                "alerta_texto":      texto,
            })

        # ── Tácticos (Largo Acciones) ──────────────────────────────────────
        elif cat == "Largo Acciones":
            # Tipo de empresa
            tipo_row = tipos_idx.loc[ticker] if ticker in tipos_idx.index else None
            tipo = str(tipo_row["tipo_empresa"]).upper() if tipo_row is not None else "GROWTH"
            tipo_ab = tipo_posicion.get(ticker, "B")  # default B si no está configurado
            resultado["tipo_empresa"]   = tipo
            resultado["grupo_satelite"] = None
            resultado["tipo_ab"] = tipo_ab

            t1 = calcular_t1(tipo, ppp_equiv, precio_actual) if tipo_ab == "B" else \
                 {"stop_t1_usd": None, "t1_activo": False, "t1_activado": False, "t1_detalle": "Tipo A — T1 no aplica"}
            t2 = calcular_t2(tipo, ppp_equiv, precio_actual, maximo) if maximo else \
                 {"stop_t2_usd": None, "t2_activo": False, "t2_activado": False, "y_pct": None}

            # T3
            tir_obj = TIR_OBJETIVO.get(ticker)
            fila_mod = modelo_idx.loc[ticker] if ticker in modelo_idx.index else None
            fase_mod = str(fila_mod["FASE"]) if fila_mod is not None and "FASE" in fila_mod else None
            t3 = evaluar_t3(precio_actual, ppp_equiv, tir_obj, fase_mod)

            # T4
            t4 = evaluar_t4(fila_mod)

            emoji, texto = generar_alerta_tactico(ticker, tipo, t1, t2, t3, t4)

            resultado.update({
                "stop_t1_usd":          t1.get("stop_t1_usd"),
                "t1_activo":            t1.get("t1_activo"),
                "t1_activado":          t1.get("t1_activado"),
                "stop_t2_usd":          t2.get("stop_t2_usd"),
                "t2_activo":            t2.get("t2_activo"),
                "t2_activado":          t2.get("t2_activado"),
                "y_pct":                t2.get("y_pct"),
                "fase_modelo":          t4.get("fase_modelo"),
                "accion_modelo":        t4.get("accion_modelo"),
                "flag_revision":        t4.get("flag_revision"),
                "tamano_posicion_pct":  t4.get("tamano_posicion_pct"),
                "t3_estado":            t3.get("t3_estado"),
                "t3_precio_objetivo":   t3.get("t3_precio_objetivo"),
                "tir_objetivo":         tir_obj,
                "alerta_emoji":         emoji,
                "alerta_texto":         texto,
            })

        resultados.append(resultado)

    # 6. Generar Excel
    logger.info("Generando SALIDAS_MONITOR.xlsx...")
    excel_bytes = generar_excel(resultados, bytes_existente=bytes_monitor_prev)

    # 7. Subir a Drive
    drive.upload_or_update(
        "monitor", excel_bytes,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # 8. Generar HTML y guardarlo como artefacto de Actions
    logger.info("Generando dashboard HTML... resultados: %d", len(resultados))
    if resultados:
        logger.info("Primer resultado: %s", list(resultados[0].keys())[:5])
    try:
        import io
        hist_prev = []
        if bytes_monitor_prev:
            try:
                df_hp = pd.read_excel(io.BytesIO(bytes_monitor_prev), sheet_name="HISTORIAL")
                hist_prev = df_hp.to_dict("records")
            except Exception:
                pass
        cambios_prev = []
        if bytes_monitor_prev:
            try:
                df_cp = pd.read_excel(io.BytesIO(bytes_monitor_prev), sheet_name="CAMBIOS")
                cambios_prev = df_cp.to_dict("records")
            except Exception:
                pass
        html_str = generar_html(resultados, cambios_prev, hist_prev + resultados)
        with open("SALIDAS_MONITOR.html", "w", encoding="utf-8") as f:
            f.write(html_str)
        logger.info("HTML guardado como SALIDAS_MONITOR.html")
    except Exception as e:
        logger.warning("No se pudo generar el HTML: %s", e)

    # 9. Resumen en stdout
    print("\n" + "═" * 60)
    print(f"  SALIDAS MONITOR — {date.today().isoformat()}")
    print("═" * 60)
    for r in sorted(resultados, key=lambda x: x["alerta_emoji"]):
        print(f"  {r['alerta_emoji']}  {r['ticker']:<8} ({r['categoria'][:4]})  {r['alerta_texto']}")
    if errores:
        print(f"\n  ⚠️  Saltados por falta de datos: {', '.join(errores)}")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    main()
