"""Estado rápido compartilhado com o Worker: Cloudflare KV via API REST.

O Worker (webhook do Telegram) grava a configuração feita por comando (/capital, /silencio…)
e lê o "painel" que as Actions publicam. Sem CLOUDFLARE_* configurados, o bot roda
normalmente só com os arquivos de config (o KV vira um no-op).
"""

from __future__ import annotations

import json
import os
from typing import Any

from bot.http import Http
from bot.logs import aviso, log

TITULO_NAMESPACE = "polymarket-sinais-estado"  # mesmo nome usado no deploy do Worker
API = "https://api.cloudflare.com/client/v4"
_log = log("kv")


class KV:
    def __init__(self, http: Http | None = None, token: str | None = None, conta: str | None = None) -> None:
        self.token = token if token is not None else os.getenv("CLOUDFLARE_API_TOKEN", "")
        self.conta = conta if conta is not None else os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        self.http = http or Http(tentativas=3)
        self._namespace: str | None = None

    @property
    def ativo(self) -> bool:
        return bool(self.token and self.conta)

    def _cab(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def namespace(self) -> str | None:
        if self._namespace or not self.ativo:
            return self._namespace
        url = f"{API}/accounts/{self.conta}/storage/kv/namespaces"
        resp = self.http.sessao.get(url, headers=self._cab(), params={"per_page": 100}, timeout=20)
        resp.raise_for_status()
        for ns in resp.json().get("result", []):
            if ns.get("title") == TITULO_NAMESPACE:
                self._namespace = ns["id"]
                break
        if not self._namespace:
            aviso(
                _log,
                "namespace KV não encontrado — rode o deploy do Worker primeiro",
                titulo=TITULO_NAMESPACE,
            )
        return self._namespace

    def ler(self, chave: str, padrao: Any = None) -> Any:
        try:
            ns = self.namespace()
            if not ns:
                return padrao
            url = f"{API}/accounts/{self.conta}/storage/kv/namespaces/{ns}/values/{chave}"
            resp = self.http.sessao.get(url, headers=self._cab(), timeout=20)
            if resp.status_code == 404:
                return padrao
            resp.raise_for_status()
            return json.loads(resp.text)
        except Exception as erro:  # rede, HTTP, JSON inválido: o bot segue com o padrão
            aviso(_log, "falha ao ler KV", chave=chave, erro=str(erro))
            return padrao

    def gravar(self, chave: str, valor: Any) -> bool:
        try:
            ns = self.namespace()
            if not ns:
                return False
            url = f"{API}/accounts/{self.conta}/storage/kv/namespaces/{ns}/values/{chave}"
            self.http.put(url, json.dumps(valor, ensure_ascii=False).encode(), headers=self._cab())
            return True
        except Exception as erro:
            aviso(_log, "falha ao gravar KV", chave=chave, erro=str(erro))
            return False
