"""Módulo 6 — carteiras vencedoras ("baleias").

Ranking (1×/dia): candidatas = maiores detentores dos mercados dos temas. Para cada uma, as posições
encerradas em mercados de geopolítica, economia e balanços (pelo título). Acerto = parcela com lucro
realizado > 0; só entra quem tem ≥ 20 encerradas. Fica o top 20 (+ as de carteiras_seguidas.yaml).
Alerta (a cada coleta): uma carteira do top 20 abre ou aumenta posição relevante num mercado dos temas.
Observação: a Data API chama de "closed positions" também as vendidas antes da resolução.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from bot import formato as f
from bot.config import Config
from bot.db import iso
from bot.logs import aviso, info, log

_log = log("baleias")
CATEGORIAS = [
    "iran", "israel", "ukraine", "russia", "china", "taiwan", "war", "ceasefire", "peace", "strike", "military",
    "fed", "fomc", "rate", "inflation", "cpi", "recession", "gdp", "tariff", "trade", "election", "president",
    "earnings", "hormuz", "houthi", "oil", "brazil", "nato", "sanction", "nuclear",
]  # fmt: skip


@dataclass
class Carteira:
    endereco: str
    apelido: str
    resolvidos: int
    acerto: float
    pnl: float


def relevante(titulo: str) -> bool:
    t = (titulo or "").lower()
    return any(re.search(rf"\b{c}", t) for c in CATEGORIAS)


def avaliar_carteira(endereco: str, encerradas: list[dict], apelido: str = "") -> Carteira | None:
    rel = [p for p in encerradas if relevante(p.get("title", ""))]
    if not rel:
        return None
    ganhos = [float(p.get("realizedPnl") or 0) for p in rel]
    acerto = sum(1 for g in ganhos if g > 0) / len(ganhos)
    return Carteira(endereco, apelido or endereco[:6] + "…" + endereco[-4:], len(rel), acerto, sum(ganhos))


def ranquear(
    con: sqlite3.Connection,
    cfg: Config,
    agora: datetime,
    obter_holders: Callable[[str], list[dict]],
    obter_encerradas: Callable[[str], list[dict]],
    manuais: list[dict] | None = None,
) -> list[Carteira]:
    rb = cfg.regras.get("baleias", {})
    minimo = rb.get("minimo_resolvidos", 20)
    vol_min = cfg.regras.get("filtros", {}).get("volume_min_sinal_usd", 0)
    mercados = con.execute(
        """SELECT condicao FROM mercados WHERE fechado = 0 AND condicao IS NOT NULL AND volume >= ?
           ORDER BY volume DESC LIMIT ?""",
        (vol_min, rb.get("mercados_amostra", 30)),
    ).fetchall()
    saldo: dict[str, float] = {}
    nomes: dict[str, str] = {}
    for m in mercados:
        try:
            for h in obter_holders(m["condicao"]):
                w = h.get("proxyWallet")
                if w:
                    saldo[w] = saldo.get(w, 0.0) + float(h.get("amount") or 0)
                    nomes[w] = h.get("name") or h.get("pseudonym") or ""
        except Exception as erro:
            aviso(_log, "holders indisponíveis", condicao=m["condicao"], erro=str(erro))
    candidatas = sorted(saldo, key=saldo.get, reverse=True)[: rb.get("candidatas", 60)]
    for manual in manuais or []:
        if manual.get("endereco") and manual["endereco"] not in candidatas:
            candidatas.append(manual["endereco"])
            nomes[manual["endereco"]] = manual.get("apelido", "")

    avaliadas = []
    for w in candidatas:
        try:
            c = avaliar_carteira(w, obter_encerradas(w), nomes.get(w, ""))
        except Exception as erro:
            aviso(_log, "posições encerradas indisponíveis", carteira=w, erro=str(erro))
            continue
        if c and c.resolvidos >= minimo:
            avaliadas.append(c)
    top = sorted(avaliadas, key=lambda c: (c.acerto, c.pnl), reverse=True)[: rb.get("top", 20)]
    if not top:
        return []
    con.execute("DELETE FROM carteiras")
    con.executemany(
        "INSERT INTO carteiras (endereco, apelido, resolvidos, acerto, pnl, ranking, ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (c.endereco, c.apelido, c.resolvidos, c.acerto, c.pnl, i + 1, iso(agora))
            for i, c in enumerate(top)
        ],
    )
    con.commit()
    info(_log, "ranking de carteiras", candidatas=len(candidatas), aprovadas=len(avaliadas), top=len(top))
    return top


def vigiar(
    con: sqlite3.Connection, cfg: Config, agora: datetime, obter_posicoes: Callable[[str], list[dict]]
) -> list[str]:
    """Compara as posições do top 20 com o retrato anterior. Retorna mensagens de alerta."""
    rb = cfg.regras.get("baleias", {})
    minimo_usd = rb.get("alerta_minimo_usd", 5000)
    aumento = rb.get("alerta_aumento_pct", 20) / 100
    mercados = {
        r["condicao"]: r
        for r in con.execute(
            "SELECT * FROM mercados WHERE fechado = 0 AND condicao IS NOT NULL AND ultimo_visto >= ?",
            (iso(agora - timedelta(hours=6)),),
        ).fetchall()
    }
    alertas = []
    for c in con.execute("SELECT * FROM carteiras ORDER BY ranking").fetchall():
        try:
            posicoes = obter_posicoes(c["endereco"])
        except Exception as erro:
            aviso(_log, "posições indisponíveis", carteira=c["endereco"], erro=str(erro))
            continue
        # 1º retrato de uma carteira só registra; alerta a partir do segundo
        tinha_retrato = (
            con.execute(
                "SELECT 1 FROM posicoes_carteiras WHERE endereco = ? LIMIT 1", (c["endereco"],)
            ).fetchone()
            is not None
        )
        for p in posicoes:
            cond, lado = p.get("conditionId"), p.get("outcome") or str(p.get("outcomeIndex"))
            if cond not in mercados:
                continue
            tamanho = float(p.get("currentValue") or 0)
            antes = con.execute(
                "SELECT tamanho FROM posicoes_carteiras WHERE endereco=? AND condicao=? AND lado=?",
                (c["endereco"], cond, lado),
            ).fetchone()
            con.execute(
                "INSERT OR REPLACE INTO posicoes_carteiras (endereco, condicao, lado, tamanho, ts) VALUES (?, ?, ?, ?, ?)",
                (c["endereco"], cond, lado, tamanho, iso(agora)),
            )
            anterior = antes["tamanho"] if antes else None
            novo = anterior is None and tamanho >= minimo_usd
            cresceu = anterior is not None and tamanho - anterior >= max(minimo_usd, anterior * aumento)
            if (novo or cresceu) and tinha_retrato:
                m = mercados[cond]
                tema = cfg.temas.get(m["tema"], {})
                delta = tamanho - (anterior or 0)
                acao = "abriu" if novo else "aumentou"
                alertas.append(
                    f"🐋 <b>Baleia #{c['ranking']}</b> ({f.pct(c['acerto'], 0)} de acerto em {c['resolvidos']} encerrados) "
                    f"{acao} posição em <b>{f.esc(str(lado))}</b>\n"
                    f"{tema.get('emoji', '')} {f.esc(f.encurtar(m['pergunta'], 70))} — agora {f.prob(m['prob'])}\n"
                    f"+{f.volume(delta)} (total {f.volume(tamanho)})"
                )
    con.commit()
    return alertas


def texto(con: sqlite3.Connection) -> str:
    linhas = con.execute("SELECT * FROM carteiras ORDER BY ranking").fetchall()
    if not linhas:
        return "🐋 Ranking de carteiras ainda não calculado (sai no resumo diário)."
    partes = ["🐋 <b>Carteiras vencedoras</b> (geopolítica, economia, balanços)"]
    for c in linhas:
        partes.append(
            f"{c['ranking']}. {f.esc(c['apelido'])} — {f.pct(c['acerto'], 0)} em {c['resolvidos']} | "
            f"lucro {f.dinheiro(c['pnl'], 'USD')}"
        )
    partes.append("Acerto = encerradas com lucro. Alerta quando abrem ou aumentam posição nos temas.")
    return "\n".join(partes)
