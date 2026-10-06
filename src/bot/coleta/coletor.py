"""Módulo 1 — snapshot horário dos mercados dos temas e dos ativos ligados."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from bot.coleta.polymarket_clob import Clob
from bot.coleta.polymarket_gamma import Gamma, Mercado, e_palavras_ditas
from bot.coleta.precos import Cotacao
from bot.config import Config
from bot.db import iso
from bot.logs import aviso, info, log

_log = log("coleta")


@dataclass
class ResultadoColeta:
    ts: datetime
    mercados: int = 0
    novos_ids: list[str] = field(default_factory=list)
    cotacoes: int = 0
    fontes: dict[str, str] = field(default_factory=dict)
    primeira_coleta: bool = False


def _gravar_mercado(
    con: sqlite3.Connection, m: Mercado, tema: str, prob: float | None, palavras_ditas: bool, ts: str
) -> bool:
    """Insere/atualiza o mercado. Retorna True se é a primeira vez que o vemos."""
    existe = con.execute("SELECT 1 FROM mercados WHERE id = ?", (m.id,)).fetchone()
    valores = dict(
        id=m.id,
        tema=tema,
        evento_id=m.evento_id,
        evento_titulo=m.evento_titulo,
        pergunta=m.pergunta,
        item=m.item,
        slug=m.slug,
        evento_slug=m.evento_slug,
        token_sim=m.token_sim,
        fim=iso(m.fim) if m.fim else None,
        criado_em=iso(m.criado_em) if m.criado_em else None,
        ts=ts,
        volume=m.volume,
        liquidez=m.liquidez,
        prob=prob,
        var=m.var_24h,
        pd=int(palavras_ditas),
        condicao=m.condicao or None,
        fechado=int(m.fechado),
    )
    if existe:
        con.execute(
            """UPDATE mercados SET evento_titulo=:evento_titulo, pergunta=:pergunta, item=:item, fim=:fim,
               ultimo_visto=:ts, volume=:volume, liquidez=:liquidez, prob=:prob, var_24h_gamma=:var,
               palavras_ditas=:pd, fechado=:fechado, condicao=COALESCE(:condicao, condicao) WHERE id=:id""",
            valores,
        )
        return False
    con.execute(
        """INSERT INTO mercados (id, tema, evento_id, evento_titulo, pergunta, item, slug, evento_slug,
           token_sim, fim, criado_em, primeiro_visto, ultimo_visto, volume, liquidez, prob, var_24h_gamma,
           palavras_ditas, fechado, condicao)
           VALUES (:id, :tema, :evento_id, :evento_titulo, :pergunta, :item, :slug, :evento_slug, :token_sim,
           :fim, :criado_em, :ts, :ts, :volume, :liquidez, :prob, :var, :pd, :fechado, :condicao)""",
        valores,
    )
    return True


def coletar(
    con: sqlite3.Connection,
    cfg: Config,
    gamma: Gamma,
    clob: Clob,
    cotar: Callable[[list[str]], dict[str, Cotacao]],
    ts: datetime,
) -> ResultadoColeta:
    res = ResultadoColeta(ts=ts)
    ts_txt = iso(ts.replace(second=0, microsecond=0))
    res.primeira_coleta = con.execute("SELECT COUNT(*) FROM mercados").fetchone()[0] == 0
    regras_coleta = cfg.regras.get("coleta", {})

    # 1) Descobrir mercados por tema (uma falha num tema não derruba os outros).
    por_tema: dict[str, list[Mercado]] = {}
    erros_gamma = seguidos = 0
    for chave, tema in cfg.temas_ligados().items():
        if seguidos >= 2:  # API fora do ar: não gasta minutos das Actions repetindo
            aviso(_log, "Gamma falhou 2× seguidas; pulando os demais temas")
            break
        try:
            por_tema[chave] = gamma.mercados_do_tema(
                tema,
                limite_busca=regras_coleta.get("resultados_por_busca", 20),
                maximo=regras_coleta.get("max_mercados_por_tema", 40),
                ignorar_fechados=regras_coleta.get("ignorar_mercados_fechados", True),
            )
            seguidos = 0
        except Exception as erro:
            erros_gamma += 1
            seguidos += 1
            aviso(_log, "tema falhou na Gamma", tema=chave, erro=str(erro))
    res.fontes["Polymarket Gamma"] = (
        "ok"
        if erros_gamma == 0
        else ("indisponível" if not por_tema else f"parcial ({erros_gamma} tema(s) com erro)")
    )

    # 2) Midpoints em lote (fallback: preço da Gamma).
    tokens = [m.token_sim for ms in por_tema.values() for m in ms if m.token_sim]
    mids: dict[str, float] = {}
    if tokens:
        try:
            mids = clob.midpoints(tokens, lote=regras_coleta.get("lote_midpoints", 50))
            res.fontes["Polymarket CLOB"] = "ok" if mids else "sem dados"
        except Exception as erro:
            res.fontes["Polymarket CLOB"] = "indisponível"
            aviso(_log, "midpoints falharam", erro=str(erro))

    atribuido: set[str] = set()
    for chave, mercados in por_tema.items():
        tema = cfg.temas[chave]
        for m in mercados:
            if m.id in atribuido:  # um mercado pertence ao primeiro tema que o encontrou
                continue
            atribuido.add(m.id)
            mid = mids.get(m.token_sim or "")
            prob = mid if mid is not None else m.prob_gamma
            if _gravar_mercado(con, m, chave, prob, e_palavras_ditas(m, tema), ts_txt):
                res.novos_ids.append(m.id)
            con.execute(
                """INSERT OR REPLACE INTO series (ts, tipo, chave, valor, volume, liquidez, bid, ask, fonte)
                   VALUES (?, 'mercado', ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ts_txt,
                    m.id,
                    prob,
                    m.volume,
                    m.liquidez,
                    m.bid,
                    m.ask,
                    "midpoint" if mid is not None else "gamma",
                ),
            )
            res.mercados += 1

    # 3) Cotações dos ativos e indicadores no mesmo horário.
    try:
        cotacoes = cotar(cfg.todos_tickers())
        for c in cotacoes.values():
            con.execute(
                """INSERT OR REPLACE INTO series (ts, tipo, chave, valor, fonte, ts_fonte)
                   VALUES (?, 'ativo', ?, ?, 'yfinance', ?)""",
                (ts_txt, c.ticker, c.preco, iso(c.ts_fonte)),
            )
        res.cotacoes = len(cotacoes)
        total = len(cfg.todos_tickers())
        res.fontes["Preços (yfinance)"] = (
            "ok"
            if res.cotacoes == total
            else ("indisponível" if res.cotacoes == 0 else f"parcial ({res.cotacoes}/{total})")
        )
    except Exception as erro:
        res.fontes["Preços (yfinance)"] = "indisponível"
        aviso(_log, "cotações falharam", erro=str(erro))

    # Na primeira coleta tudo é "novo": marca como avisado para não inundar o Telegram.
    if res.primeira_coleta:
        con.execute("UPDATE mercados SET novo_avisado = 1")
    con.commit()
    info(
        _log,
        "coleta concluída",
        mercados=res.mercados,
        novos=len(res.novos_ids),
        cotacoes=res.cotacoes,
        fontes=res.fontes,
    )
    return res
