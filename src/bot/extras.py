"""Fase 3 dentro das Actions: tempo real (ponte com o Worker), Kalshi, GDELT, manipulação,
carteiras vencedoras e agenda. Cada bloco falha sozinho, sem derrubar a coleta."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta

from bot import formato as f
from bot.analise import baleias, manipulacao, plataformas, protecao
from bot.analise.balancos import Balanco
from bot.analise.mercados import agrupar_por_evento, ativos
from bot.coleta import agenda, gdelt, precos
from bot.coleta.kalshi import Kalshi
from bot.coleta.polymarket_clob import Clob
from bot.coleta.polymarket_data import DataApi
from bot.config import PASTA_CONFIG, Config
from bot.db import guardar_texto, iso
from bot.logs import aviso, info, log
from bot.saida import vigia
from bot.saida.telegram import despachar

_log = log("extras")
UA_NAVEGADOR = "Mozilla/5.0 (compatible; polymarket-sinais/0.3; somente leitura)"


# ---------- tempo real ----------


def ingerir_worker(ctx) -> tuple[dict | None, bool]:
    """Lê o estado do Worker, grava os eventos no diário e devolve (rt, worker_vivo)."""
    if not ctx.kv.ativo:
        return None, False
    rt = ctx.kv.ler("rt", None)
    try:
        seguradas, ack = vigia.ingerir(ctx.con, ctx.cfg, rt, ctx.agora)
        for texto in seguradas:
            despachar(ctx.con, ctx.tg, texto, "🔔", ctx.cfg.regras, ctx.agora)
        ctx.kv.gravar("rt_ack", ack)
    except Exception as erro:
        aviso(_log, "ingestão do Worker falhou", erro=str(erro))
    return rt, vigia.worker_vivo(rt, ctx.agora)


def publicar_vigia(ctx) -> int:
    if not ctx.kv.ativo:
        return 0
    try:
        dados = vigia.montar(
            ctx.con, ctx.cfg, ctx.agora,
            obter_hist=Clob(ctx.http).historico_periodo,
            obter_ohlc=lambda t: precos.ohlc_diario(t, 60),
            pausado_ate=protecao.pausado_ate(ctx.con, ctx.agora),
        )  # fmt: skip
        ctx.kv.gravar("vigia", dados)
        info(_log, "vigia publicada", mercados=len(dados["mercados"]), abertos=len(dados["abertos"]))
        return len(dados["mercados"])
    except Exception as erro:
        aviso(_log, "vigia não publicada", erro=str(erro))
        return 0


# ---------- Kalshi, GDELT e manipulação ----------


def _picos_gdelt(ctx, temas: set[str]) -> dict[str, float | None]:
    saida: dict[str, float | None] = {}
    for t in temas:
        consulta = gdelt.consulta_do_tema(ctx.cfg.temas[t])
        if not consulta:
            continue
        try:
            saida[t] = gdelt.pico(gdelt.serie(ctx.http, consulta), ctx.agora)
        except Exception as erro:
            aviso(_log, "GDELT indisponível", tema=t, erro=str(erro))
            saida[t] = None
    return saida


def _moveu(con: sqlite3.Connection, mercado_id: str, agora: datetime, pp: float) -> bool:
    linhas = con.execute(
        "SELECT valor FROM series WHERE tipo='mercado' AND chave=? AND ts >= ? AND valor IS NOT NULL ORDER BY ts",
        (mercado_id, iso(agora - timedelta(hours=6))),
    ).fetchall()
    return len(linhas) >= 2 and abs(linhas[-1]["valor"] - linhas[0]["valor"]) * 100 >= pp


def plataformas_e_manipulacao(ctx) -> dict[str, str]:
    cfg, con, agora = ctx.cfg, ctx.con, ctx.agora
    fontes: dict[str, str] = {}
    vol_min = cfg.regras.get("filtros", {}).get("volume_min_sinal_usd", 0)
    try:
        lista = Kalshi(ctx.http).mercados_abertos(cfg.regras.get("kalshi", {}).get("paginas", 15))
        pares = plataformas.casar(
            con, lista, agora, vol_min, cfg.regras.get("kalshi", {}).get("similaridade_min", 0.45)
        )
        fontes["Kalshi"] = f"ok ({pares} pares)"
    except Exception as erro:
        fontes["Kalshi"] = "indisponível"
        aviso(_log, "Kalshi indisponível", erro=str(erro))

    mercados = con.execute(
        "SELECT * FROM mercados WHERE fechado = 0 AND volume >= ? AND ultimo_visto >= ? ORDER BY volume DESC LIMIT 60",
        (vol_min, iso(agora - timedelta(hours=3))),
    ).fetchall()
    pp_mov = cfg.regras.get("manipulacao", {}).get("movimento_pp", 3)
    temas_movendo = {m["tema"] for m in mercados if _moveu(con, m["id"], agora, pp_mov)}
    picos = _picos_gdelt(ctx, temas_movendo)
    if temas_movendo:
        fontes["GDELT"] = "ok" if any(v is not None for v in picos.values()) else "indisponível"

    api = DataApi(ctx.http)
    falhas = tentativas = 0
    for m in mercados:
        conc = None
        if m["condicao"] and falhas < 3:
            tentativas += 1
            try:
                conc = manipulacao.concentracao(api.holders(m["condicao"]))
            except Exception as erro:
                falhas += 1
                aviso(_log, "holders indisponíveis", mercado=m["id"], erro=str(erro))
        nota = manipulacao.avaliar(
            con, m, agora, regras=cfg.regras, concentracao_top5=conc,
            prob_kalshi=plataformas.prob_kalshi(con, m["id"], agora), pico_noticias=picos.get(m["tema"]),
        )  # fmt: skip
        manipulacao.gravar(con, m["id"], nota, agora)
    if tentativas:
        fontes["Polymarket Data API"] = (
            "ok" if falhas == 0 else ("indisponível" if falhas >= 3 else "parcial")
        )
    return fontes


# ---------- carteiras vencedoras ----------


def _manuais() -> list[dict]:
    import yaml

    caminho = PASTA_CONFIG / "carteiras_seguidas.yaml"
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}
    return (dados or {}).get("carteiras") or []


def vigiar_baleias(ctx) -> None:
    try:
        api = DataApi(ctx.http)
        for alerta in baleias.vigiar(ctx.con, ctx.cfg, ctx.agora, api.posicoes):
            despachar(ctx.con, ctx.tg, alerta, "🔔", ctx.cfg.regras, ctx.agora)
    except Exception as erro:
        aviso(_log, "vigia de baleias falhou", erro=str(erro))


def ranquear_baleias(ctx) -> str:
    try:
        api = DataApi(ctx.http)
        top = baleias.ranquear(ctx.con, ctx.cfg, ctx.agora, api.holders, api.posicoes_encerradas, _manuais())
        estado = "ok" if top else "sem carteiras aprovadas"
    except Exception as erro:
        aviso(_log, "ranking de baleias falhou", erro=str(erro))
        estado = "indisponível"
    guardar_texto(ctx.con, "baleias", baleias.texto(ctx.con))
    return estado


# ---------- agenda ----------


def _pagina(ctx, url: str) -> str:
    resp = ctx.http.sessao.get(url, headers={"User-Agent": UA_NAVEGADOR}, timeout=30)
    resp.raise_for_status()
    return resp.text


def _gravar_agenda(con: sqlite3.Connection, eventos: list[agenda.Evento], hoje: date) -> None:
    con.execute("DELETE FROM agenda WHERE data >= ? AND avisado = 0", (hoje.isoformat(),))
    for e in eventos:
        con.execute(
            """INSERT OR IGNORE INTO agenda (id, tipo, titulo, data, status, fonte, temas)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (e.id, e.tipo, e.titulo, e.data.isoformat(), e.status, e.fonte, json.dumps(e.temas)),
        )
    con.commit()


def _probabilidades(con, cfg: Config, temas: list[str], agora: datetime, n: int = 2) -> list[str]:
    linhas = []
    for t in temas:
        tema = cfg.temas.get(t)
        if not tema:
            continue
        for g in agrupar_por_evento(ativos(con, agora, tema=t))[:n]:
            x = g[0]
            itens = (
                " | ".join(f"{f.esc(f.encurtar(m.item, 18))}: {f.prob(m.prob)}" for m in g[:2])
                if len(g) > 1
                else f.prob(x.prob)
            )
            linhas.append(
                f"{tema.get('emoji', '')} {f.esc(f.encurtar(x.evento_titulo or x.pergunta, 50))}: {itens}"
            )
    return linhas


def atualizar_agenda(ctx, balancos_lista: list[Balanco]) -> tuple[list[str], dict[str, str]]:
    """Busca a agenda, grava, manda o alerta de véspera e devolve (eventos de hoje, fontes)."""
    cfg, con, agora = ctx.cfg, ctx.con, ctx.agora
    hoje = f.local(agora).date()
    eventos, fontes = agenda.buscar(lambda url: _pagina(ctx, url), hoje)
    for b in balancos_lista:
        if b.proxima:
            eventos.append(
                agenda.Evento(
                    "balanco",
                    f"Balanço {b.ticker}",
                    b.proxima.date(),
                    b.status,
                    "Yahoo Finance",
                    ["balancos_cripto"],
                )
            )
    _gravar_agenda(con, eventos, hoje)

    amanha = (hoje + timedelta(days=1)).isoformat()
    for e in con.execute("SELECT * FROM agenda WHERE data = ? AND avisado = 0", (amanha,)).fetchall():
        temas = json.loads(e["temas"] or "[]")
        texto = "\n".join([
            f"📅 <b>Amanhã ({f.data(datetime.fromisoformat(e['data']))}): {f.esc(e['titulo'])}</b> ({e['status']})",
            *(_probabilidades(con, cfg, temas, agora) or ["Sem mercados ligados acima do volume mínimo."]),
        ])  # fmt: skip
        despachar(con, ctx.tg, texto, "🔔", cfg.regras, agora)
        con.execute("UPDATE agenda SET avisado = 1 WHERE id = ?", (e["id"],))
    con.commit()
    hoje_lista = [
        f"{r['titulo']} ({r['status']})"
        for r in con.execute(
            "SELECT * FROM agenda WHERE data = ? ORDER BY tipo", (hoje.isoformat(),)
        ).fetchall()
    ]
    guardar_texto(con, "agenda", texto_agenda(con, hoje))
    return hoje_lista, fontes


def texto_agenda(con: sqlite3.Connection, hoje: date, dias: int = 30) -> str:
    linhas = con.execute(
        "SELECT * FROM agenda WHERE data >= ? AND data <= ? ORDER BY data, tipo",
        (hoje.isoformat(), (hoje + timedelta(days=dias)).isoformat()),
    ).fetchall()
    if not linhas:
        return "📅 Nenhum evento nos próximos 30 dias (ou fontes indisponíveis)."
    icone = {
        "fomc": "🏦",
        "copom": "🇧🇷",
        "payroll": "👷",
        "cpi": "🛒",
        "opep": "🛢️",
        "eleicao": "🗳️",
        "balanco": "🪙",
    }
    partes = ["📅 <b>Agenda (30 dias)</b>"]
    for r in linhas:
        d = datetime.fromisoformat(r["data"])
        partes.append(
            f"{d.strftime('%d/%m')} {icone.get(r['tipo'], '•')} {f.esc(r['titulo'])} — {r['status']}"
        )
    partes.append("Alerta com as probabilidades na véspera de cada evento.")
    return "\n".join(partes)


# ---------- posts do X (módulo 14) ----------


def _pedidos(con: sqlite3.Connection) -> list[dict]:
    from bot.db import ler_texto

    return json.loads(ler_texto(con, "x_pedidos", "[]") or "[]")


def pedir_post(ctx, pedido: dict) -> None:
    """Enfileira um pedido para o Worker escrever (fio, placar da semana)."""
    lista = [p for p in _pedidos(ctx.con) if p["id"] != pedido["id"]] + [pedido]
    lista = lista[-20:]
    guardar_texto(ctx.con, "x_pedidos", json.dumps(lista, ensure_ascii=False))
    if ctx.kv.ativo:
        ctx.kv.gravar("x_pedidos", lista)


def publicar_pauta_x(ctx, placar_curto: str) -> None:
    from bot.coleta import carteira_externa
    from bot.saida import pauta_x

    if not ctx.kv.ativo:
        return
    try:
        try:
            auto = carteira_externa.ler(ctx.http)
        except Exception as erro:
            aviso(_log, "posições do alerta-ema indisponíveis", erro=str(erro))
            auto = None  # None = não sei (o Worker não trata como zerada)
        pauta = pauta_x.montar(ctx.con, ctx.cfg, ctx.agora, posicoes_auto=auto, placar_curto=placar_curto)
        ctx.kv.gravar("x_pauta", pauta)
        fio = pauta_x.pedido_fio(ctx.con, ctx.cfg, pauta["destaques"], ctx.agora)
        if fio:
            pedir_post(ctx, fio)
        info(_log, "pauta do X publicada", destaques=len(pauta["destaques"]), grafico=bool(pauta["grafico_png"]),
             posicoes_auto=None if auto is None else len(auto))  # fmt: skip
    except Exception as erro:
        aviso(_log, "pauta do X não publicada", erro=str(erro))


def atualizar_liquidez(ctx) -> None:
    from bot.saida import pauta_x

    auto = {}
    try:
        from bot.coleta import carteira_externa

        auto = carteira_externa.ler(ctx.http)
    except Exception:
        pass
    tickers = sorted(
        set(ctx.cfg.todos_tickers())
        | set(auto)
        | set((ctx.kv.ler("posicoes", {}) or {}) if ctx.kv.ativo else {})
    )
    pauta_x.atualizar_liquidez(ctx.con, tickers, precos.volume_financeiro)
