"""Fixtures dos testes: nada acessa a rede.

As respostas em tests/fixtures/ seguem o formato documentado das APIs da Polymarket
(Gamma /public-search, /events/{id}; CLOB /midpoints).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bot import db
from bot.coleta.precos import Cotacao
from bot.config import carregar

FIX = Path(__file__).parent / "fixtures"
AGORA = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def carregar_fixture(nome: str):
    return json.loads((FIX / nome).read_text(encoding="utf-8"))


class FakeHttp:
    """Imita bot.http.Http devolvendo fixtures por URL/consulta."""

    def __init__(self, falhar_clob: bool = False):
        self.chamadas: list[tuple[str, str, object]] = []
        self.falhar_clob = falhar_clob

    def get_json(self, url, params=None, cache=True):
        self.chamadas.append(("GET", url, params))
        if url.endswith("/public-search"):
            q = (params or {}).get("q", "").lower()
            if "iran" in q or "hormuz" in q:
                return carregar_fixture("gamma_busca_ira.json")
            if "brazil" in q:
                return carregar_fixture("gamma_busca_brasil.json")
            return {"events": []}
        if url.endswith("/events/ev11"):
            return carregar_fixture("gamma_evento_ev11.json")
        raise AssertionError(f"URL inesperada: {url}")

    def post_json(self, url, corpo, **kw):
        self.chamadas.append(("POST", url, corpo))
        if url.endswith("/midpoints"):
            if self.falhar_clob:
                from bot.http import ErroHttp

                raise ErroHttp("simulado")
            mids = carregar_fixture("clob_midpoints.json")
            return {c["token_id"]: mids[c["token_id"]] for c in corpo if c["token_id"] in mids}
        if "api.telegram.org" in url:
            return {"ok": True}
        raise AssertionError(f"URL inesperada: {url}")


def cotacoes_falsas(tickers):
    return {t: Cotacao(t, 100.0 + i, AGORA) for i, t in enumerate(tickers)}


@pytest.fixture
def cfg():
    return carregar()


@pytest.fixture
def con(tmp_path):
    c = db.conectar(tmp_path / "teste.sqlite")
    yield c
    c.close()


@pytest.fixture
def http():
    return FakeHttp()
