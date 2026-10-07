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
    # Textos já em português quando há tradução (pergunta/item/evento_titulo); o original fica aqui.
    original: str = ""
    polaridade: int = 1  # +1: "Sim" a favor do tema; −1: contra; 0: indefinido


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
    chaves = r.keys()

    def pt(campo: str, original: str | None) -> str:
        return (r[campo] if campo in chaves and r[campo] else None) or original or ""

    pol = r["polaridade"] if "polaridade" in chaves and r["polaridade"] is not None else 1
    return Linha(
        id=r["id"],
        tema=r["tema"],
        pergunta=pt("pergunta_pt", r["pergunta"]),
        item=pt("item_pt", r["item"]),
        evento_id=r["evento_id"] or "",
        evento_titulo=pt("titulo_pt", r["evento_titulo"]),
        link=f"https://polymarket.com/event/{slug}" if slug else "",
        fim=de_iso(r["fim"]),
        criado_em=de_iso(r["criado_em"]),
        volume=r["volume"] or 0.0,
        prob=r["prob"],
        var_24h=var,
        palavras_ditas=bool(r["palavras_ditas"]),
        original=r["pergunta"],
        polaridade=int(pol),
    )


def ativos(
    con: sqlite3.Connection, agora: datetime, tema: str | None = None, visto_desde_h: int = 6
) -> list[Linha]:
    """Mercados abertos vistos na coleta recente (descarta os que sumiram da busca)."""
    corte = iso(agora - timedelta(hours=visto_desde_h))
    # Prazo vencido com preço já decidido (≤2% ou ≥98%) = só aguardando resolução: sai das telas.
    # Prazo vencido com preço em aberto continua (ex.: eleição que foi para o 2º turno).
    sql = """SELECT m.*, t.pergunta_pt, t.item_pt, t.titulo_pt, t.polaridade FROM mercados m
             LEFT JOIN traducoes t ON t.mercado_id = m.id
             WHERE m.fechado = 0 AND m.ultimo_visto >= ?
             AND (m.fim IS NULL OR m.fim > ? OR (m.prob > 0.02 AND m.prob < 0.98))"""
    args: list = [corte, iso(agora)]
    if tema:
        sql += " AND m.tema = ?"
        args.append(tema)
    sql += " ORDER BY m.volume DESC"
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
