"""Módulo 11b — acompanhamento dos sinais acionáveis abertos (a cada coleta).

Avisa quando o preço toca alvo parcial, alvo final, stop ou o prazo (stop de tempo), e quando a
probabilidade devolve mais da metade do movimento ("❌ sinal invalidado — sair").
Na Fase 2 roda de hora em hora; na Fase 3 passa para o Worker (1–5 min).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from bot import formato as f
from bot.analise.sinais import leituras, preco_em
from bot.db import de_iso, iso


@dataclass
class Evento:
    sinal_id: int
    tipo: str  # parcial | alvo | stop | tempo | invalidado
    texto: str
    urgencia: str


def _fechar(con: sqlite3.Connection, sid: int, status: str, agora: datetime, resultado: float) -> None:
    con.execute(
        "UPDATE sinais SET status = ?, fechado_em = ?, resultado = ? WHERE id = ?",
        (status, iso(agora), resultado, sid),
    )


def acompanhar(con: sqlite3.Connection, regras: dict, agora: datetime) -> list[Evento]:
    custo = regras.get("diario", {}).get("custo_estimado_pct", 0.2) / 100
    devolucao = regras.get("risco", {}).get("invalidacao_devolucao", 0.5)
    eventos: list[Evento] = []
    abertos = con.execute("SELECT * FROM sinais WHERE status = 'aberto'").fetchall()
    for s in abertos:
        if not s["acionavel"]:
            continue  # informativos: o diário avalia em +1 h/+1 d/+1 sem; sem alertas de saída
        preco = preco_em(con, s["ativo"], agora, janela_h=2)
        if not preco:
            continue
        sentido, entrada = s["sentido"], s["entrada"]
        resultado = sentido * (preco / entrada - 1) - custo
        nome = s["ativo"].removesuffix(".SA")
        pergunta = json.loads(s["detalhes"] or "{}").get("pergunta", "")
        avisos = json.loads(s["avisos"] or "[]")
        cab = f"{nome} ({'🔺 long' if sentido > 0 else '🔻 short'} de {f.numero(entrada)}) agora {f.numero(preco)}"
        res = f"Resultado simulado: {f.pct(resultado, 2, sinal=True)}"

        # invalidação pela própria probabilidade
        lt = leituras(con, s["mercado_id"], 1) if s["mercado_id"] else []
        if lt and s["p_base"] is not None and s["p_sinal"] is not None:
            mov = s["p_sinal"] - s["p_base"]
            atual = lt[-1][1] - s["p_base"]
            if mov and atual / mov < 1 - devolucao:
                _fechar(con, s["id"], "invalidado", agora, resultado)
                eventos.append(
                    Evento(
                        s["id"],
                        "invalidado",
                        f"❌ Sinal invalidado — sair\n{cab}\n{f.esc(f.encurtar(pergunta, 70))}: "
                        f"probabilidade devolveu mais da metade do movimento\n{res}",
                        "🚨",
                    )
                )
                continue
        if s["stop"] is not None and sentido * (preco - s["stop"]) <= 0:
            _fechar(con, s["id"], "stop", agora, resultado)
            eventos.append(Evento(s["id"], "stop", f"🛑 Stop atingido\n{cab}\n{res}", "🚨"))
            continue
        if s["alvo"] is not None and sentido * (preco - s["alvo"]) >= 0:
            _fechar(con, s["id"], "alvo", agora, resultado)
            eventos.append(Evento(s["id"], "alvo", f"🎯 Alvo final atingido\n{cab}\n{res}", "🔔"))
            continue
        fim = de_iso(s["stop_tempo"])
        if fim and agora >= fim:
            _fechar(con, s["id"], "tempo", agora, resultado)
            eventos.append(Evento(s["id"], "tempo", f"⏱️ Prazo do sinal acabou — sair\n{cab}\n{res}", "🔔"))
            continue
        if (
            s["alvo_parcial"] is not None
            and "parcial" not in avisos
            and sentido * (preco - s["alvo_parcial"]) >= 0
        ):
            avisos.append("parcial")
            con.execute("UPDATE sinais SET avisos = ? WHERE id = ?", (json.dumps(avisos), s["id"]))
            eventos.append(Evento(s["id"], "parcial", f"🎯 Alvo parcial atingido\n{cab}\n{res}", "🔔"))
    # informativos abertos há mais de 1 semana saem da lista de abertos
    con.execute(
        "UPDATE sinais SET status = 'encerrado' WHERE status = 'aberto' AND acionavel = 0 AND ts < ?",
        (iso(agora - timedelta(days=7)),),
    )
    con.commit()
    return eventos
