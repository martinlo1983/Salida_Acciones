"""
market_data.py
--------------
Obtiene datos de mercado desde Yahoo Finance (yfinance) para cada ticker:
  - Precio actual USD
  - Máximo histórico desde la fecha de primera compra
  - Volatilidad mensual promedio 12m (σ mensual)

Todos los precios son del subyacente en USD (NYSE/NASDAQ), no del Cedear en ARS.
"""

import logging
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Cache de descarga para no hacer requests repetidos en el mismo run
_price_cache: dict[str, pd.DataFrame] = {}


def _get_history(ticker: str, start: date) -> pd.DataFrame:
    """Descarga histórico diario desde 'start' hasta hoy. Cachea por ticker."""
    if ticker not in _price_cache:
        # Pedimos desde 13 meses atrás para tener datos suficientes de σ
        fetch_start = min(start, date.today() - timedelta(days=400))
        try:
            df = yf.download(
                ticker,
                start=fetch_start.isoformat(),
                end=(date.today() + timedelta(days=1)).isoformat(),
                auto_adjust=True,
                progress=False,
            )
            if df.empty:
                logger.warning("yfinance: sin datos para %s", ticker)
                _price_cache[ticker] = pd.DataFrame()
            else:
                # Flatten MultiIndex si viene así
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                _price_cache[ticker] = df
        except Exception as e:
            logger.error("Error descargando %s: %s", ticker, e)
            _price_cache[ticker] = pd.DataFrame()
    return _price_cache[ticker]


def get_precio_actual(ticker: str) -> Optional[float]:
    """Precio de cierre más reciente en USD."""
    df = _get_history(ticker, date.today() - timedelta(days=10))
    if df.empty:
        return None
    return float(df["Close"].iloc[-1])


def get_maximo_desde_entrada(ticker: str, fecha_entrada: date) -> Optional[float]:
    """Mayor precio de cierre desde la fecha de primera compra hasta hoy."""
    df = _get_history(ticker, fecha_entrada)
    if df.empty:
        return None
    df_desde = df[df.index.date >= fecha_entrada]
    if df_desde.empty:
        return None
    return float(df_desde["Close"].max())


def get_sigma_mensual_12m(ticker: str) -> Optional[float]:
    """
    Volatilidad mensual promedio de los últimos 12 meses.
    Se calcula como la desviación estándar de los 12 retornos mensuales
    (cierre a cierre de cada mes) del último año.
    Retorna el valor como fracción (ej: 0.045 = 4.5%).
    """
    fetch_start = date.today() - timedelta(days=400)  # ~13 meses
    df = _get_history(ticker, fetch_start)
    if df.empty or len(df) < 20:
        return None

    # Resamplear a cierre mensual
    monthly = df["Close"].resample("ME").last().dropna()
    if len(monthly) < 3:
        return None

    # Tomar los últimos 12 meses (o menos si no hay suficiente historia)
    monthly = monthly.iloc[-13:]  # 13 cierres = 12 retornos
    returns = monthly.pct_change().dropna()

    if len(returns) < 3:
        return None

    sigma = float(returns.std())
    logger.debug("σ mensual 12m %s: %.4f", ticker, sigma)
    return sigma


def get_datos_mercado(ticker: str, fecha_entrada: date) -> dict:
    """
    Wrapper que retorna todos los datos de mercado para un ticker en un dict.
    Pensado para iterar sobre el DataFrame de tenencia.
    """
    precio_actual = get_precio_actual(ticker)
    maximo = get_maximo_desde_entrada(ticker, fecha_entrada)
    sigma = get_sigma_mensual_12m(ticker)

    return {
        "precio_actual_usd": precio_actual,
        "maximo_desde_entrada_usd": maximo,
        "sigma_mensual_12m": sigma,
    }
