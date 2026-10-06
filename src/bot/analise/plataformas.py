"""Polymarket × Kalshi: acha a mesma pergunta nas duas plataformas e guarda a probabilidade da Kalshi.

Casamento conservador: palavras em comum (Jaccard) ≥ 0,45 e prazos a até 3 dias um do outro.
Na dúvida, não casa: um par errado geraria divergência falsa.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from bot.coleta.kalshi import MercadoKalshi, similaridade
from bot.db import de_iso, iso


def casar(
    con: sqlite3.Connection,
    kalshi: list[MercadoKalshi],
    agora: datetime,
    volume_min: float,
    similaridade_min: float = 0.45,
) -> int:
    mercados = con.execute(
        "SELECT * FROM mercados WHERE fechado = 0 AND volume >= ? AND ultimo_visto >= ?",
        (volume_min, iso(agora - timedelta(hours=6))),
    ).fetchall()
    pares = 0
    for m in mercados:
        texto = f"{m['evento_titulo'] or ''} {m['pergunta']} {m['item'] or ''}"
        fim = de_iso(m["fim"])
        melhor, nota = None, 0.0
        for k in kalshi:
            if k.prob is None:
                continue
            if fim and k.fim and abs((fim - k.fim).total_seconds()) > 3 * 86400:
                continue
            s = similaridade(texto, k.titulo)
            if s > nota:
                melhor, nota = k, s
        if melhor and nota >= similaridade_min:
            con.execute(
                """INSERT OR REPLACE INTO kalshi_pares (mercado_id, ticker, titulo, similaridade, prob, ts)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (m["id"], melhor.ticker, melhor.titulo, nota, melhor.prob, iso(agora)),
            )
            pares += 1
    con.commit()
    return pares


def prob_kalshi(con: sqlite3.Connection, mercado_id: str, agora: datetime) -> float | None:
    r = con.execute(
        "SELECT prob FROM kalshi_pares WHERE mercado_id = ? AND ts >= ?",
        (mercado_id, iso(agora - timedelta(hours=3))),
    ).fetchone()
    return r["prob"] if r else None
