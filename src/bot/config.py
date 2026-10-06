"""Carrega config/*.yaml e aplica por cima o que foi ajustado pelo Telegram (KV "config")."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parents[2]
PASTA_CONFIG = RAIZ / "config"


def _ler(nome: str, pasta: Path) -> dict:
    with open(pasta / nome, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def mesclar(base: dict, por_cima: dict) -> dict:
    """Mescla recursiva: valores de `por_cima` vencem; dicts são combinados."""
    saida = copy.deepcopy(base)
    for chave, valor in (por_cima or {}).items():
        if isinstance(valor, dict) and isinstance(saida.get(chave), dict):
            saida[chave] = mesclar(saida[chave], valor)
        else:
            saida[chave] = valor
    return saida


@dataclass
class Config:
    temas: dict[str, dict]
    empresas_cripto: dict[str, dict]
    ativos: dict[str, dict]
    indicadores: dict[str, dict]
    pregoes: dict[str, dict]
    regras: dict[str, Any]
    telegram: dict[str, Any] = field(default_factory=dict)

    def temas_ligados(self) -> dict[str, dict]:
        return {k: v for k, v in self.temas.items() if v.get("ligado", True)}

    def todos_tickers(self) -> list[str]:
        return list(self.ativos) + list(self.indicadores)

    def ativos_do_tema(self, tema: str) -> dict[str, int]:
        saida = {}
        for ticker, info in {**self.ativos, **self.indicadores}.items():
            sentido = (info.get("temas") or {}).get(tema)
            if sentido is not None:
                saida[ticker] = sentido
        return saida


def carregar(ajustes_telegram: dict | None = None, pasta: Path = PASTA_CONFIG) -> Config:
    """`ajustes_telegram` é o JSON salvo pelo Worker no KV (chave "config")."""
    temas = _ler("temas.yaml", pasta)
    ativos = _ler("ativos.yaml", pasta)
    regras = _ler("regras.yaml", pasta)
    ajustes = ajustes_telegram or {}

    regras = mesclar(regras, ajustes.get("regras", {}))
    temas_cfg = copy.deepcopy(temas.get("temas", {}))
    for tema in ajustes.get("temas_desligados", []) or []:
        if tema in temas_cfg:
            temas_cfg[tema]["ligado"] = False

    return Config(
        temas=temas_cfg,
        empresas_cripto=temas.get("empresas_cripto", {}),
        ativos=ativos.get("ativos", {}),
        indicadores=ativos.get("indicadores", {}),
        pregoes=ativos.get("pregoes", {}),
        regras=regras,
        telegram=ajustes,
    )
