"""Tarefas executadas pelas GitHub Actions (coleta horária e resumo diário)."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from bot import db
from bot.analise import acompanhamento, balancos, calibracao, novos, prazos, protecao, sinais
from bot.coleta import precos
from bot.coleta.coletor import coletar
from bot.coleta.polymarket_clob import Clob
from bot.coleta.polymarket_gamma import Gamma
from bot.config import Config, carregar
from bot.diario import avaliacao, placar
from bot.diario.registro import registrar
from bot.http import Http
from bot.kv import KV
from bot.logs import aviso, info, log
from bot.saida import painel, resumo
from bot.saida.telegram import Telegram, despachar, esvaziar_fila, informativos_pendentes

_log = log("tarefas")
BOTOES_RESUMO = [
    [
        {"text": "⏳ Prazos", "callback_data": "ver:prazos"},
        {"text": "🪙 Balanços", "callback_data": "ver:balancos"},
    ],
    [
        {"text": "🆕 Novos", "callback_data": "ver:novos"},
        {"text": "📒 Placar", "callback_data": "ver:placar"},
    ],
]


@dataclass
class Contexto:
    cfg: Config
    con: sqlite3.Connection
    http: Http
    tg: Telegram
    kv: KV
    agora: datetime


def contexto(caminho_db: str | Path | None = None, agora: datetime | None = None) -> Contexto:
    kv = KV()
    ajustes = kv.ler("config", {}) if kv.ativo else {}
    cfg = carregar(ajustes)
    http = Http(pausa=cfg.regras.get("coleta", {}).get("pausa_entre_chamadas_s", 0.0))
    caminho = caminho_db or os.getenv("BOT_DB", "dados/bot.sqlite")
    return Contexto(
        cfg=cfg, con=db.conectar(caminho), http=http, tg=Telegram(), kv=kv, agora=agora or db.agora()
    )


def _textos_comuns(ctx: Contexto) -> dict[str, str]:
    cfg, con, agora = ctx.cfg, ctx.con, ctx.agora
    d = cfg.regras.get("diario", {})
    p = placar.calcular(con, agora)
    recentes = novos.recentes(con, agora)
    return {
        "sinais": sinais.texto_recentes(con, cfg, agora),
        "prazos": prazos.texto(prazos.vencendo(con, cfg, agora), cfg),
        "novos": novos.mensagem(recentes, cfg) or "🆕 Nenhum mercado novo nos últimos 7 dias.",
        "placar": placar.texto(p, d.get("minimo_sinais_avaliados", 30), d.get("minimo_semanas", 8)),
    }


def _publicar_painel(ctx: Contexto, fontes: dict[str, str], textos: dict[str, str]) -> None:
    if not ctx.kv.ativo:
        return
    dados = painel.montar(ctx.con, ctx.cfg, ctx.agora, fontes=fontes, textos=textos)
    if ctx.kv.gravar("painel", dados):
        info(_log, "painel publicado no KV", bytes=painel.tamanho(dados))


def tarefa_coletar(ctx: Contexto) -> dict[str, str]:
    cfg, con, agora = ctx.cfg, ctx.con, ctx.agora
    status = "ok"
    fontes: dict[str, str] = {}
    try:
        esvaziar_fila(con, ctx.tg, cfg.regras, agora)
        res = coletar(con, cfg, Gamma(ctx.http), Clob(ctx.http), precos.ultimas_cotacoes, agora)
        fontes = res.fontes

        if not res.primeira_coleta:
            lista = novos.pendentes(con, cfg, agora)
            texto = novos.mensagem(lista, cfg)
            if texto:
                despachar(con, ctx.tg, texto, "🔔", cfg.regras, agora)
        novos.marcar_avisados(con)

        d = cfg.regras.get("diario", {})
        avaliacao.avaliar_pendentes(con, agora, d.get("custo_estimado_pct", 0.2), d.get("horizontes"))
        _rodar_sinais(ctx)
        _publicar_painel(ctx, fontes, _textos_comuns(ctx))
    except Exception:
        status = "erro"
        raise
    finally:
        db.registrar_execucao(con, "coletar", agora, status, fontes)
    return fontes


def _rodar_sinais(ctx: Contexto) -> None:
    """Módulos 3, 4, 11, 11b e 12: acompanha os abertos, checa a trava e procura sinais novos.
    Qualquer erro aqui é registrado sem derrubar a coleta."""
    cfg, con, agora = ctx.cfg, ctx.con, ctx.agora
    clob = Clob(ctx.http)
    try:
        for e in acompanhamento.acompanhar(con, cfg.regras, agora):
            despachar(con, ctx.tg, e.texto, e.urgencia, cfg.regras, agora)
        aviso_trava = protecao.verificar(con, cfg.regras, agora)
        if aviso_trava:
            despachar(con, ctx.tg, aviso_trava, "🔔", cfg.regras, agora)
        pausado = protecao.pausado_ate(con, agora) is not None
        candidatos = sinais.detectar(con, cfg, agora, clob.historico_periodo)
        for c in candidatos:
            montado = sinais.montar(
                con, cfg, c, agora, obter_hist=clob.historico_periodo,
                obter_ohlc=lambda t: precos.ohlc_diario(t, 60), pausado=pausado,
            )  # fmt: skip
            if not montado:
                continue
            registrar(con, montado.sinal)
            texto = montado.texto
            if montado.sinal.urgencia == "📋":  # informativo: uma linha no resumo diário
                texto = sinais.linha_curta(cfg, montado.sinal, c.mercado["pergunta"])
            despachar(con, ctx.tg, texto, montado.sinal.urgencia, cfg.regras, agora)
        info(_log, "sinais avaliados", candidatos=len(candidatos), pausado=pausado)
    except Exception as erro:
        aviso(_log, "módulo de sinais falhou; coleta segue", erro=str(erro))


def tarefa_calibrar(ctx: Contexto) -> str:
    """Módulo 2 (mensal): recalcula defasagem e beta de cada par e publica o /ranking."""
    cfg, con, agora = ctx.cfg, ctx.con, ctx.agora
    status = "ok"
    try:
        clob = Clob(ctx.http)
        pares = calibracao.calibrar(con, cfg, agora, clob.historico_periodo, precos.barras_intradiarias)
        texto = calibracao.texto_ranking(con, cfg, cfg.regras.get("calibracao", {}).get("t_min", 2.0))
        db.guardar_texto(con, "ranking", texto)
        confirmados = sum(1 for p in pares if p.confirmado)
        cab = f"📊 Calibração concluída: {len(pares)} pares medidos, {confirmados} com efeito claro.\n\n"
        despachar(con, ctx.tg, cab + texto, "🔔", cfg.regras, agora)
        _publicar_painel(ctx, {}, {**_textos_comuns(ctx), "ranking": texto})
        return texto
    except Exception:
        status = "erro"
        raise
    finally:
        db.registrar_execucao(con, "calibrar", agora, status, {})


def tarefa_placar_semanal(ctx: Contexto) -> str:
    cfg, con, agora = ctx.cfg, ctx.con, ctx.agora
    d = cfg.regras.get("diario", {})
    texto = placar.semanal(con, agora, d.get("minimo_sinais_avaliados", 30), d.get("minimo_semanas", 8))
    db.guardar_texto(con, "placar_semanal", texto)
    despachar(con, ctx.tg, texto, "🔔", cfg.regras, agora)
    _publicar_painel(ctx, {}, _textos_comuns(ctx))
    db.registrar_execucao(con, "placar_semanal", agora, "ok", {})
    return texto


def _levantar_balancos(ctx: Contexto) -> tuple[list[balancos.Balanco], str]:
    try:
        lista = balancos.levantar(
            ctx.con,
            ctx.cfg,
            ctx.agora,
            precos.datas_balanco,
            precos.calendario,
            lambda t: precos.historico_diario(t, "3y"),
        )
    except Exception as erro:
        aviso(_log, "balanços falharam", erro=str(erro))
        return [], "indisponível"
    ok = sum(1 for b in lista if not b.erro)
    estado = "ok" if ok == len(lista) else ("indisponível" if ok == 0 else f"parcial ({ok}/{len(lista)})")
    return lista, estado


def _acionaveis_24h(ctx: Contexto) -> list[str]:
    linhas = ctx.con.execute(
        """SELECT * FROM sinais WHERE acionavel = 1 AND ts >= ? ORDER BY ts""",
        (db.iso(ctx.agora - timedelta(hours=24)),),
    ).fetchall()
    return [
        f"{r['ativo'].removesuffix('.SA')} {'🔺' if r['sentido'] > 0 else '🔻'} {r['semaforo'] or ''} ({r['status']})"
        for r in linhas
    ]


def tarefa_resumo(ctx: Contexto) -> str:
    cfg, con, agora = ctx.cfg, ctx.con, ctx.agora
    ultima = db.ultima_execucao(con, "coletar")
    fontes: dict[str, str] = {}
    if not ultima or db.de_iso(ultima["fim"]) < agora - timedelta(hours=2):
        info(_log, "última coleta antiga; coletando antes do resumo")
        fontes = tarefa_coletar(ctx)
    elif ultima["fontes"]:
        fontes = json.loads(ultima["fontes"])

    lista, estado = _levantar_balancos(ctx)
    fontes = {**fontes, "Balanços (Yahoo)": estado}
    texto_bal = balancos.texto_completo(lista, agora) if lista else "🪙 Balanços indisponíveis hoje."
    db.guardar_texto(con, "balancos", texto_bal)

    d = cfg.regras.get("diario", {})
    p = placar.calcular(con, agora)
    desde = db.iso(agora - timedelta(hours=24))
    n_novos = con.execute(
        """SELECT COUNT(*) FROM mercados WHERE primeiro_visto >= ?
           AND primeiro_visto > (SELECT MIN(primeiro_visto) FROM mercados)""",
        (desde,),
    ).fetchone()[0]
    texto = resumo.resumo_diario(
        con,
        cfg,
        agora,
        balancos=balancos.no_resumo(lista, cfg, agora),
        n_vencendo=len(prazos.vencendo(con, cfg, agora)),
        n_novos=n_novos,
        placar=placar.linha_resumo(p, d.get("minimo_sinais_avaliados", 30), d.get("minimo_semanas", 8)),
        sinais_acionaveis=_acionaveis_24h(ctx),
        fontes=fontes,
        informativos=informativos_pendentes(con),
    )
    despachar(con, ctx.tg, texto, "🔔", cfg.regras, agora, botoes=BOTOES_RESUMO)
    db.guardar_texto(con, "resumo", texto)
    _publicar_painel(ctx, fontes, {**_textos_comuns(ctx), "resumo": texto, "balancos": texto_bal})
    db.registrar_execucao(con, "resumo", agora, "ok", fontes)
    return texto
