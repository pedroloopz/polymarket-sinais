"""Formatação no padrão brasileiro (datas dd/mm, vírgula decimal, R$ / US$)."""

from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")
MENOS = "−"  # sinal de menos tipográfico, como nos exemplos do PROMPT


def _num(valor: float, casas: int) -> str:
    """1234.5 → '1.234,50' (sem sinal)."""
    texto = f"{abs(valor):,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def numero(valor: float, casas: int = 2, sinal: bool = False) -> str:
    base = _num(valor, casas)
    if valor < 0 and base.strip("0,.") != "":
        return MENOS + base
    if sinal and valor > 0:
        return "+" + base
    return base


def pct(fracao: float, casas: int = 1, sinal: bool = False) -> str:
    """0.125 → '12,5%'."""
    return numero(fracao * 100, casas, sinal) + "%"


def prob(p: float | None) -> str:
    """Probabilidade 0–1 → '91%'. Extremos viram '<1%' / '>99%'."""
    if p is None:
        return "—"
    if p < 0.01:
        return "<1%"
    if p > 0.99:
        return ">99%"
    return f"{round(p * 100):d}%"


def pp(delta: float | None) -> str:
    """Variação de probabilidade (0–1) em pontos percentuais: 0.015 → '+1,5 p.p.'."""
    if delta is None:
        return "—"
    return numero(delta * 100, 1, sinal=True) + " p.p."


def dinheiro(valor: float, moeda: str = "BRL") -> str:
    simbolo = {"BRL": "R$", "USD": "US$"}.get(moeda, moeda)
    texto = _num(valor, 2)
    return f"{MENOS if valor < 0 else ''}{simbolo} {texto}"


def volume(valor: float | None) -> str:
    """Volume compacto em dólares: 1_234_567 → 'US$ 1,2 mi'."""
    if valor is None:
        return "—"
    if valor >= 1e9:
        return f"US$ {_num(valor / 1e9, 1)} bi"
    if valor >= 1e6:
        return f"US$ {_num(valor / 1e6, 1)} mi"
    if valor >= 1e3:
        return f"US$ {_num(valor / 1e3, 0)} mil"
    return f"US$ {_num(valor, 0)}"


def local(dt: datetime) -> datetime:
    return dt.astimezone(FUSO)


def data(dt: datetime) -> str:
    return local(dt).strftime("%d/%m")


def hora(dt: datetime) -> str:
    return local(dt).strftime("%H:%M")


def data_hora(dt: datetime) -> str:
    return local(dt).strftime("%d/%m %H:%M")


def esc(texto: str) -> str:
    """Escapa texto para parse_mode=HTML do Telegram."""
    return html.escape(texto, quote=False)


def encurtar(texto: str, limite: int = 70) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"
