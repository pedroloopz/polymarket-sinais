"""Módulo 13 — registro de todo sinal emitido (operação simulada)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime

from bot.db import iso


@dataclass
class Sinal:
    ts: datetime
    tema: str
    ativo: str
    sentido: int  # +1 long, -1 short
    entrada: float
    mercado_id: str | None = None
    stop: float | None = None
    alvo: float | None = None
    semaforo: str | None = None  # 🟢 🟡 🔴
    manipulacao: str | None = None
    urgencia: str = "🔔"
    acionavel: bool = False
    latencia_s: float | None = None
    detalhes: dict = field(default_factory=dict)
    # Fase 2
    confianca: str | None = None
    base_ts: datetime | None = None
    p_base: float | None = None
    p_sinal: float | None = None
    z: float | None = None
    alvo_parcial: float | None = None
    stop_tempo: datetime | None = None
    esperado: float | None = None
    realizado: float | None = None
    defasagem_min: float | None = None
    beta_10pp: float | None = None
    quantidade: float | None = None


COLUNAS = [
    "ts", "tema", "mercado_id", "ativo", "sentido", "entrada", "stop", "alvo", "semaforo", "manipulacao",
    "urgencia", "acionavel", "latencia_s", "detalhes", "confianca", "base_ts", "p_base", "p_sinal", "z",
    "alvo_parcial", "stop_tempo", "esperado", "realizado", "defasagem_min", "beta_10pp", "quantidade", "status",
]  # fmt: skip


def registrar(con: sqlite3.Connection, s: Sinal) -> int:
    if s.sentido not in (1, -1):
        raise ValueError("sentido deve ser +1 (long) ou -1 (short)")
    valores = [
        iso(s.ts), s.tema, s.mercado_id, s.ativo, s.sentido, s.entrada, s.stop, s.alvo, s.semaforo,
        s.manipulacao, s.urgencia, int(s.acionavel), s.latencia_s,
        json.dumps(s.detalhes or {}, ensure_ascii=False), s.confianca,
        iso(s.base_ts) if s.base_ts else None, s.p_base, s.p_sinal, s.z, s.alvo_parcial,
        iso(s.stop_tempo) if s.stop_tempo else None, s.esperado, s.realizado, s.defasagem_min, s.beta_10pp,
        s.quantidade, "aberto",
    ]  # fmt: skip
    cur = con.execute(
        f"INSERT INTO sinais ({', '.join(COLUNAS)}) VALUES ({', '.join('?' * len(COLUNAS))})", valores
    )
    con.commit()
    return int(cur.lastrowid)


def para_dict(s: Sinal) -> dict:
    d = asdict(s)
    d["ts"] = iso(s.ts)
    return d
