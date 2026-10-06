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


def registrar(con: sqlite3.Connection, s: Sinal) -> int:
    if s.sentido not in (1, -1):
        raise ValueError("sentido deve ser +1 (long) ou -1 (short)")
    cur = con.execute(
        """INSERT INTO sinais (ts, tema, mercado_id, ativo, sentido, entrada, stop, alvo, semaforo,
           manipulacao, urgencia, acionavel, latencia_s, detalhes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            iso(s.ts),
            s.tema,
            s.mercado_id,
            s.ativo,
            s.sentido,
            s.entrada,
            s.stop,
            s.alvo,
            s.semaforo,
            s.manipulacao,
            s.urgencia,
            int(s.acionavel),
            s.latencia_s,
            json.dumps(s.detalhes or {}, ensure_ascii=False),
        ),
    )
    con.commit()
    return int(cur.lastrowid)


def para_dict(s: Sinal) -> dict:
    d = asdict(s)
    d["ts"] = iso(s.ts)
    return d
