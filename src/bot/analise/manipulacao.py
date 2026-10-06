"""Módulo 5 — nota de risco de manipulação (🟢 baixo / 🟡 médio / 🔴 alto).

Nunca afirma "foi manipulado": é sempre "risco de manipulação". Critérios:
- concentração: 5 maiores carteiras ≥ 60% das cotas entre os 20 maiores detentores (aproximação:
  a Data API só devolve os 20 maiores por lado);
- divergência entre plataformas: Polymarket × Kalshi ≥ 5 p.p. na mesma pergunta;
- impacto por volume: movimento ≥ 3 p.p. em 1 h com menos de US$ 50 mil negociados, ou livro raso;
- reversão rápida: subiu (ou caiu) ≥ 5 p.p. e voltou em menos de 6 h;
- movimento sem notícia: ≥ 3 p.p. em 6 h sem pico de notícias no GDELT;
- mercados de palavras ditas: sempre 🔴 e nunca geram sinal.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from bot import formato as f
from bot.db import iso


@dataclass
class Nota:
    nota: str
    criterios: list[str] = field(default_factory=list)

    @property
    def texto(self) -> str:
        nome = {"🟢": "baixo", "🟡": "médio", "🔴": "alto"}[self.nota]
        base = f"{self.nota} {nome}"
        return base + (f" ({'; '.join(self.criterios)})" if self.criterios else "")


def concentracao(holders: list[dict]) -> float | None:
    """Parcela das 5 maiores carteiras entre os maiores detentores (somando os dois lados)."""
    por_carteira: dict[str, float] = {}
    for h in holders:
        try:
            por_carteira[h["proxyWallet"]] = por_carteira.get(h["proxyWallet"], 0.0) + float(
                h.get("amount") or 0
            )
        except (KeyError, TypeError, ValueError):
            continue
    total = sum(por_carteira.values())
    if total <= 0 or len(por_carteira) < 5:
        return None
    top5 = sum(sorted(por_carteira.values(), reverse=True)[:5])
    return top5 / total


def _serie(con: sqlite3.Connection, mercado_id: str, desde: datetime) -> list[sqlite3.Row]:
    return con.execute(
        """SELECT ts, valor, volume FROM series WHERE tipo='mercado' AND chave=? AND ts >= ? AND valor IS NOT NULL
           ORDER BY ts""",
        (mercado_id, iso(desde)),
    ).fetchall()


def avaliar(
    con: sqlite3.Connection,
    mercado: sqlite3.Row,
    agora: datetime,
    *,
    regras: dict,
    concentracao_top5: float | None = None,
    prob_kalshi: float | None = None,
    pico_noticias: float | None = None,
) -> Nota:
    r = regras.get("manipulacao", {})
    if mercado["palavras_ditas"]:
        return Nota("🔴", ["mercado de palavras ditas: quem fala decide"])
    criterios: list[str] = []
    if concentracao_top5 is not None and concentracao_top5 >= r.get("concentracao_top5", 0.6):
        criterios.append(f"5 carteiras com {f.pct(concentracao_top5, 0)} das cotas")
    p = mercado["prob"]
    if prob_kalshi is not None and p is not None and abs(p - prob_kalshi) * 100 >= r.get("divergencia_pp", 5):
        criterios.append(f"Kalshi diverge ({f.prob(prob_kalshi)} × {f.prob(p)})")

    serie = _serie(con, mercado["id"], agora - timedelta(hours=7))
    if len(serie) >= 2:
        a, b = serie[-2], serie[-1]
        dp = abs(b["valor"] - a["valor"]) * 100
        dvol = (b["volume"] or 0) - (a["volume"] or 0)
        if dp >= r.get("movimento_pp", 3) and 0 <= dvol < r.get("volume_baixo_usd", 50_000):
            criterios.append(f"{f.numero(dp, 1)} p.p. com só {f.volume(dvol)} negociados")
    if (mercado["liquidez"] or 0) < r.get("liquidez_rasa_usd", 20_000):
        criterios.append(f"livro raso ({f.volume(mercado['liquidez'] or 0)})")
    janela = [x for x in serie if x["ts"] >= iso(agora - timedelta(hours=6))]
    if len(janela) >= 3:
        inicio, fim = janela[0]["valor"], janela[-1]["valor"]
        extremo = max(janela, key=lambda x: abs(x["valor"] - inicio))["valor"]
        excursao = abs(extremo - inicio)
        if excursao * 100 >= r.get("reversao_pp", 5) and abs(fim - inicio) <= 0.3 * excursao:
            criterios.append(
                "subiu e voltou em menos de 6 h" if extremo > inicio else "caiu e voltou em menos de 6 h"
            )
        if (
            abs(fim - inicio) * 100 >= r.get("movimento_pp", 3)
            and pico_noticias is not None
            and pico_noticias < r.get("pico_noticias_min", 1.5)
        ):
            criterios.append("movimento sem pico de notícias (GDELT)")

    if len(criterios) >= 3 or (concentracao_top5 and prob_kalshi is not None and len(criterios) >= 2):
        nota = "🔴"
    elif criterios:
        nota = "🟡"
    else:
        nota = "🟢"
    return Nota(nota, criterios)


def gravar(con: sqlite3.Connection, mercado_id: str, nota: Nota, agora: datetime) -> None:
    con.execute(
        "INSERT OR REPLACE INTO manipulacao (mercado_id, ts, nota, detalhes) VALUES (?, ?, ?, ?)",
        (mercado_id, iso(agora), nota.nota, json.dumps(nota.criterios, ensure_ascii=False)),
    )
    con.commit()


def ler(con: sqlite3.Connection, mercado_id: str) -> Nota | None:
    r = con.execute("SELECT nota, detalhes FROM manipulacao WHERE mercado_id = ?", (mercado_id,)).fetchone()
    return Nota(r["nota"], json.loads(r["detalhes"] or "[]")) if r else None
