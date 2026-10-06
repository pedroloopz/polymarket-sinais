"""Módulos 11 e 11b — stop por volatilidade, tamanho de posição, alvo, ganho/risco e stop de tempo."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd


@dataclass
class Plano:
    entrada: float
    stop: float
    alvo: float | None
    alvo_parcial: float | None
    ganho_risco: float | None
    quantidade: float | None  # ações (arredondado para baixo); None sem capital
    valor_moeda: float | None  # valor da posição na moeda do ativo
    stop_tempo: datetime | None


def atr(ohlc: pd.DataFrame, n: int = 14) -> float | None:
    """Average True Range de n dias (média simples dos true ranges)."""
    if ohlc is None or len(ohlc) < n + 1:
        return None
    alta, baixa, fech = ohlc["High"], ohlc["Low"], ohlc["Close"]
    tr = pd.concat([alta - baixa, (alta - fech.shift()).abs(), (baixa - fech.shift()).abs()], axis=1).max(
        axis=1
    )
    valor = float(tr.iloc[-n:].mean())
    return valor if valor > 0 and not math.isnan(valor) else None


def pregao(cfg_pregoes: dict, bolsa: str) -> tuple[ZoneInfo, tuple[int, int], tuple[int, int]]:
    p = cfg_pregoes.get(bolsa) or cfg_pregoes.get("EUA", {})
    abre = tuple(int(x) for x in p.get("abre", "09:30").split(":"))
    fecha = tuple(int(x) for x in p.get("fecha", "16:00").split(":"))
    return ZoneInfo(p.get("fuso", "America/New_York")), abre, fecha


def pregao_aberto(cfg_pregoes: dict, bolsa: str, agora: datetime) -> bool:
    """Pelo relógio da bolsa, em dia útil. Feriados não são considerados."""
    fuso, abre, fecha = pregao(cfg_pregoes, bolsa)
    local = agora.astimezone(fuso)
    if bolsa not in ("CRIPTO",) and local.weekday() >= 5:
        return False
    return abre <= (local.hour, local.minute) < fecha


def fim_do_pregao(cfg_pregoes: dict, bolsa: str, agora: datetime) -> datetime:
    fuso, _, fecha = pregao(cfg_pregoes, bolsa)
    local = agora.astimezone(fuso)
    return local.replace(hour=fecha[0], minute=fecha[1], second=0, microsecond=0)


def montar_plano(
    *,
    entrada: float,
    sentido: int,
    espaco: float | None,
    atr_valor: float | None,
    regras: dict,
    capital_moeda_ativo: float | None,
    defasagem_min: float | None,
    fim_pregao: datetime | None,
    agora: datetime,
) -> Plano | None:
    """`espaco`: movimento restante esperado (fração, já com sinal). Sem ATR não há stop → sem plano."""
    r = regras.get("risco", {})
    if not atr_valor or entrada <= 0:
        return None
    stop = entrada - sentido * r.get("atr_multiplo_stop", 1.5) * atr_valor
    risco_unit = abs(entrada - stop)
    alvo = alvo_parcial = ganho_risco = None
    if espaco is not None:
        alvo = entrada * (1 + espaco)
        alvo_parcial = entrada * (1 + espaco / 2)
        ganho_risco = abs(alvo - entrada) / risco_unit if risco_unit else None
    quantidade = valor = None
    if capital_moeda_ativo and risco_unit:
        orcamento = capital_moeda_ativo * r.get("risco_por_operacao_pct", 1.0) / 100
        quantidade = math.floor(orcamento / risco_unit)
        quantidade = min(quantidade, math.floor(capital_moeda_ativo / entrada))  # sem alavancagem
        valor = quantidade * entrada
    stop_tempo = None
    if defasagem_min and defasagem_min > 0:
        stop_tempo = agora + timedelta(minutes=r.get("stop_tempo_multiplo_defasagem", 2) * defasagem_min)
        if fim_pregao:
            stop_tempo = min(stop_tempo, fim_pregao)
    elif fim_pregao:
        stop_tempo = fim_pregao
    return Plano(entrada, stop, alvo, alvo_parcial, ganho_risco, quantidade, valor, stop_tempo)
