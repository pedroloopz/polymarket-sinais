"""Módulo 13 — placar do diário simulado (a versão semanal completa vem na Fase 2)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from bot import formato as f
from bot.db import de_iso

AVISO_AMOSTRA = "⚠️ Amostra insuficiente — use só como observação"


@dataclass
class Placar:
    sinais: int
    avaliados: int
    acertos: int
    ganho_medio: float | None
    semanas: float
    pior_sequencia: int

    @property
    def taxa_acerto(self) -> float | None:
        return self.acertos / self.avaliados if self.avaliados else None


def calcular(con: sqlite3.Connection, agora: datetime, horizonte: str = "1d") -> Placar:
    total = con.execute("SELECT COUNT(*) FROM sinais").fetchone()[0]
    primeiro = con.execute("SELECT MIN(ts) FROM sinais").fetchone()[0]
    semanas = (agora - de_iso(primeiro)).days / 7 if primeiro else 0.0
    linhas = con.execute(
        """SELECT a.retorno_liquido FROM avaliacoes a JOIN sinais s ON s.id = a.sinal_id
           WHERE a.horizonte = ? ORDER BY s.ts""",
        (horizonte,),
    ).fetchall()
    rets = [r[0] for r in linhas]
    pior = atual = 0
    for r in rets:
        atual = atual + 1 if r <= 0 else 0
        pior = max(pior, atual)
    return Placar(
        sinais=total,
        avaliados=len(rets),
        acertos=sum(1 for r in rets if r > 0),
        ganho_medio=sum(rets) / len(rets) if rets else None,
        semanas=semanas,
        pior_sequencia=pior,
    )


def amostra_insuficiente(p: Placar, minimo_sinais: int, minimo_semanas: int) -> bool:
    return p.avaliados < minimo_sinais or p.semanas < minimo_semanas


def linha_resumo(p: Placar, minimo_sinais: int = 30, minimo_semanas: int = 8) -> str:
    rotulo = " (amostra insuficiente)" if amostra_insuficiente(p, minimo_sinais, minimo_semanas) else ""
    if not p.avaliados:
        return f"📒 Placar{rotulo}: {p.sinais} sinais | nenhum avaliado ainda"
    return f"📒 Placar{rotulo}: {p.sinais} sinais | {f.pct(p.taxa_acerto, 0)} acerto"


def texto(p: Placar, minimo_sinais: int = 30, minimo_semanas: int = 8) -> str:
    partes = ["📒 <b>Placar do diário simulado</b> (horizonte 1 dia, já com custo)"]
    partes.append(f"Sinais: {p.sinais} | avaliados: {p.avaliados}")
    if p.avaliados:
        partes.append(
            f"Acerto: {f.pct(p.taxa_acerto, 0)} | ganho médio: {f.pct(p.ganho_medio, 2, sinal=True)}"
        )
        partes.append(f"Pior sequência de perdas: {p.pior_sequencia}")
    if amostra_insuficiente(p, minimo_sinais, minimo_semanas):
        partes.append(AVISO_AMOSTRA)
    return "\n".join(partes)
