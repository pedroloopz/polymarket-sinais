"""Módulo 12 — trava contra impulso: após N perdas seguidas no diário simulado,
pausa os sinais acionáveis por 24 h e avisa."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from bot import formato as f
from bot.db import de_iso, guardar_texto, iso, ler_texto


def pausado_ate(con: sqlite3.Connection, agora: datetime) -> datetime | None:
    ate = de_iso(ler_texto(con, "pausa_ate"))
    return ate if ate and ate > agora else None


def verificar(con: sqlite3.Connection, regras: dict, agora: datetime) -> str | None:
    """Liga a trava se as últimas N operações acionáveis encerradas deram prejuízo.
    Retorna a mensagem de aviso (só na hora em que a trava liga)."""
    p = regras.get("protecao", {})
    n = int(p.get("perdas_seguidas_para_pausar", 2))
    ultimos = con.execute(
        """SELECT id, resultado FROM sinais WHERE acionavel = 1 AND resultado IS NOT NULL
           AND fechado_em IS NOT NULL ORDER BY fechado_em DESC, id DESC LIMIT ?""",
        (n,),
    ).fetchall()
    if len(ultimos) < n or any(r["resultado"] > 0 for r in ultimos):
        return None
    marca = str(ultimos[0]["id"])
    if ler_texto(con, "trava_ultimo_id") == marca:
        return None  # esta sequência já travou
    ate = agora + timedelta(hours=p.get("pausa_horas", 24))
    guardar_texto(con, "pausa_ate", iso(ate))
    guardar_texto(con, "trava_ultimo_id", marca)
    return (
        f"⏸️ <b>Trava ligada</b>: {n} perdas seguidas no diário simulado.\n"
        f"Sinais acionáveis pausados até {f.data_hora(ate)}. Os informativos continuam.\n"
        "Respire. O plano existe para os dias ruins."
    )
