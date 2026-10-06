"""Cliente HTTP com retry, backoff exponencial, respeito a Retry-After e cache por execução."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import requests

from bot.logs import aviso, log

_log = log("http")
REPETIR_STATUS = {429, 500, 502, 503, 504}
_TOKEN_TELEGRAM = re.compile(r"bot\d+:[A-Za-z0-9_-]+")


def seguro(texto: str) -> str:
    """Remove o token do Telegram de URLs e mensagens antes de logar."""
    return _TOKEN_TELEGRAM.sub("bot***", texto)


class ErroHttp(RuntimeError):
    pass


class Http:
    def __init__(
        self,
        tentativas: int = 4,
        espera_base: float = 2.0,
        timeout: float = 20.0,
        pausa: float = 0.0,
        sessao: requests.Session | None = None,
    ) -> None:
        self.tentativas = tentativas
        self.espera_base = espera_base
        self.timeout = timeout
        self.pausa = pausa
        self.sessao = sessao or requests.Session()
        self.sessao.headers.setdefault("User-Agent", "polymarket-sinais/0.1 (somente leitura)")
        self._cache: dict[str, Any] = {}

    def _pedir(self, metodo: str, url: str, **kw) -> requests.Response:
        ultimo: Exception | None = None
        for tentativa in range(self.tentativas):
            if self.pausa:
                time.sleep(self.pausa)
            try:
                resp = self.sessao.request(metodo, url, timeout=self.timeout, **kw)
            except requests.RequestException as erro:
                ultimo = ErroHttp(seguro(str(erro)))
            else:
                if resp.status_code not in REPETIR_STATUS:
                    if resp.status_code >= 400:
                        raise ErroHttp(seguro(f"{metodo} {url} → HTTP {resp.status_code}: {resp.text[:200]}"))
                    return resp
                ultimo = ErroHttp(f"HTTP {resp.status_code}")
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    time.sleep(min(int(retry_after), 60))
                    continue
            espera = self.espera_base * (2**tentativa)
            aviso(
                _log,
                "repetindo requisição",
                url=seguro(url),
                tentativa=tentativa + 1,
                espera_s=espera,
                erro=str(ultimo),
            )
            time.sleep(espera)
        raise ErroHttp(seguro(f"{metodo} {url} falhou após {self.tentativas} tentativas: {ultimo}"))

    def get_json(self, url: str, params: dict | None = None, cache: bool = True) -> Any:
        chave = url + "?" + json.dumps(params or {}, sort_keys=True)
        if cache and chave in self._cache:
            return self._cache[chave]
        dados = self._pedir("GET", url, params=params).json()
        if cache:
            self._cache[chave] = dados
        return dados

    def post_json(self, url: str, corpo: Any, **kw) -> Any:
        resp = self._pedir("POST", url, json=corpo, **kw)
        return resp.json() if resp.content else None

    def put(self, url: str, dados: str | bytes, **kw) -> requests.Response:
        return self._pedir("PUT", url, data=dados, **kw)
