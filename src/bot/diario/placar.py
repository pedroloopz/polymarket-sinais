"""Módulo 13 — placar do diário simulado (a versão semanal completa vem na Fase 2)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from bot import formato as f
from bot.db import de_iso, iso

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


def _estat(rets: list[float]) -> str:
    if not rets:
        return "—"
    ganhos = [r for r in rets if r > 0]
    perdas = [r for r in rets if r <= 0]
    acerto = len(ganhos) / len(rets)
    texto = f"{len(rets)} | {f.pct(acerto, 0)} acerto | médio {f.pct(sum(rets) / len(rets), 2, sinal=True)}"
    if ganhos and perdas:
        razao = (sum(ganhos) / len(ganhos)) / abs(sum(perdas) / len(perdas)) if sum(perdas) else None
        if razao:
            texto += f" | ganho/perda {f.numero(razao, 1)}"
    return texto


def semanal(
    con: sqlite3.Connection,
    agora: datetime,
    minimo_sinais: int = 30,
    minimo_semanas: int = 8,
    horizonte: str = "1d",
) -> str:
    """Placar da semana (módulo 13): acerto, ganho médio, ganho/perda, pior sequência e quebras."""
    linhas = con.execute(
        """SELECT s.ts, s.tema, s.semaforo, s.manipulacao, s.acionavel, a.retorno_liquido AS r
           FROM avaliacoes a JOIN sinais s ON s.id = a.sinal_id
           WHERE a.horizonte = ? ORDER BY s.ts""",
        (horizonte,),
    ).fetchall()
    inicio_semana = agora - timedelta(days=7)
    semana = [x for x in linhas if de_iso(x["ts"]) >= inicio_semana]
    p = calcular(con, agora, horizonte)
    partes = [
        f"📒 <b>Placar da semana</b> ({f.data(inicio_semana)} a {f.data(agora)}) — horizonte 1 dia, com custo"
    ]
    partes.append(f"Semana: {_estat([x['r'] for x in semana])}")
    partes.append(f"Desde o início: {_estat([x['r'] for x in linhas])} | pior sequência: {p.pior_sequencia}")
    fechados = con.execute(
        """SELECT status, resultado FROM sinais WHERE acionavel = 1 AND fechado_em >= ?""",
        (iso(inicio_semana),),
    ).fetchall()
    if fechados:
        por_status: dict[str, int] = {}
        for r in fechados:
            por_status[r["status"]] = por_status.get(r["status"], 0) + 1
        resumo = ", ".join(f"{k}: {v}" for k, v in sorted(por_status.items()))
        partes.append(f"Acionáveis encerrados: {_estat([r['resultado'] for r in fechados])} ({resumo})")

    def quebra(titulo: str, chave: str, rotulo=lambda v: v or "—"):
        grupos: dict[str, list[float]] = {}
        for x in linhas:
            grupos.setdefault(str(rotulo(x[chave])), []).append(x["r"])
        if grupos:
            partes.append(f"\n<b>Por {titulo}</b>")
            partes.extend(f"• {k}: {_estat(v)}" for k, v in sorted(grupos.items()))

    quebra("tema", "tema")
    quebra("semáforo", "semaforo")
    quebra("nota de manipulação", "manipulacao")
    quebra("tipo", "acionavel", lambda v: "acionável" if v else "informativo")
    if amostra_insuficiente(p, minimo_sinais, minimo_semanas):
        partes.append(f"\n{AVISO_AMOSTRA}")
    return "\n".join(partes)
