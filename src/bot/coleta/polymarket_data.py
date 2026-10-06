"""Polymarket Data API — posições e negociações por carteira (somente leitura, sem chave).

Endpoints (raiz, conferidos em guias da documentação oficial em 06/10/2026):
- GET https://data-api.polymarket.com/holders?market=<conditionId>&limit=20  (máx. 20 por token)
- GET https://data-api.polymarket.com/positions?user=<carteira>&sizeThreshold=1&limit=500
- GET https://data-api.polymarket.com/closed-positions?user=<carteira>&limit=50&offset=0
Limites publicados: 1.000 req/10 s no total; 150 req/10 s em /positions e /closed-positions.
"""

from __future__ import annotations

from bot.http import Http

BASE = "https://data-api.polymarket.com"


class DataApi:
    def __init__(self, http: Http) -> None:
        self.http = http

    def holders(self, condicao: str, limite: int = 20) -> list[dict]:
        """Maiores detentores de cada lado (token) do mercado: [{proxyWallet, amount, outcomeIndex}]."""
        dados = self.http.get_json(f"{BASE}/holders", {"market": condicao, "limit": limite}) or []
        saida = []
        for bloco in dados if isinstance(dados, list) else []:
            for h in bloco.get("holders") or []:
                saida.append(h)
        return saida

    def posicoes(self, carteira: str) -> list[dict]:
        return (
            self.http.get_json(
                f"{BASE}/positions", {"user": carteira, "sizeThreshold": 1, "limit": 500}, cache=False
            )
            or []
        )

    def posicoes_encerradas(self, carteira: str, maximo: int = 200) -> list[dict]:
        saida: list[dict] = []
        for offset in range(0, maximo, 50):
            lote = (
                self.http.get_json(
                    f"{BASE}/closed-positions", {"user": carteira, "limit": 50, "offset": offset}
                )
                or []
            )
            saida.extend(lote)
            if len(lote) < 50:
                break
        return saida
