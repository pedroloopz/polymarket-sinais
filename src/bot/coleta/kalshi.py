"""Kalshi — dados públicos de mercado (sem chave), para comparar com a Polymarket.

Endpoint (conferido no SDK oficial kalshi_python_sync 3.2.0 e no guia "quick start market data"):
- GET https://api.elections.kalshi.com/trade-api/v2/events?status=open&with_nested_markets=true&limit=200&cursor=
Preços: yes_bid/yes_ask em centavos; versões novas também trazem *_dollars ("0.5300").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from bot.db import de_iso
from bot.http import Http

BASE = "https://api.elections.kalshi.com/trade-api/v2"
PALAVRAS_VAZIAS = {
    "will", "the", "a", "an", "of", "in", "on", "by", "to", "be", "before", "after", "and", "or", "for",
    "at", "is", "than", "end", "yes", "no", "this", "2026", "2027", "who", "what", "which", "how", "any",
}  # fmt: skip


@dataclass
class MercadoKalshi:
    ticker: str
    titulo: str
    prob: float | None
    fim: datetime | None
    volume: float


def _preco(m: dict, campo: str) -> float | None:
    dolares = m.get(f"{campo}_dollars")
    if dolares not in (None, ""):
        try:
            return float(dolares)
        except ValueError:
            pass
    centavos = m.get(campo)
    return centavos / 100 if isinstance(centavos, int | float) else None


def parse(m: dict, evento: dict) -> MercadoKalshi:
    bid, ask = _preco(m, "yes_bid"), _preco(m, "yes_ask")
    prob = (bid + ask) / 2 if bid is not None and ask is not None and ask > 0 else _preco(m, "last_price")
    titulo = " ".join(
        x for x in [evento.get("title"), m.get("title"), m.get("yes_sub_title") or m.get("subtitle")] if x
    )
    return MercadoKalshi(
        ticker=m.get("ticker", ""),
        titulo=titulo,
        prob=prob,
        fim=de_iso(m.get("close_time") or m.get("expiration_time")),
        volume=float(m.get("volume") or 0),
    )


def palavras(texto: str) -> set[str]:
    return {p for p in re.findall(r"[a-z0-9]+", texto.lower()) if p not in PALAVRAS_VAZIAS and len(p) > 2}


def similaridade(a: str, b: str) -> float:
    pa, pb = palavras(a), palavras(b)
    return len(pa & pb) / len(pa | pb) if pa and pb else 0.0


class Kalshi:
    def __init__(self, http: Http) -> None:
        self.http = http

    def mercados_abertos(self, paginas: int = 15) -> list[MercadoKalshi]:
        saida: list[MercadoKalshi] = []
        cursor = None
        for _ in range(paginas):
            params = {"status": "open", "with_nested_markets": "true", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            dados = self.http.get_json(f"{BASE}/events", params) or {}
            for ev in dados.get("events") or []:
                for m in ev.get("markets") or []:
                    saida.append(parse(m, ev))
            cursor = dados.get("cursor")
            if not cursor:
                break
        return saida
