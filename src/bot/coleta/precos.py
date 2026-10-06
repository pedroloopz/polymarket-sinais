"""Preços de ações, ETFs e indicadores via yfinance (gratuito, não oficial).

O yfinance raspa o Yahoo Finance e às vezes falha ou é limitado; por isso cada chamada
é isolada e uma falha vira "⚠️ fonte indisponível" em vez de derrubar o bot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from bot.logs import aviso, log

_log = log("precos")


@dataclass
class Cotacao:
    ticker: str
    preco: float
    ts_fonte: datetime


def _yf():
    import yfinance as yf  # importação tardia: testes não precisam de rede

    return yf


def _fechamentos(df: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        nivel0 = df.columns.get_level_values(0)
        if "Close" in nivel0:
            return df["Close"]
        return df.xs("Close", axis=1, level=1)
    return df[["Close"]].rename(columns={"Close": tickers[0]})


def ultimas_cotacoes(tickers: list[str]) -> dict[str, Cotacao]:
    """Último preço disponível (intervalo de 15 min, últimos 5 dias) de cada ticker."""
    if not tickers:
        return {}
    df = _yf().download(
        tickers,
        period="5d",
        interval="15m",
        progress=False,
        auto_adjust=False,
        threads=True,
        group_by="column",
    )
    closes = _fechamentos(df, tickers)
    saida: dict[str, Cotacao] = {}
    for ticker in tickers:
        if ticker not in closes:
            continue
        serie = closes[ticker].dropna()
        if serie.empty:
            continue
        ts = serie.index[-1].to_pydatetime()
        ts = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
        saida[ticker] = Cotacao(ticker, float(serie.iloc[-1]), ts.astimezone(UTC))
    faltando = sorted(set(tickers) - set(saida))
    if faltando:
        aviso(_log, "tickers sem cotação", tickers=faltando)
    return saida


def historico_diario(tickers: list[str], periodo: str = "3y") -> pd.DataFrame:
    """Fechamentos diários (colunas = tickers)."""
    df = _yf().download(
        tickers,
        period=periodo,
        interval="1d",
        progress=False,
        auto_adjust=False,
        threads=True,
        group_by="column",
    )
    return _fechamentos(df, tickers)


def barras_intradiarias(tickers: list[str], dias: int = 30, intervalo_min: int = 5) -> pd.DataFrame:
    """Fechamentos intradiários em UTC (colunas = tickers). O Yahoo dá 5 min por até 60 dias."""
    df = _yf().download(
        tickers,
        period=f"{dias}d",
        interval=f"{intervalo_min}m",
        progress=False,
        auto_adjust=False,
        threads=True,
        group_by="column",
    )
    closes = _fechamentos(df, tickers)
    if not closes.empty:
        idx = pd.DatetimeIndex(closes.index)
        closes.index = idx.tz_convert("UTC") if idx.tz is not None else idx.tz_localize("UTC")
    return closes


def ohlc_diario(ticker: str, dias: int = 60) -> pd.DataFrame:
    """Máxima, mínima e fechamento diários (para o ATR do stop)."""
    df = _yf().Ticker(ticker).history(period=f"{dias}d", interval="1d", auto_adjust=False)
    return df[["High", "Low", "Close"]].dropna() if df is not None and not df.empty else pd.DataFrame()


def datas_balanco(ticker: str, limite: int = 12) -> pd.DataFrame:
    """Datas de balanço (passadas e futuras) com EPS estimado/realizado."""
    df = _yf().Ticker(ticker).get_earnings_dates(limit=limite)
    return df if df is not None else pd.DataFrame()


def calendario(ticker: str) -> dict:
    """Calendário do Yahoo. 'Earnings Date' com 2 datas = janela estimada; com 1 = data informada."""
    try:
        cal = _yf().Ticker(ticker).calendar
    except Exception as erro:
        aviso(_log, "calendário indisponível", ticker=ticker, erro=str(erro))
        return {}
    return cal if isinstance(cal, dict) else {}
