"""Posições do outro bot (pedroloopz/alerta-ema), para declarar nos posts do X.

O repositório é privado: precisa do Secret ALERTA_EMA_TOKEN (token fine-grained do GitHub,
somente leitura de "Contents" no alerta-ema). Sem ele, vale só o que você declarar por
/posicao no Telegram. Só ticker, lado, preço médio e data saem daqui; quantidade nunca.
"""

from __future__ import annotations

import json
import os

from bot.http import Http

REPO = "pedroloopz/alerta-ema"
ARQUIVOS = {"carteira.json": "EUA", "carteira_b3.json": "B3"}


def ler(http: Http, token: str | None = None, repo: str = REPO) -> dict[str, dict]:
    """{ticker_yahoo: {lado, preco, desde, origem}}. Levanta erro se o GitHub recusar."""
    token = token if token is not None else os.getenv("ALERTA_EMA_TOKEN", "")
    if not token:
        return {}
    saida: dict[str, dict] = {}
    for arquivo, bolsa in ARQUIVOS.items():
        resp = http.sessao.get(
            f"https://api.github.com/repos/{repo}/contents/{arquivo}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw+json"},
            timeout=20,
        )
        resp.raise_for_status()
        dados = json.loads(resp.text)
        saida.update(converter(dados, bolsa))
    return saida


def converter(dados: dict, bolsa: str) -> dict[str, dict]:
    posicoes = {}
    for ticker, info in (dados.get("ativos") or {}).items():
        if not isinstance(info, dict):
            continue
        if bolsa == "B3":
            qtd, preco, desde = info.get("qtd"), info.get("pm"), info.get("desde")
            yahoo = ticker if ticker.endswith(".SA") else f"{ticker}.SA"
        else:
            qtd, preco, desde = info.get("unidades"), info.get("preco_entrada"), info.get("data_entrada")
            yahoo = ticker
        if not qtd or float(qtd) <= 0:
            continue
        posicoes[yahoo] = {"lado": "comprado", "preco": preco, "desde": desde, "origem": "alerta-ema"}
    return posicoes
