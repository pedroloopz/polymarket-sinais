"""Polymarket Gamma API — descoberta de eventos e mercados (somente leitura, sem chave).

Endpoints usados (conferidos na documentação oficial em 06/10/2026):
- GET https://gamma-api.polymarket.com/public-search?q=&limit_per_type=&events_status=active
- GET https://gamma-api.polymarket.com/events/{id}   (quando a busca não traz os mercados do evento)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from bot.db import de_iso
from bot.http import Http

BASE = "https://gamma-api.polymarket.com"


@dataclass
class Mercado:
    id: str
    pergunta: str
    slug: str
    evento_id: str
    evento_titulo: str
    evento_slug: str
    item: str
    token_sim: str | None
    fim: datetime | None
    criado_em: datetime | None
    volume: float
    liquidez: float
    prob_gamma: float | None
    bid: float | None
    ask: float | None
    var_24h: float | None
    ativo: bool
    fechado: bool

    @property
    def link(self) -> str:
        return f"https://polymarket.com/event/{self.evento_slug or self.slug}"


def _lista(valor) -> list:
    """A Gamma devolve outcomes/outcomePrices/clobTokenIds como string JSON."""
    if valor is None:
        return []
    if isinstance(valor, list):
        return valor
    try:
        dados = json.loads(valor)
        return dados if isinstance(dados, list) else []
    except (TypeError, ValueError):
        return []


def _float(valor) -> float | None:
    try:
        return None if valor is None or valor == "" else float(valor)
    except (TypeError, ValueError):
        return None


def parse_mercado(m: dict, evento: dict | None = None) -> Mercado | None:
    evento = evento or {}
    tokens = _lista(m.get("clobTokenIds"))
    resultados = [str(x).strip().lower() for x in _lista(m.get("outcomes"))]
    precos = [_float(x) for x in _lista(m.get("outcomePrices"))]
    i_sim = resultados.index("yes") if "yes" in resultados else 0
    pergunta = m.get("question") or m.get("title") or ""
    if not m.get("id") or not pergunta:
        return None
    return Mercado(
        id=str(m["id"]),
        pergunta=pergunta,
        slug=m.get("slug") or "",
        evento_id=str(evento.get("id") or ""),
        evento_titulo=evento.get("title") or "",
        evento_slug=evento.get("slug") or "",
        item=m.get("groupItemTitle") or "",
        token_sim=str(tokens[i_sim]) if len(tokens) > i_sim else None,
        fim=de_iso(m.get("endDate") or evento.get("endDate")),
        criado_em=de_iso(m.get("createdAt") or m.get("startDate")),
        volume=_float(m.get("volumeNum")) or _float(m.get("volume")) or 0.0,
        liquidez=_float(m.get("liquidityNum")) or _float(m.get("liquidity")) or 0.0,
        prob_gamma=precos[i_sim] if len(precos) > i_sim else None,
        bid=_float(m.get("bestBid")),
        ask=_float(m.get("bestAsk")),
        var_24h=_float(m.get("oneDayPriceChange")),
        ativo=bool(m.get("active", True)),
        fechado=bool(m.get("closed", False)),
    )


def _contem(texto: str, termos: list[str]) -> bool:
    texto = texto.lower()
    return any(re.search(rf"\b{re.escape(t.lower())}\b", texto) for t in termos)


def combina_tema(mercado: Mercado, tema: dict) -> bool:
    texto = f"{mercado.pergunta} {mercado.evento_titulo} {mercado.item}"
    incluir = tema.get("incluir") or []
    if incluir and not _contem(texto, incluir):
        return False
    return not _contem(texto, tema.get("excluir") or [])


def e_palavras_ditas(mercado: Mercado, tema: dict) -> bool:
    termos = tema.get("palavras_ditas") or []
    return bool(termos) and _contem(mercado.pergunta, termos)


class Gamma:
    def __init__(self, http: Http) -> None:
        self.http = http

    def buscar_eventos(self, consulta: str, limite: int = 20) -> list[dict]:
        dados = self.http.get_json(
            f"{BASE}/public-search",
            params={"q": consulta, "limit_per_type": limite, "events_status": "active"},
        )
        return (dados or {}).get("events") or []

    def evento(self, evento_id: str) -> dict:
        return self.http.get_json(f"{BASE}/events/{evento_id}") or {}

    def mercados_do_tema(
        self, tema: dict, limite_busca: int = 20, maximo: int = 40, ignorar_fechados: bool = True
    ) -> list[Mercado]:
        vistos: dict[str, Mercado] = {}
        for consulta in tema.get("buscas") or []:
            for ev in self.buscar_eventos(consulta, limite_busca):
                brutos = ev.get("markets")
                if brutos is None and ev.get("id"):
                    brutos = self.evento(str(ev["id"])).get("markets") or []
                for bruto in brutos or []:
                    m = parse_mercado(bruto, ev)
                    if not m or m.id in vistos:
                        continue
                    if ignorar_fechados and (m.fechado or not m.ativo):
                        continue
                    if combina_tema(m, tema):
                        vistos[m.id] = m
        ordenados = sorted(vistos.values(), key=lambda m: m.volume, reverse=True)
        return ordenados[:maximo]
