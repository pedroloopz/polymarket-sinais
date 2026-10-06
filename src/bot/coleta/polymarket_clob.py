"""Polymarket CLOB API — midpoint e histórico de preços (somente leitura, sem chave).

Endpoints (caminhos conferidos no cliente oficial py-clob-client e na documentação):
- POST https://clob.polymarket.com/midpoints   corpo: [{"token_id": "..."}]  → {"<token>": "0.53"}
- GET  https://clob.polymarket.com/midpoint?token_id=...                    → {"mid": "0.53"}
- GET  https://clob.polymarket.com/prices-history?market=<token>&interval=1d&fidelity=1
Usamos sempre o midpoint (média entre compra e venda), nunca o último negócio isolado.
"""

from __future__ import annotations

from bot.http import ErroHttp, Http
from bot.logs import aviso, log

BASE = "https://clob.polymarket.com"
_log = log("clob")


class Clob:
    def __init__(self, http: Http) -> None:
        self.http = http

    def midpoints(self, tokens: list[str], lote: int = 50) -> dict[str, float]:
        saida: dict[str, float] = {}
        unicos = list(dict.fromkeys(t for t in tokens if t))
        for i in range(0, len(unicos), lote):
            parte = unicos[i : i + lote]
            try:
                dados = self.http.post_json(f"{BASE}/midpoints", [{"token_id": t} for t in parte]) or {}
            except ErroHttp as erro:
                aviso(_log, "lote de midpoints falhou; tentando um a um", erro=str(erro))
                dados = {}
                for t in parte:
                    try:
                        dados[t] = (
                            self.http.get_json(f"{BASE}/midpoint", {"token_id": t}, cache=False) or {}
                        ).get("mid")
                    except ErroHttp:
                        continue
            for token, valor in dados.items():
                try:
                    saida[str(token)] = float(valor)
                except (TypeError, ValueError):
                    continue
        return saida

    def historico(
        self, token: str, intervalo: str = "1d", fidelidade_min: int = 1
    ) -> list[tuple[int, float]]:
        """Lista de (timestamp unix, preço) do período `intervalo` (1h, 6h, 1d, 1w, max)."""
        dados = (
            self.http.get_json(
                f"{BASE}/prices-history",
                params={"market": token, "interval": intervalo, "fidelity": fidelidade_min},
            )
            or {}
        )
        return _pontos(dados)

    def historico_periodo(
        self, token: str, inicio: int, fim: int, fidelidade_min: int = 5, bloco_dias: int = 5
    ) -> list[tuple[int, float]]:
        """Histórico entre dois timestamps unix, pedido em blocos (startTs/endTs)."""
        pontos: dict[int, float] = {}
        passo = bloco_dias * 86400
        for a in range(inicio, fim, passo):
            dados = (
                self.http.get_json(
                    f"{BASE}/prices-history",
                    params={
                        "market": token,
                        "startTs": a,
                        "endTs": min(a + passo, fim),
                        "fidelity": fidelidade_min,
                    },
                )
                or {}
            )
            pontos.update(dict(_pontos(dados)))
        return sorted(pontos.items())


def _pontos(dados: dict) -> list[tuple[int, float]]:
    return [(int(p["t"]), float(p["p"])) for p in dados.get("history", []) if "t" in p and "p" in p]
