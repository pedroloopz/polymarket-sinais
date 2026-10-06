"""Módulo 8 — mercados dos temas vencendo em poucos dias."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from bot import formato as f
from bot.analise.mercados import Linha, ativos
from bot.config import Config


def vencendo(con: sqlite3.Connection, cfg: Config, agora: datetime) -> list[Linha]:
    dias = cfg.regras.get("prazos", {}).get("dias_vencendo", 3)
    limite = agora + timedelta(days=dias)
    minimo = cfg.regras.get("filtros", {}).get("volume_min_exibir_usd", 0)
    linhas = [x for x in ativos(con, agora) if x.fim and agora <= x.fim <= limite and x.volume >= minimo]
    return sorted(linhas, key=lambda x: x.fim)


def texto(linhas: list[Linha], cfg: Config) -> str:
    dias = cfg.regras.get("prazos", {}).get("dias_vencendo", 3)
    if not linhas:
        return f"⏳ Nenhum mercado dos temas vence nos próximos {dias} dias."
    partes = [f"⏳ <b>Vencendo em até {dias} dias</b>"]
    for x in linhas[:15]:
        emoji = cfg.temas.get(x.tema, {}).get("emoji", "•")
        nome = f.esc(f.encurtar(x.pergunta, 70))
        partes.append(f"{emoji} {nome} — {f.data_hora(x.fim)}: {f.prob(x.prob)} ({f.pp(x.var_24h)} em 24 h)")
    return "\n".join(partes)
