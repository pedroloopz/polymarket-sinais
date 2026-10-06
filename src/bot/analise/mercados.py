"""Consultas comuns sobre os mercados guardados (probabilidade atual, variação 24 h, agrupamento)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from bot.db import de_iso, iso


@dataclass
class Linha:
    id: str
    tema: str
    pergunta: str
    item: str
    evento_id: str
    evento_titulo: str
    link: str
    fim: datetime | None
    criado_em: datetime | None
    volume: float
    prob: float | None
    var_24h: float | None
    palavras_ditas: bool


def variacao_24h(
    con: sqlite3.Connection, mercado_id: str, agora: datetime, prob_atual: float | None
) -> float | None:
    """Δp em 24 h pela nossa série (leitura mais próxima de 24 h atrás, tolerância de 3 h)."""
    if prob_atual is None:
        return None
    alvo = agora - timedelta(hours=24)
    linha = con.execute(
        """SELECT valor, ts FROM series WHERE tipo='mercado' AND chave=? AND ts BETWEEN ? AND ?
           ORDER BY ABS(julianday(ts) - julianday(?)) LIMIT 1""",
        (mercado_id, iso(alvo - timedelta(hours=3)), iso(alvo + timedelta(hours=3)), iso(alvo)),
    ).fetchone()
    if not linha or linha["valor"] is None:
        return None
    return prob_atual - linha["valor"]


def _linha(con: sqlite3.Connection, r: sqlite3.Row, agora: datetime) -> Linha:
    var = variacao_24h(con, r["id"], agora, r["prob"])
    if var is None:
        var = r["var_24h_gamma"]
    slug = r["evento_slug"] or r["slug"]
    return Linha(
        id=r["id"],
        tema=r["tema"],
        pergunta=r["pergunta"],
        item=r["item"] or "",
        evento_id=r["evento_id"] or "",
        evento_titulo=r["evento_titulo"] or "",
        link=f"https://polymarket.com/event/{slug}" if slug else "",
        fim=de_iso(r["fim"]),
        criado_em=de_iso(r["criado_em"]),
        volume=r["volume"] or 0.0,
        prob=r["prob"],
        var_24h=var,
        palavras_ditas=bool(r["palavras_ditas"]),
    )


def ativos(
    con: sqlite3.Connection, agora: datetime, tema: str | None = None, visto_desde_h: int = 6
) -> list[Linha]:
    """Mercados abertos vistos na coleta recente (descarta os que sumiram da busca)."""
    corte = iso(agora - timedelta(hours=visto_desde_h))
    # Prazo vencido com preço já decidido (≤2% ou ≥98%) = só aguardando resolução: sai das telas.
    # Prazo vencido com preço em aberto continua (ex.: eleição que foi para o 2º turno).
    sql = """SELECT * FROM mercados WHERE fechado = 0 AND ultimo_visto >= ?
             AND (fim IS NULL OR fim > ? OR (prob > 0.02 AND prob < 0.98))"""
    args: list = [corte, iso(agora)]
    if tema:
        sql += " AND tema = ?"
        args.append(tema)
    sql += " ORDER BY volume DESC"
    return [_linha(con, r, agora) for r in con.execute(sql, args).fetchall()]


def agrupar_por_evento(linhas: list[Linha]) -> list[list[Linha]]:
    """Mercados do mesmo evento (ex.: candidatos de uma eleição) viram um grupo."""
    grupos: dict[str, list[Linha]] = {}
    for linha in linhas:
        chave = linha.evento_id or linha.id
        grupos.setdefault(chave, []).append(linha)
    saida = list(grupos.values())
    for g in saida:
        g.sort(key=lambda x: x.prob or 0, reverse=True)
    saida.sort(key=lambda g: sum(x.volume for x in g), reverse=True)
    return saida
