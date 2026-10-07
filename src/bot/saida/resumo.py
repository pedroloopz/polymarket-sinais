"""Textos do resumo diário e das telas por tema (usados no Telegram e no painel do Worker).

Formato pensado para ler no celular: primeiro o que dá para operar, depois o mapa
(o que mudou na Polymarket e quem ganha ou perde na bolsa com isso).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from bot import formato as f
from bot.analise import jogada, manipulacao
from bot.analise.mercados import Linha, agrupar_por_evento, ativos
from bot.config import Config

AVISO_SISTEMA = "⚠️ Sinal do sistema, não é recomendação."
LEGENDA = "ℹ️ LONG = comprar (ganha se subir) · SHORT = vender/vendido (ganha se cair)"
MOVIMENTO_MIN = 0.03  # 3 p.p. em 24 h: abaixo disso o mercado aparece como "estável"


def seta_var(var: float | None) -> str:
    """'▲ +16 p.p. em 24 h' | '▼ −3 p.p. em 24 h' | 'estável'."""
    if var is None:
        return "sem histórico de 24 h"
    if abs(var) < MOVIMENTO_MIN:
        return "estável em 24 h"
    return f"{'▲' if var > 0 else '▼'} {f.pp(var)} em 24 h"


def _titulo(grupo: list[Linha], limite: int = 70) -> str:
    if len(grupo) == 1:
        return f.encurtar(grupo[0].pergunta, limite)
    return f.encurtar(grupo[0].evento_titulo or grupo[0].pergunta, limite)


def _risco(con: sqlite3.Connection | None, grupo: list[Linha]) -> str:
    """'⚠️ risco de manipulação 🟡' quando algum mercado do grupo tem nota média ou alta."""
    if con is None:
        return ""
    notas = [n.nota for x in grupo if (n := manipulacao.ler(con, x.id))]
    pior = "🔴" if "🔴" in notas else ("🟡" if "🟡" in notas else "")
    return f"⚠️ risco de manipulação {pior}" if pior else ""


def bloco_grupo(
    con: sqlite3.Connection | None,
    cfg: Config,
    grupo: list[Linha],
    emoji: str,
    volume_min_sinal: float,
) -> list[str]:
    """Bloco de 2–3 linhas do resumo: pergunta, chance e (se mexeu) quem ganha na bolsa."""
    x = grupo[0]
    linhas = [f"{emoji} <b>{f.esc(_titulo(grupo))}</b>"]
    if len(grupo) == 1:
        linhas.append(f"{f.prob(x.prob)} · {seta_var(x.var_24h)}")
    else:
        itens = " · ".join(
            f"{f.esc(f.encurtar(m.item or m.pergunta, 22))} {f.prob(m.prob)}" for m in grupo[:3]
        )
        linhas.append(itens)
    alertas = []
    if sum(m.volume for m in grupo) < volume_min_sinal:
        alertas.append("👁️ pouco volume, só observando")
    if risco := _risco(con, grupo):
        alertas.append(risco)
    if len(grupo) == 1 and x.var_24h is not None and abs(x.var_24h) >= MOVIMENTO_MIN:
        j = jogada.montar(con, cfg, x.tema, 1 if x.var_24h > 0 else -1, x.polaridade, x.id)
        if txt := jogada.linhas(j, compacta=True):
            linhas.append(f"↳ {txt[0]}")
    if alertas:
        linhas.append(" · ".join(alertas))
    return linhas


def blocos_tema(con: sqlite3.Connection, cfg: Config, chave: str, agora: datetime, maximo: int) -> list[str]:
    tema = cfg.temas[chave]
    filtros = cfg.regras.get("filtros", {})
    minimo = filtros.get("volume_min_exibir_usd", 0)
    linhas = [x for x in ativos(con, agora, tema=chave) if x.volume >= minimo and not x.palavras_ditas]
    grupos = agrupar_por_evento(linhas)[:maximo]
    return [
        "\n".join(bloco_grupo(con, cfg, g, tema.get("emoji", "•"), filtros.get("volume_min_sinal_usd", 0)))
        for g in grupos
    ]


# compatibilidade: telas antigas pediam uma linha por grupo
linhas_tema = blocos_tema


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
    hoje: list[str] | None = None,
) -> str:
    por_tema = cfg.regras.get("filtros", {}).get("mercados_por_tema_resumo", 2)
    partes = [f"☀️ <b>Resumo de {f.data(agora)}</b>"]

    partes.append("\n🎯 <b>PARA OPERAR</b>")
    if sinais_acionaveis:
        partes.extend(sinais_acionaveis)
    else:
        partes.append("Nada para operar agora ⏸️ (quando houver, chega na hora como 🚨/🔔)")

    partes.append("\n📊 <b>POLYMARKET — O QUE MUDOU</b>")
    blocos = []
    for chave in cfg.temas_ligados():
        if chave == "balancos_cripto":
            continue
        blocos.extend(blocos_tema(con, cfg, chave, agora, por_tema))
    partes.append("\n\n".join(blocos) if blocos else "Nenhum mercado dos temas acima do volume mínimo.")

    partes.append("\n📅 <b>HOJE</b>")
    partes.append("; ".join(hoje) if hoje else "Nada na agenda.")
    partes.extend(balancos)

    extras = []
    if n_vencendo:
        dias = cfg.regras.get("prazos", {}).get("dias_vencendo", 3)
        extras.append(f"⏳ {n_vencendo} mercado(s) vencem em até {dias} dias — /prazos")
    if n_novos:
        extras.append(f"🆕 {n_novos} mercado(s) novo(s) — /novos")
    if informativos:
        extras.append("👀 Movimentos que não viraram operação:")
        extras.extend(f"• {t}" for t in informativos[:6])
    extras.append(placar)
    for fonte, estado in fontes.items():
        if estado != "ok":
            extras.append(f"⚠️ Fonte {fonte}: {estado}")
    partes.append("")
    partes.extend(extras)
    partes.append(f"\n{LEGENDA}")
    return "\n".join(partes)


def texto_tema(con: sqlite3.Connection, cfg: Config, chave: str, agora: datetime) -> str:
    tema = cfg.temas[chave]
    cabecalho = f"{tema.get('emoji', '')} <b>{f.esc(tema['nome'])}</b>"
    if not tema.get("ligado", True):
        return cabecalho + "\n⏸️ Tema desligado."
    partes = [cabecalho]
    leitura = tema.get("leitura") or {}

    # 1) a regra do tema: o que fazer se a chance sobe / cai
    j_sobe = jogada.montar(None, cfg, chave, 1)
    if leitura.get("sobe"):
        partes.append(f"\n📈 <b>Se a chance SOBE</b>: {f.esc(leitura['sobe'])}")
        partes.extend(jogada.linhas(j_sobe) or ["(sem ativo com sentido definido; espera a calibração)"])
    if leitura.get("cai"):
        partes.append(f"\n📉 <b>Se a chance CAI</b>: {f.esc(leitura['cai'])}")
        partes.extend(jogada.linhas(jogada.montar(None, cfg, chave, -1)) or ["—"])

    # 2) os mercados
    linhas = ativos(con, agora, tema=chave)
    if not linhas:
        partes.append("\nNenhum mercado aberto encontrado na última coleta.")
        return "\n".join(partes)
    partes.append("\n━━━━━━━━━━")
    for n, grupo in enumerate(agrupar_por_evento(linhas)[:6], start=1):
        x = grupo[0]
        titulo = f.esc(_titulo(grupo, 80))
        link = f'<a href="{x.link}">{titulo}</a>' if x.link else titulo
        partes.append(f"\n<b>{n}.</b> {link}")
        if x.palavras_ditas:
            partes.append("🔴 aposta em palavras ditas: nunca gera sinal")
        if len(grupo) == 1:
            partes.append(f"Chance: <b>{f.prob(x.prob)}</b> · {seta_var(x.var_24h)}")
        else:
            for m in grupo[:4]:
                partes.append(f"• {f.esc(f.encurtar(m.item or m.pergunta, 30))}: <b>{f.prob(m.prob)}</b>")
        if len(grupo) == 1 and x.polaridade == -1:
            partes.append("🔄 Pergunta ao contrário do tema: aqui, chance subindo = jogada do 📉")
        elif len(grupo) == 1 and x.polaridade == 0:
            partes.append("❔ Pergunta sem relação clara com o tema: sem jogada automática")
        j = jogada.montar(con, cfg, chave, 1, x.polaridade, x.id)
        for m in j.medidos:
            partes.append(f"📏 Medido: {m}")
        prazo = f"vence {f.data(x.fim)}" if x.fim else "sem prazo"
        detalhes = [prazo, f"volume {f.volume(sum(m.volume for m in grupo))}"]
        kal = con.execute("SELECT prob FROM kalshi_pares WHERE mercado_id = ?", (x.id,)).fetchone()
        if kal and kal["prob"] is not None:
            detalhes.append(f"Kalshi {f.prob(kal['prob'])}")
        partes.append(" · ".join(detalhes))
        nota = manipulacao.ler(con, x.id)
        if nota and nota.nota != "🟢":
            partes.append(f"🕵️ {nota.texto}")
    partes.append(f"\n{LEGENDA}")
    return "\n".join(partes)
