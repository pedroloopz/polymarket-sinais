"""Módulo 13 — avaliação simulada de cada sinal em +1 h, +1 dia e +1 semana."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from bot.db import de_iso, iso

HORIZONTES = {"1h": timedelta(hours=1), "1d": timedelta(days=1), "1w": timedelta(weeks=1)}
# Tolerância para achar o preço: a coleta é horária e o fim de semana não tem pregão.
TOLERANCIA = {"1h": timedelta(hours=3), "1d": timedelta(days=3), "1w": timedelta(days=4)}


def retorno(sentido: int, entrada: float, saida: float, custo_pct: float) -> tuple[float, float]:
    bruto = sentido * (saida / entrada - 1)
    return bruto, bruto - custo_pct / 100


def _preco_apos(con: sqlite3.Connection, ativo: str, momento: datetime, tolerancia: timedelta):
    return con.execute(
        """SELECT valor, ts FROM series WHERE tipo='ativo' AND chave=? AND ts >= ? AND ts <= ?
           AND valor IS NOT NULL ORDER BY ts LIMIT 1""",
        (ativo, iso(momento), iso(momento + tolerancia)),
    ).fetchone()


def avaliar_pendentes(
    con: sqlite3.Connection, agora: datetime, custo_pct: float, horizontes: list[str] | None = None
) -> int:
    """Avalia o que já venceu e tem preço na série. Retorna quantas avaliações gravou."""
    horizontes = horizontes or list(HORIZONTES)
    feitas = 0
    for s in con.execute("SELECT * FROM sinais").fetchall():
        inicio = de_iso(s["ts"])
        for h in horizontes:
            momento = inicio + HORIZONTES[h]
            if momento > agora:
                continue
            ja = con.execute(
                "SELECT 1 FROM avaliacoes WHERE sinal_id=? AND horizonte=?", (s["id"], h)
            ).fetchone()
            if ja:
                continue
            linha = _preco_apos(con, s["ativo"], momento, TOLERANCIA[h])
            if not linha:
                continue
            bruto, liquido = retorno(s["sentido"], s["entrada"], linha["valor"], custo_pct)
            con.execute(
                """INSERT INTO avaliacoes (sinal_id, horizonte, ts, preco, retorno_bruto, retorno_liquido)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (s["id"], h, linha["ts"], linha["valor"], bruto, liquido),
            )
            feitas += 1
    con.commit()
    return feitas
