"""O que cada movimento da Polymarket significa na bolsa: quem ganha (LONG) e quem perde (SHORT).

Junta três coisas:
- a hipótese de ativos.yaml (sentido de cada ativo quando a chance do tema sobe), agrupada por setor;
- a polaridade da pergunta (tradução): "Sim" contra o tema inverte a jogada;
- o efeito medido pela calibração, quando existe ("a cada +10 p.p., XLE −0,8%").
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from bot import formato as f
from bot.analise import calibracao
from bot.config import Config

MAX_SETORES = 3
MAX_TICKERS = 3


def nome(ticker: str) -> str:
    return ticker.removesuffix(".SA").lstrip("^")


@dataclass
class Jogada:
    longs: list[tuple[str, list[str]]] = field(default_factory=list)  # (setor, tickers)
    shorts: list[tuple[str, list[str]]] = field(default_factory=list)
    medidos: list[str] = field(default_factory=list)
    por_que: str = ""

    @property
    def vazia(self) -> bool:
        return not (self.longs or self.shorts or self.medidos)


def _por_setor(cfg: Config, tickers: list[str]) -> list[tuple[str, list[str]]]:
    grupos: dict[str, list[str]] = {}
    for t in tickers:
        setor = (cfg.ativos.get(t) or {}).get("setor") or "outros"
        grupos.setdefault(setor, []).append(nome(t))
    return [(s, ts[:MAX_TICKERS]) for s, ts in list(grupos.items())[:MAX_SETORES]]


def montar(
    con: sqlite3.Connection | None,
    cfg: Config,
    tema: str,
    direcao: int = 1,
    polaridade: int = 1,
    mercado_id: str | None = None,
) -> Jogada:
    """Jogada quando a chance anda na `direcao` (+1 subiu, −1 caiu)."""
    info_tema = cfg.temas.get(tema, {})
    leitura = info_tema.get("leitura") or {}
    efeito = direcao * polaridade  # +1: o evento do tema ficou mais provável
    j = Jogada(por_que=leitura.get("sobe" if efeito > 0 else "cai", "") if polaridade else "")
    if polaridade:
        longs, shorts = [], []
        for t, s in cfg.ativos_do_tema(tema).items():
            if not s or t not in cfg.ativos:
                continue
            (longs if s * efeito > 0 else shorts).append(t)
        j.longs, j.shorts = _por_setor(cfg, longs), _por_setor(cfg, shorts)
    if con is not None and mercado_id:
        t_min = cfg.regras.get("calibracao", {}).get("t_min", 3.3)
        for p in calibracao.confirmados(con, mercado_id, t_min)[:2]:
            efeito_pct = p["beta_10pp"] * direcao
            quando = (
                f"~{f.numero(p['defasagem_min'], 0)} min depois"
                if p["defasagem_min"] > 0
                else "ao mesmo tempo"
            )
            j.medidos.append(
                f"{'+' if direcao > 0 else '−'}10 p.p. → {nome(p['ativo'])} "
                f"{f.numero(efeito_pct, 1, sinal=True)}% ({quando})"
            )
    return j


def _lado(itens: list[tuple[str, list[str]]], setores: int = 2, tickers: int = 2) -> str:
    return " · ".join(f"{s} ({', '.join(ts[:tickers])})" for s, ts in itens[:setores])


def linhas(j: Jogada, compacta: bool = False) -> list[str]:
    """Texto da jogada. Compacta = uma linha só (para o resumo)."""
    if compacta:
        partes = []
        if j.longs:
            partes.append("🟢 LONG " + _lado(j.longs))
        if j.shorts:
            partes.append("🔴 SHORT " + _lado(j.shorts))
        return [" | ".join(partes)] if partes else []
    saida = []
    for setor, ts in j.longs:
        saida.append(f"🟢 LONG {setor}: {', '.join(ts)}")
    for setor, ts in j.shorts:
        saida.append(f"🔴 SHORT {setor}: {', '.join(ts)}")
    for m in j.medidos:
        saida.append(f"📏 Medido: {m}")
    return saida
