"""Textos do resumo diário e das telas por tema (usados no Telegram e no painel do Worker)."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from bot import formato as f
from bot.analise.mercados import Linha, agrupar_por_evento, ativos
from bot.config import Config

AVISO_SISTEMA = "⚠️ Sinal de sistema, não recomendação."


def _rotulo_grupo(grupo: list[Linha]) -> str:
    if len(grupo) == 1:
        return f.encurtar(grupo[0].pergunta, 60)
    return f.encurtar(grupo[0].evento_titulo or grupo[0].pergunta, 45)


def linha_grupo(grupo: list[Linha], emoji: str, volume_min_sinal: float) -> str:
    """Uma linha do resumo. Grupo = mercados do mesmo evento (ex.: candidatos)."""
    vigia = "" if sum(x.volume for x in grupo) >= volume_min_sinal else " 👁️"
    if len(grupo) == 1:
        x = grupo[0]
        var = f" ({f.pp(x.var_24h)})" if x.var_24h is not None else ""
        return f"{emoji} {f.esc(_rotulo_grupo(grupo))}: {f.prob(x.prob)}{var}{vigia}"
    itens = " | ".join(f"{f.esc(f.encurtar(x.item or x.pergunta, 22))}: {f.prob(x.prob)}" for x in grupo[:2])
    return f"{emoji} {f.esc(_rotulo_grupo(grupo))} — {itens}{vigia}"


def linhas_tema(con: sqlite3.Connection, cfg: Config, chave: str, agora: datetime, maximo: int) -> list[str]:
    tema = cfg.temas[chave]
    filtros = cfg.regras.get("filtros", {})
    minimo = filtros.get("volume_min_exibir_usd", 0)
    linhas = [x for x in ativos(con, agora, tema=chave) if x.volume >= minimo and not x.palavras_ditas]
    grupos = agrupar_por_evento(linhas)[:maximo]
    return [linha_grupo(g, tema.get("emoji", "•"), filtros.get("volume_min_sinal_usd", 0)) for g in grupos]


def resumo_diario(
    con: sqlite3.Connection,
    cfg: Config,
    agora: datetime,
    *,
    balancos: list[str],
    n_vencendo: int,
    n_novos: int,
    placar: str,
    sinais_acionaveis: list[str],
    fontes: dict[str, str],
    informativos: list[str] | None = None,
) -> str:
    por_tema = cfg.regras.get("filtros", {}).get("mercados_por_tema_resumo", 2)
    partes = [f"🗓️ <b>{f.data(agora)} — Mercados de previsão</b>"]
    for chave in cfg.temas_ligados():
        if chave == "balancos_cripto":
            continue
        partes.extend(linhas_tema(con, cfg, chave, agora, por_tema))
    if len(partes) == 1:
        partes.append("Nenhum mercado dos temas acima do volume mínimo.")
    partes.extend(balancos)
    if n_vencendo:
        partes.append(
            f"⏳ Vencendo em até {cfg.regras.get('prazos', {}).get('dias_vencendo', 3)} dias: "
            f"{n_vencendo} mercado(s) — /prazos"
        )
    if n_novos:
        partes.append(f"🆕 Mercados novos (24 h): {n_novos} — /novos")
    partes.append("📅 Hoje: — (agenda chega na Fase 3)")
    if sinais_acionaveis:
        partes.append("🎯 Sinais acionáveis: " + "; ".join(sinais_acionaveis))
    else:
        partes.append("🎯 Sinais acionáveis: nenhum ⏸️")
    partes.append(placar)
    for texto in informativos or []:
        partes.append(f"📋 {texto}")
    for fonte, estado in fontes.items():
        if estado != "ok":
            partes.append(f"⚠️ Fonte {fonte}: {estado}")
    return "\n".join(partes)


def texto_tema(con: sqlite3.Connection, cfg: Config, chave: str, agora: datetime) -> str:
    tema = cfg.temas[chave]
    cabecalho = f"{tema.get('emoji', '')} <b>{f.esc(tema['nome'])}</b>"
    if not tema.get("ligado", True):
        return cabecalho + "\n⏸️ Tema desligado."
    linhas = ativos(con, agora, tema=chave)
    if not linhas:
        return cabecalho + "\nNenhum mercado aberto encontrado na última coleta."
    partes = [cabecalho]
    for grupo in agrupar_por_evento(linhas)[:8]:
        x = grupo[0]
        titulo = f.esc(_rotulo_grupo(grupo))
        link = f'<a href="{x.link}">{titulo}</a>' if x.link else titulo
        prazo = f"até {f.data(x.fim)}" if x.fim else "sem prazo"
        vol = f.volume(sum(m.volume for m in grupo))
        aviso = " 🔴 palavras ditas (nunca gera sinal)" if x.palavras_ditas else ""
        partes.append(f"\n• {link}{aviso}\n  {prazo} | vol. {vol}")
        for m in grupo[:4]:
            nome = f.esc(f.encurtar(m.item, 30)) + ": " if len(grupo) > 1 and m.item else ""
            partes.append(f"  {nome}{f.prob(m.prob)} ({f.pp(m.var_24h)} em 24 h)")
    ligados = cfg.ativos_do_tema(chave)
    if ligados:
        seta = {1: "🔺", -1: "🔻", 0: "❔"}
        txt = " ".join(f"{t.removesuffix('.SA')}{seta.get(s, '❔')}" for t, s in ligados.items())
        partes.append(f"\n🔗 Ativos (se a prob. sobe): {txt}")
    partes.append("👁️ = volume abaixo do mínimo para sinal; só monitorado.")
    return "\n".join(partes)
