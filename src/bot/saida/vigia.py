"""Ponte com o Worker de quase tempo real (Fase 3).

Actions → KV "vigia" (de hora em hora): mercados prioritários com desvio horário, calibração, ATR,
indicadores do semáforo, regras e sinais acionáveis abertos.
Worker → KV "rt" (a cada 5 min): últimas leituras + eventos (sinais novos, fechamentos, mensagens
seguradas no silêncio). As Actions leem os eventos, gravam no diário e confirmam em "rt_ack".
Só o Worker escreve "rt" e só as Actions escrevem "vigia"/"rt_ack": sem disputa de escrita.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta

import pandas as pd

from bot import formato as f
from bot.analise import calibracao, manipulacao, risco
from bot.analise.sinais import desvio_horario, preco_em
from bot.config import Config
from bot.db import de_iso, guardar_texto, iso, ler_texto
from bot.diario.registro import Sinal, registrar
from bot.logs import aviso, info, log

_log = log("vigia")


def worker_vivo(rt: dict | None, agora: datetime, tolerancia_min: int = 20) -> bool:
    ts = de_iso((rt or {}).get("atualizado_em"))
    return bool(ts and agora - ts <= timedelta(minutes=tolerancia_min))


def atualizar_atr(
    con: sqlite3.Connection,
    tickers: list[str],
    agora: datetime,
    obter_ohlc: Callable[[str], pd.DataFrame],
    n: int = 14,
) -> dict[str, float]:
    """ATR por ticker, recalculado no máximo 1×/dia (cache em textos.atr)."""
    cache = json.loads(ler_texto(con, "atr", "{}") or "{}")
    if de_iso(cache.get("_ts")) and agora - de_iso(cache["_ts"]) < timedelta(hours=20):
        faltam = [t for t in tickers if t not in cache]
    else:
        cache, faltam = {}, list(tickers)
    for t in faltam[:40]:
        try:
            v = risco.atr(obter_ohlc(t), n)
            if v:
                cache[t] = v
        except Exception as erro:
            aviso(_log, "ATR indisponível", ativo=t, erro=str(erro))
    cache["_ts"] = cache.get("_ts") or iso(agora)
    guardar_texto(con, "atr", json.dumps(cache))
    return {k: v for k, v in cache.items() if not k.startswith("_")}


def montar(
    con: sqlite3.Connection,
    cfg: Config,
    agora: datetime,
    *,
    obter_hist,
    obter_ohlc: Callable[[str], pd.DataFrame],
    pausado_ate: datetime | None,
) -> dict:
    r = cfg.regras
    rs, rr, rt = r.get("sinais", {}), r.get("risco", {}), r.get("tempo_real", {})
    t_min = r.get("calibracao", {}).get("t_min", 3.3)
    vol_min = r.get("filtros", {}).get("volume_min_sinal_usd", 0)
    temas = set(cfg.temas_ligados())
    linhas = con.execute(
        """SELECT * FROM mercados WHERE fechado = 0 AND palavras_ditas = 0 AND volume >= ? AND token_sim IS NOT NULL
           AND prob > 0.02 AND prob < 0.98 AND ultimo_visto >= ? ORDER BY volume DESC""",
        (vol_min, iso(agora - timedelta(hours=3))),
    ).fetchall()
    linhas = [m for m in linhas if m["tema"] in temas][: rt.get("mercados", 25)]

    pares = {m["id"]: calibracao.confirmados(con, m["id"], t_min) for m in linhas}
    tickers = {p[0]["ativo"] for p in pares.values() if p}
    abertos = con.execute("SELECT * FROM sinais WHERE status = 'aberto' AND acionavel = 1").fetchall()
    tickers |= {s["ativo"] for s in abertos}
    atrs = atualizar_atr(con, sorted(tickers), agora, obter_ohlc, rr.get("atr_dias", 14))

    def bolsa_de(t: str) -> str:
        return (cfg.ativos.get(t) or cfg.indicadores.get(t) or {}).get("bolsa", "EUA")

    mercados = []
    for m in linhas:
        sigma = desvio_horario(
            con, m["id"], m["token_sim"], agora, obter_hist, rs.get("janela_desvio_dias", 30)
        )
        if not sigma:
            continue
        tema = cfg.temas[m["tema"]]
        par = None
        if pares[m["id"]]:
            p0 = pares[m["id"]][0]
            alt = pares[m["id"]][1] if len(pares[m["id"]]) > 1 else None
            par = {
                "ativo": p0["ativo"], "beta_10pp": p0["beta_10pp"], "defasagem_min": p0["defasagem_min"],
                "bolsa": bolsa_de(p0["ativo"]), "atr": atrs.get(p0["ativo"]),
                "alt": {"ativo": alt["ativo"], "beta_10pp": alt["beta_10pp"]} if alt else None,
            }  # fmt: skip
        hip = [(t, s) for t, s in cfg.ativos_do_tema(m["tema"]).items() if s and t in cfg.ativos]
        nota = manipulacao.ler(con, m["id"])
        mercados.append({
            "id": m["id"], "token": m["token_sim"], "tema": m["tema"], "emoji": tema.get("emoji", ""),
            "nome_tema": tema.get("nome", m["tema"]), "pergunta": m["pergunta"], "sigma_h": sigma,
            "fim": m["fim"], "manip": nota.nota if nota else None, "par": par,
            "hipotese": {"ativo": hip[0][0], "sentido": hip[0][1]} if hip else None,
            "semaforo": tema.get("semaforo") or {},
        })  # fmt: skip

    capital = rr.get("capital")
    return {
        "versao": 1,
        "gerado_em": iso(agora),
        "regras": {
            "zscore_min": rs.get("zscore_min", 2.0),
            "retencao_min": rs.get("retencao_min", 0.5),
            "prefiltro_pp": rs.get("prefiltro_pp", 1.0),
            "espaco_min_pct": rs.get("espaco_minimo_pct_do_esperado", 50),
            "latencia_multiplo": rs.get("latencia_multiplo", 3),
            "zona": rs.get("zona_distorcida", {"abaixo": 0.1, "acima": 0.9}),
            "prazo_curto_dias": rs.get("prazo_curto_dias", 3),
            "prazo_curto_fator_z": rs.get("prazo_curto_fator_z", 1.5),
            "ganho_risco_min": rr.get("ganho_risco_min", 1.5),
            "risco_pct": rr.get("risco_por_operacao_pct", 1.0),
            "atr_mult": rr.get("atr_multiplo_stop", 1.5),
            "stop_tempo_mult": rr.get("stop_tempo_multiplo_defasagem", 2),
            "devolucao": rr.get("invalidacao_devolucao", 0.5),
            "custo_pct": r.get("diario", {}).get("custo_estimado_pct", 0.2),
            "limiar_semaforo_pct": r.get("semaforo", {}).get("limiar_pct", 0.1),
            "silencio": r.get("silencio", {}),
            "janelas_min": rt.get("janelas_min", [15, 30, 60]),
            "pausado_ate": iso(pausado_ate) if pausado_ate else None,
        },
        "capital_brl": capital,
        "cambio_brl": preco_em(con, "BRL=X", agora, janela_h=96),
        "pregoes": cfg.pregoes,
        "mercados": mercados,
        "abertos": [
            {
                "id": s["id"],
                "ativo": s["ativo"],
                "bolsa": bolsa_de(s["ativo"]),
                "sentido": s["sentido"],
                "entrada": s["entrada"],
                "stop": s["stop"],
                "alvo": s["alvo"],
                "parcial": s["alvo_parcial"],
                "stop_tempo": s["stop_tempo"],
                "mercado_id": s["mercado_id"],
                "p_base": s["p_base"],
                "p_sinal": s["p_sinal"],
                "avisos": json.loads(s["avisos"] or "[]"),
                "token": (
                    con.execute("SELECT token_sim FROM mercados WHERE id=?", (s["mercado_id"],)).fetchone()
                    or {"token_sim": None}
                )["token_sim"],
            }  # fmt: skip
            for s in abertos
        ],
    }


def ingerir(con: sqlite3.Connection, cfg: Config, rt: dict | None, agora: datetime) -> tuple[list[str], int]:
    """Grava no diário os eventos do Worker ainda não confirmados.
    Retorna (textos a enfileirar para depois do silêncio/resumo com urgência, último seq lido)."""
    ack = int(ler_texto(con, "rt_ack", "0") or 0)
    eventos = [e for e in (rt or {}).get("eventos", []) if int(e.get("seq", 0)) > ack]
    seguradas: list[str] = []
    for e in sorted(eventos, key=lambda x: x["seq"]):
        tipo = e.get("tipo")
        try:
            if tipo == "sinal":
                s = e["sinal"]
                registrar(con, Sinal(
                    ts=de_iso(s["ts"]), tema=s["tema"], ativo=s["ativo"], sentido=int(s["sentido"]),
                    entrada=float(s["entrada"]), mercado_id=s.get("mercado_id"), stop=s.get("stop"),
                    alvo=s.get("alvo"), semaforo=s.get("semaforo"), manipulacao=s.get("manipulacao"),
                    urgencia=s.get("urgencia", "📋"), acionavel=bool(s.get("acionavel")),
                    latencia_s=s.get("latencia_s"), confianca=s.get("confianca"),
                    detalhes={**(s.get("detalhes") or {}), "origem": "worker", "ref": f"rt-{e['seq']}"},
                    base_ts=de_iso(s.get("base_ts")), p_base=s.get("p_base"), p_sinal=s.get("p_sinal"),
                    z=s.get("z"), alvo_parcial=s.get("parcial"), stop_tempo=de_iso(s.get("stop_tempo")),
                    esperado=s.get("esperado"), realizado=s.get("realizado"),
                    defasagem_min=s.get("defasagem_min"), beta_10pp=s.get("beta_10pp"),
                    quantidade=s.get("quantidade"),
                ))  # fmt: skip
                if s.get("urgencia") == "📋" and e.get("linha"):
                    con.execute(
                        "INSERT INTO fila (ts, texto, urgencia) VALUES (?, ?, '📋')", (iso(agora), e["linha"])
                    )
            elif tipo == "fechamento":
                alvo = e.get("sinal_id")
                if not alvo and e.get("ref"):
                    linha = con.execute(
                        "SELECT id FROM sinais WHERE json_extract(detalhes, '$.ref') = ?", (e["ref"],)
                    ).fetchone()
                    alvo = linha["id"] if linha else None
                if alvo:
                    con.execute(
                        "UPDATE sinais SET status = ?, resultado = ?, fechado_em = ? WHERE id = ? AND status = 'aberto'",
                        (e["status"], e.get("resultado"), e.get("ts") or iso(agora), alvo),
                    )
            elif tipo == "parcial":
                alvo = e.get("sinal_id")
                if not alvo and e.get("ref"):
                    linha = con.execute(
                        "SELECT id FROM sinais WHERE json_extract(detalhes, '$.ref') = ?", (e["ref"],)
                    ).fetchone()
                    alvo = linha["id"] if linha else None
                if alvo:
                    con.execute("UPDATE sinais SET avisos = '[\"parcial\"]' WHERE id = ?", (alvo,))
            elif tipo == "segurada":
                seguradas.append(e["texto"])
        except Exception as erro:
            aviso(_log, "evento do Worker ignorado", seq=e.get("seq"), erro=str(erro))
        ack = max(ack, int(e["seq"]))
    con.commit()
    guardar_texto(con, "rt_ack", str(ack))
    if eventos:
        info(_log, "eventos do Worker gravados", n=len(eventos), ack=ack)
    return seguradas, ack


def texto_status(rt: dict | None, agora: datetime) -> str:
    if not rt:
        return "⚡ Tempo real: Worker ainda não rodou."
    ts = de_iso(rt.get("atualizado_em"))
    if not ts:
        return "⚡ Tempo real: sem leitura."
    atraso = (agora - ts).total_seconds() / 60
    estado = "✅" if atraso <= 20 else "⚠️ parado"
    return f"⚡ Tempo real: {estado} última leitura {f.hora(ts)} ({len(rt.get('leituras', {}))} mercados vigiados)"
