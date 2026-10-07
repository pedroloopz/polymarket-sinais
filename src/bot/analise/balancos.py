"""Módulo 10 — balanços das empresas ligadas a cripto."""

from __future__ import annotations

import math
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from bot import formato as f
from bot.analise.mercados import Linha, ativos
from bot.config import Config
from bot.logs import aviso, log

NY = ZoneInfo("America/New_York")
LEMBRETE = "ℹ️ Bater a estimativa ≠ ação subir: o que pesa é a projeção futura e o que já estava precificado."
_log = log("balancos")


@dataclass
class Balanco:
    ticker: str
    proxima: datetime | None = None
    status: str = "desconhecida"  # confirmada | estimada | desconhecida
    mercado: Linha | None = None
    reacoes: list[tuple[date, float]] = field(default_factory=list)
    erro: str | None = None

    def dias_ate(self, agora: datetime) -> int | None:
        if not self.proxima:
            return None
        return (self.proxima.astimezone(NY).date() - agora.astimezone(NY).date()).days


def dia_de_reacao(momento: datetime, pregoes: pd.DatetimeIndex) -> pd.Timestamp | None:
    """Pregão que reage ao balanço.

    Divulgação antes da abertura (antes de 09:30 NY) → reage no mesmo dia.
    Depois do fechamento ou horário desconhecido (00:00) → reage no pregão seguinte.
    """
    local = momento.astimezone(NY)
    dia = pd.Timestamp(local.date())
    antes_da_abertura = (local.hour, local.minute) != (0, 0) and (local.hour, local.minute) < (9, 30)
    pos = pregoes.searchsorted(dia, side="left" if antes_da_abertura else "right")
    return pregoes[pos] if pos < len(pregoes) else None


def reacoes(momentos: list[datetime], fechamentos: pd.Series, n: int = 8) -> list[tuple[date, float]]:
    serie = fechamentos.dropna()
    if serie.empty:
        return []
    idx = pd.DatetimeIndex(serie.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    serie.index = idx.normalize()
    saida: list[tuple[date, float]] = []
    for momento in sorted(momentos, reverse=True):
        dia = dia_de_reacao(momento, serie.index)
        if dia is None:
            continue
        pos = serie.index.get_loc(dia)
        if not isinstance(pos, int) or pos == 0:
            continue
        ret = float(serie.iloc[pos] / serie.iloc[pos - 1] - 1)
        if not math.isnan(ret):
            saida.append((momento.astimezone(NY).date(), ret))
        if len(saida) >= n:
            break
    return saida


def _mercado_da_empresa(nomes: list[str], linhas: list[Linha]) -> Linha | None:
    for linha in linhas:
        if linha.palavras_ditas:
            continue
        texto = (linha.original or linha.pergunta).lower()
        if "earnings" in texto and any(re.search(rf"\b{re.escape(n)}\b", texto) for n in nomes):
            return linha
    return None


def _proxima(cal: dict, datas: pd.DataFrame, agora: datetime) -> tuple[datetime | None, str]:
    brutas = cal.get("Earnings Date") or []
    futuras = []
    for d in brutas if isinstance(brutas, list) else [brutas]:
        dt = datetime(d.year, d.month, d.day, tzinfo=NY) if isinstance(d, date) else None
        if dt and dt.date() >= agora.astimezone(NY).date():
            futuras.append(dt)
    if futuras:
        return min(futuras), ("confirmada" if len(brutas) == 1 else "estimada")
    if not datas.empty:
        idx = [t.to_pydatetime() for t in datas.index]
        proximas = [t for t in idx if t >= agora]
        if proximas:
            return min(proximas), "estimada"
    return None, "desconhecida"


def levantar(
    con: sqlite3.Connection,
    cfg: Config,
    agora: datetime,
    obter_datas: Callable[[str], pd.DataFrame],
    obter_calendario: Callable[[str], dict],
    obter_historico: Callable[[list[str]], pd.DataFrame],
) -> list[Balanco]:
    n = cfg.regras.get("balancos", {}).get("reacoes_historicas", 8)
    linhas = ativos(con, agora, tema="balancos_cripto", visto_desde_h=48)
    tickers = list(cfg.empresas_cripto)
    try:
        historico = obter_historico(tickers)
    except Exception as erro:
        aviso(_log, "histórico diário indisponível", erro=str(erro))
        historico = pd.DataFrame()

    saida = []
    for ticker, info in cfg.empresas_cripto.items():
        b = Balanco(ticker=ticker, mercado=_mercado_da_empresa(info.get("nomes", []), linhas))
        try:
            datas = obter_datas(ticker)
            b.proxima, b.status = _proxima(obter_calendario(ticker), datas, agora)
            if not datas.empty and ticker in historico:
                passadas = [t.to_pydatetime() for t in datas.index if t.to_pydatetime() < agora]
                if "Reported EPS" in datas:
                    passadas = [
                        t.to_pydatetime()
                        for t, v in datas["Reported EPS"].items()
                        if t.to_pydatetime() < agora and pd.notna(v)
                    ]
                b.reacoes = reacoes(passadas, historico[ticker], n)
        except Exception as erro:
            b.erro = str(erro)
            aviso(_log, "balanço indisponível", ticker=ticker, erro=str(erro))
        saida.append(b)
    return saida


def linha_resumo(b: Balanco, agora: datetime) -> str:
    data = f"{f.data(b.proxima)} ({b.status})" if b.proxima else "data não divulgada"
    merc = f"Polymarket: {f.prob(b.mercado.prob)} bate" if b.mercado else "mercado ainda não criado"
    dias = b.dias_ate(agora)
    contagem = f" ⏳ {dias} d" if dias is not None and dias >= 0 else ""
    return f"🪙 {b.ticker} balanço: {data}{contagem} — {merc}"


def no_resumo(balancos: list[Balanco], cfg: Config, agora: datetime) -> list[str]:
    """Só entra no resumo diário quem divulga nos próximos N dias (contagem regressiva)."""
    limite = cfg.regras.get("balancos", {}).get("contagem_regressiva_dias", 10)
    escolhidos = [b for b in balancos if (d := b.dias_ate(agora)) is not None and 0 <= d <= limite]
    return [linha_resumo(b, agora) for b in sorted(escolhidos, key=lambda b: b.proxima)]


def texto_completo(balancos: list[Balanco], agora: datetime) -> str:
    partes = ["🪙 <b>Balanços de cripto</b>"]
    for b in sorted(balancos, key=lambda b: b.proxima or datetime.max.replace(tzinfo=UTC)):
        partes.append(linha_resumo(b, agora))
        if b.reacoes:
            subiu = sum(1 for _, r in b.reacoes if r > 0)
            media = sum(r for _, r in b.reacoes) / len(b.reacoes)
            ultimos = " ".join(f.pct(r, 1, sinal=True) for _, r in b.reacoes[:4])
            partes.append(
                f"   Dia seguinte (últ. {len(b.reacoes)}): subiu {subiu}× | média "
                f"{f.pct(media, 1, sinal=True)} | recentes: {ultimos}"
            )
        elif b.erro:
            partes.append("   ⚠️ dados do Yahoo indisponíveis")
    partes.append(LEMBRETE)
    return "\n".join(partes)
