"""Módulo 3 — sinais (com 4 semáforo, 11/11b plano e 12 urgência).

Fluxo a cada coleta horária:
1. Leituras horárias de cada mercado ≥ volume mínimo. Movimento = variação do log-odds
   entre a leitura-base e a leitura seguinte; z = movimento ÷ desvio das variações horárias
   dos últimos 30 dias (histórico da própria Polymarket, guardado em cache).
2. Persistência: o movimento precisa se manter nas N leituras seguintes (≥ 50% dele).
3. Zona distorcida (p < 10% ou > 90%) rebaixa a confiança; queda em mercado "até dd/mm"
   a menos de 3 dias do fim exige z maior (queda natural pelo tempo).
4. Ativo: o melhor par da calibração (módulo 2). Sem calibração confirmada, usa a hipótese
   de ativos.yaml e o sinal é só 📋 informativo (não há beta para calcular alvo).
5. Acionável só se: calibrado, Polymarket anda antes (defasagem > 0), defasagem > 3 × latência,
   ativo ainda não andou o esperado (espaço ≥ 50%), pregão aberto e ganho/risco ≥ 1,5.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from bot import formato as f
from bot.analise import calibracao, manipulacao, risco, semaforo
from bot.config import Config
from bot.db import de_iso, iso, ler_texto
from bot.diario.registro import Sinal
from bot.logs import aviso, log

_log = log("sinais")
ObterHist = Callable[[str, int, int, int], list[tuple[int, float]]]


def logit(p: float) -> float:
    q = min(max(p, 0.005), 0.995)
    return math.log(q / (1 - q))


# ---------- leituras guardadas ----------


def leituras(con: sqlite3.Connection, mercado_id: str, n: int) -> list[tuple[datetime, float]]:
    linhas = con.execute(
        """SELECT ts, valor FROM series WHERE tipo='mercado' AND chave=? AND valor IS NOT NULL
           ORDER BY ts DESC LIMIT ?""",
        (mercado_id, n),
    ).fetchall()
    return [(de_iso(r["ts"]), r["valor"]) for r in reversed(linhas)]


def preco_em(con: sqlite3.Connection, ativo: str, momento: datetime, janela_h: int = 6) -> float | None:
    """Último preço do ativo até `momento` (ou o primeiro logo depois, se não houver antes)."""
    antes = con.execute(
        """SELECT valor FROM series WHERE tipo='ativo' AND chave=? AND ts <= ? AND ts >= ?
           AND valor IS NOT NULL ORDER BY ts DESC LIMIT 1""",
        (ativo, iso(momento), iso(momento - timedelta(hours=janela_h))),
    ).fetchone()
    if antes:
        return antes["valor"]
    depois = con.execute(
        """SELECT valor FROM series WHERE tipo='ativo' AND chave=? AND ts > ? AND ts <= ?
           AND valor IS NOT NULL ORDER BY ts LIMIT 1""",
        (ativo, iso(momento), iso(momento + timedelta(hours=2))),
    ).fetchone()
    return depois["valor"] if depois else None


def variacao_ativo(con: sqlite3.Connection, ativo: str, desde: datetime, ate: datetime) -> float | None:
    a, b = preco_em(con, ativo, desde), preco_em(con, ativo, ate)
    return b / a - 1 if a and b else None


# ---------- desvio horário (cache do histórico da Polymarket) ----------


def desvio_horario(
    con: sqlite3.Connection,
    mercado_id: str,
    token: str,
    agora: datetime,
    obter_hist: ObterHist,
    dias: int = 30,
) -> float | None:
    fim = int(agora.timestamp())
    inicio = fim - dias * 86400
    n = con.execute(
        "SELECT COUNT(*) FROM hist_mercado WHERE mercado_id=? AND t >= ?", (mercado_id, inicio)
    ).fetchone()[0]
    if n < dias * 24 * 0.5:
        try:
            pontos = obter_hist(token, inicio, fim, 60)
            con.executemany(
                "INSERT OR REPLACE INTO hist_mercado (mercado_id, t, p) VALUES (?, ?, ?)",
                [(mercado_id, t, p) for t, p in pontos],
            )
            con.commit()
        except Exception as erro:
            aviso(_log, "histórico para o z-score indisponível", mercado=mercado_id, erro=str(erro))
    linhas = con.execute(
        "SELECT t, p FROM hist_mercado WHERE mercado_id=? AND t >= ? ORDER BY t", (mercado_id, inicio)
    ).fetchall()
    if len(linhas) < 48:
        return None
    variacoes = []
    for a, b in zip(linhas, linhas[1:], strict=False):
        horas = (b["t"] - a["t"]) / 3600
        if 0 < horas <= 6:
            variacoes.append((logit(b["p"]) - logit(a["p"])) / math.sqrt(horas))
    if len(variacoes) < 24:
        return None
    s = float(pd.Series(variacoes).std())
    return s if s > 0 else None


# ---------- detecção ----------


@dataclass
class Candidato:
    mercado: sqlite3.Row
    tema: str
    base_ts: datetime
    p_base: float
    p_movimento: float
    p_agora: float
    ts_movimento: datetime
    z: float
    notas: list[str] = field(default_factory=list)

    @property
    def dp(self) -> float:
        return self.p_agora - self.p_base

    @property
    def sentido_prob(self) -> int:
        return 1 if self.dp > 0 else -1


def detectar(
    con: sqlite3.Connection,
    cfg: Config,
    agora: datetime,
    obter_hist: ObterHist,
    excluir: set[str] | None = None,
) -> list[Candidato]:
    rs = cfg.regras.get("sinais", {})
    n_pers = max(1, int(rs.get("persistencia_leituras", 2)))
    vol_min = cfg.regras.get("filtros", {}).get("volume_min_sinal_usd", 0)
    temas = set(cfg.temas_ligados())
    saida: list[Candidato] = []
    mercados = con.execute(
        """SELECT * FROM mercados WHERE fechado = 0 AND palavras_ditas = 0 AND volume >= ?
           AND token_sim IS NOT NULL AND ultimo_visto >= ?""",
        (vol_min, iso(agora - timedelta(hours=2))),
    ).fetchall()
    for m in mercados:
        if m["tema"] not in temas or m["id"] in (excluir or set()):
            continue
        lt = leituras(con, m["id"], n_pers + 1)
        if len(lt) < n_pers + 1:
            continue
        (base_ts, p_base), (ts_mov, p_mov), (_, p_agora) = lt[0], lt[1], lt[-1]
        if abs(p_mov - p_base) * 100 < rs.get("prefiltro_pp", 1.0):
            continue
        mov = logit(p_mov) - logit(p_base)
        # persistência: todas as leituras depois do movimento mantêm ≥ X% dele, no mesmo sentido
        retido = (
            all((logit(p) - logit(p_base)) / mov >= rs.get("retencao_min", 0.5) for _, p in lt[2:])
            if n_pers > 1
            else True
        )
        if not retido:
            continue
        ja = con.execute(
            "SELECT 1 FROM sinais WHERE mercado_id = ? AND (base_ts = ? OR ts >= ?)",
            (m["id"], iso(base_ts), iso(agora - timedelta(hours=6))),
        ).fetchone()
        if ja:
            continue
        sigma = desvio_horario(
            con, m["id"], m["token_sim"], agora, obter_hist, rs.get("janela_desvio_dias", 30)
        )
        if not sigma:
            continue
        horas = max((ts_mov - base_ts).total_seconds() / 3600, 0.25)
        z = mov / (sigma * math.sqrt(horas))
        z_min = rs.get("zscore_min", 2.0)
        notas = []
        fim = de_iso(m["fim"])
        if fim and fim - agora < timedelta(days=rs.get("prazo_curto_dias", 3)) and mov < 0:
            z_min *= rs.get("prazo_curto_fator_z", 1.5)
            notas.append("prazo curto: queda natural descontada")
        if abs(z) < z_min:
            continue
        saida.append(Candidato(m, m["tema"], base_ts, p_base, p_mov, p_agora, ts_mov, z, notas))
    return saida


# ---------- montagem do sinal ----------


@dataclass
class SinalMontado:
    sinal: Sinal
    texto: str
    acionavel: bool


def _latencia(c: Candidato, agora: datetime, obter_hist: ObterHist) -> float:
    """Segundos entre o movimento na Polymarket (minuto em que fez metade do caminho) e agora."""
    try:
        pontos = obter_hist(c.mercado["token_sim"], int(c.base_ts.timestamp()), int(agora.timestamp()), 1)
        for t, p in pontos:
            if abs(p - c.p_base) >= abs(c.p_movimento - c.p_base) / 2:
                return max(agora.timestamp() - t, 0.0)
    except Exception as erro:
        aviso(_log, "latência estimada pela leitura horária", erro=str(erro))
    # sem histórico por minuto: supõe o movimento no meio da hora
    return (agora - c.ts_movimento).total_seconds() + 1800


def montar(
    con: sqlite3.Connection,
    cfg: Config,
    c: Candidato,
    agora: datetime,
    *,
    obter_hist: ObterHist,
    obter_ohlc: Callable[[str], pd.DataFrame],
    pausado: bool = False,
) -> SinalMontado | None:
    rs, rr = cfg.regras.get("sinais", {}), cfg.regras.get("risco", {})
    t_min = cfg.regras.get("calibracao", {}).get("t_min", 3.3)
    tema = cfg.temas[c.tema]

    # 1) ativo: calibração confirmada > hipótese
    pares = calibracao.confirmados(con, c.mercado["id"], t_min)
    calibrado = bool(pares)
    if calibrado:
        principal, alternativa = pares[0], (pares[1] if len(pares) > 1 else None)
        ativo, beta, defasagem = principal["ativo"], principal["beta_10pp"], principal["defasagem_min"]
        esperado = beta / 100 * (c.dp / 0.10)
        sentido = 1 if esperado > 0 else -1
        alt = None
        if alternativa:
            alt_esp = alternativa["beta_10pp"] * c.dp
            alt = (alternativa["ativo"], 1 if alt_esp > 0 else -1)
    else:
        hipoteses = [(t, s) for t, s in cfg.ativos_do_tema(c.tema).items() if s and t in cfg.ativos]
        if not hipoteses:
            return None
        ativo, s = hipoteses[0]
        sentido = s * c.sentido_prob
        beta = defasagem = esperado = None
        alt = (hipoteses[1][0], hipoteses[1][1] * c.sentido_prob) if len(hipoteses) > 1 else None

    entrada = preco_em(con, ativo, agora, janela_h=72)  # fora do pregão: último fechamento
    if not entrada:
        aviso(_log, "sem preço do ativo; sinal descartado", ativo=ativo)
        return None
    realizado = variacao_ativo(con, ativo, c.base_ts, agora)
    espaco = (esperado - (realizado or 0.0)) if esperado is not None else None

    # 2) semáforo e confiança
    esperados = dict(tema.get("semaforo") or {})
    if esperado is not None:
        esperados[ativo] = 1 if beta > 0 else -1
    variacoes = {t: variacao_ativo(con, t, c.base_ts, agora) for t in esperados}
    cor, detalhe_sem = semaforo.avaliar(
        variacoes, esperados, c.sentido_prob, cfg.regras.get("semaforo", {}).get("limiar_pct", 0.1)
    )
    confianca = cor
    zona = rs.get("zona_distorcida", {})
    if c.p_agora < zona.get("abaixo", 0.1) or c.p_agora > zona.get("acima", 0.9):
        confianca = semaforo.rebaixar(confianca)
        c.notas.append("zona distorcida (viés favorito–azarão)")
    if not calibrado:
        confianca = semaforo.rebaixar(confianca)

    # 3) plano
    bolsa = (cfg.ativos.get(ativo) or cfg.indicadores.get(ativo) or {}).get("bolsa", "EUA")
    aberto = risco.pregao_aberto(cfg.pregoes, bolsa, agora)
    try:
        atr_valor = risco.atr(obter_ohlc(ativo), rr.get("atr_dias", 14))
    except Exception as erro:
        aviso(_log, "ATR indisponível", ativo=ativo, erro=str(erro))
        atr_valor = None
    capital = rr.get("capital")
    moeda = cfg.pregoes.get(bolsa, {}).get("moeda", "USD")
    capital_moeda = None
    if capital:
        cambio = preco_em(con, "BRL=X", agora, janela_h=72)
        capital_moeda = capital if moeda == "BRL" else (capital / cambio if cambio else None)
    plano = risco.montar_plano(
        entrada=entrada, sentido=sentido, espaco=espaco, atr_valor=atr_valor, regras=cfg.regras,
        capital_moeda_ativo=capital_moeda, defasagem_min=defasagem,
        fim_pregao=risco.fim_do_pregao(cfg.pregoes, bolsa, agora) if aberto else None, agora=agora,
    )  # fmt: skip

    # 4) acionável?
    latencia = _latencia(c, agora, obter_hist)
    motivos = []
    if not calibrado:
        motivos.append("par ainda não calibrado")
    else:
        if defasagem <= 0:
            motivos.append("o ativo anda junto ou antes da Polymarket")
        elif defasagem * 60 <= rs.get("latencia_multiplo", 3) * latencia:
            motivos.append(
                f"defasagem ({f.numero(defasagem, 0)} min) curta para a latência "
                f"({f.numero(latencia / 60, 0)} min)"
            )
        if (
            espaco is None
            or espaco * esperado <= 0
            or abs(espaco) < abs(esperado) * rs.get("espaco_minimo_pct_do_esperado", 50) / 100
        ):
            motivos.append("o ativo já andou o esperado")
    if not aberto:
        motivos.append("pregão fechado: gap esperado na abertura")
    if plano is None:
        motivos.append("sem ATR para o stop")
    elif plano.ganho_risco is not None and plano.ganho_risco < rr.get("ganho_risco_min", 1.5):
        motivos.append(f"ganho/risco {f.numero(plano.ganho_risco, 1)} abaixo do mínimo")
    if pausado:
        motivos.append("trava ativa após perdas seguidas")
    nota = manipulacao.ler(con, c.mercado["id"])
    if nota and nota.nota == "🔴":
        motivos.append("risco de manipulação 🔴")
    acionavel = not motivos
    urgencia = ("🚨" if cor == "🟢" else "🔔") if acionavel else "📋"

    sinal = Sinal(
        ts=agora, tema=c.tema, ativo=ativo, sentido=sentido, entrada=entrada, mercado_id=c.mercado["id"],
        stop=plano.stop if plano else None, alvo=plano.alvo if plano else None, semaforo=cor,
        manipulacao=nota.nota if nota else None, urgencia=urgencia, acionavel=acionavel, latencia_s=latencia,
        detalhes={"motivos": motivos, "notas": c.notas, "alternativa": alt, "semaforo": detalhe_sem,
                  "pergunta": c.mercado["pergunta"]},
        confianca=confianca, base_ts=c.base_ts, p_base=c.p_base, p_sinal=c.p_agora, z=c.z,
        alvo_parcial=plano.alvo_parcial if plano else None,
        stop_tempo=plano.stop_tempo if plano else None, esperado=esperado, realizado=realizado,
        defasagem_min=defasagem, beta_10pp=beta, quantidade=plano.quantidade if plano else None,
    )  # fmt: skip
    texto = mensagem(cfg, c, sinal, plano, moeda, alt, detalhe_sem, motivos, nota.texto if nota else "—")
    return SinalMontado(sinal, texto, acionavel)


# ---------- mensagem ----------


def _seta(sentido: int) -> str:
    return "🔺 LONG" if sentido > 0 else "🔻 SHORT"


def mensagem(
    cfg: Config,
    c: Candidato,
    s: Sinal,
    plano: risco.Plano | None,
    moeda: str,
    alt: tuple[str, int] | None,
    detalhe_sem: str,
    motivos: list[str],
    manip: str = "—",
) -> str:
    tema = cfg.temas[c.tema]
    nome = s.ativo.removesuffix(".SA")
    minutos = max((s.ts - c.base_ts).total_seconds() / 60, 1)
    duracao = f"{f.numero(minutos / 60, 0)} h" if minutos >= 90 else f"{f.numero(minutos, 0)} min"
    topo = "🚨 SINAL" if s.urgencia == "🚨" else ("🔔 SINAL" if s.acionavel else "📋 Informativo")
    linhas = [
        f"{topo} — {tema.get('emoji', '')} {f.esc(tema['nome'])}",
        f"{f.esc(f.encurtar(c.mercado['pergunta'], 70))}",
        f"{f.prob(c.p_base)} → {f.prob(c.p_agora)} ({f.pp(c.dp)}, z = {f.numero(c.z, 1)}) em {duracao}",
        f"Semáforo: {s.semaforo} {detalhe_sem}",
    ]
    alt_txt = f" (alt.: {_seta(alt[1])} {alt[0].removesuffix('.SA')})" if alt else ""
    linhas.append(f"{_seta(s.sentido)} {nome}{alt_txt}")
    if plano:
        partes = [f"Entrada ~{f.dinheiro(plano.entrada, moeda)}"]
        if plano.alvo is not None:
            partes.append(
                f"🎯 Alvo: {f.dinheiro(plano.alvo, moeda)} (parcial {f.dinheiro(plano.alvo_parcial, moeda)})"
            )
        linhas.append(" | ".join(partes))
        stop = f"🛑 Stop: {f.dinheiro(plano.stop, moeda)}"
        if plano.ganho_risco is not None:
            stop += f" | Ganho/risco: {f.numero(plano.ganho_risco, 1)}"
        if plano.stop_tempo:
            stop += f" | ⏱️ Sair até {f.hora(plano.stop_tempo)}"
        linhas.append(stop)
    if s.esperado is not None:
        real = s.realizado or 0.0
        linhas.append(
            f"Esperado {f.pct(s.esperado, 1, sinal=True)} | realizado {f.pct(real, 1, sinal=True)} "
            f"→ espaço de {f.pct(s.esperado - real, 1, sinal=True)}"
        )
        linhas.append(f"Defasagem calibrada: {f.numero(s.defasagem_min, 0, sinal=True)} min")
    tamanho = f"Tamanho máx.: {f.numero(cfg.regras.get('risco', {}).get('risco_por_operacao_pct', 1), 1)}% do capital"
    if plano and plano.quantidade is not None:
        tamanho += f" → {plano.quantidade} un. (≈ {f.dinheiro(plano.valor_moeda, moeda)})"
    elif not cfg.regras.get("risco", {}).get("capital"):
        tamanho += " (defina com /capital)"
    linhas.append(f"{tamanho} | Latência do alerta: {f.numero((s.latencia_s or 0) / 60, 0)} min")
    linhas.append(f"Confiança: {s.confianca} | 🕵️ Manipulação: {manip}")
    for nota in c.notas:
        linhas.append(f"ℹ️ {nota}")
    if motivos:
        linhas.append("Por que não é acionável: " + "; ".join(motivos))
    linhas.append("⚠️ Sinal de sistema, não recomendação. Registrado no diário.")
    return "\n".join(linhas)


def linha_curta(cfg: Config, s: Sinal, pergunta: str) -> str:
    tema = cfg.temas.get(s.tema, {})
    tipo = "acionável" if s.acionavel else "informativo"
    return (
        f"{tema.get('emoji', '')} {f.esc(f.encurtar(pergunta, 45))}: {f.pp((s.p_sinal or 0) - (s.p_base or 0))} "
        f"(z {f.numero(s.z or 0, 1)}) → {_seta(s.sentido)} {s.ativo.removesuffix('.SA')} {s.semaforo} ({tipo})"
    )


def texto_recentes(con: sqlite3.Connection, cfg: Config, agora: datetime, limite: int = 10) -> str:
    linhas = con.execute("SELECT * FROM sinais ORDER BY ts DESC LIMIT ?", (limite,)).fetchall()
    if not linhas:
        return "🎯 Nenhum sinal ainda. Eles aparecem quando uma probabilidade se move com z ≥ 2 e se mantém."
    pausa = ler_texto(con, "pausa_ate")
    partes = ["🎯 <b>Últimos sinais</b>"]
    if pausa and (ate := de_iso(pausa)) and ate > agora:
        partes.append(f"⏸️ Trava ligada até {f.data_hora(ate)}")
    status = {"aberto": "⏳", "alvo": "🎯", "stop": "🛑", "tempo": "⏱️", "invalidado": "❌", "encerrado": "📋"}
    for r in linhas:
        tema = cfg.temas.get(r["tema"], {})
        res = f" {f.pct(r['resultado'], 1, sinal=True)}" if r["resultado"] is not None else ""
        tipo = "🎯" if r["acionavel"] else "📋"
        partes.append(
            f"{f.data_hora(de_iso(r['ts']))} {tipo} {tema.get('emoji', '')} {_seta(r['sentido'])} "
            f"{r['ativo'].removesuffix('.SA')} {r['semaforo'] or ''} {status.get(r['status'] or '', '')}{res}"
        )
    partes.append("🎯 acionável · 📋 informativo · ⏳ aberto · 🎯 alvo · 🛑 stop · ⏱️ prazo · ❌ invalidado")
    return "\n".join(partes)
