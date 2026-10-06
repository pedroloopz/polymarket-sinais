"""Módulo 14 (lado Python): a "pauta" dos posts do X, publicada no KV para o Worker escrever.

Hora a hora: destaques (maiores movimentos de 24 h entre os mercados líquidos), dados de apoio
(Kalshi, nota de manipulação), gráfico PNG de 7 dias com marca d'água, liquidez dos ativos e as
posições automáticas (alerta-ema). Pedidos pontuais (fio em evento grande, placar da semana) vão
para "x_pedidos". Quem escreve o texto é o Worker (Claude), nos horários configurados.
"""

from __future__ import annotations

import base64
import io
import sqlite3
from datetime import datetime, timedelta

from bot import formato as f
from bot.analise import manipulacao
from bot.analise.mercados import ativos
from bot.config import Config
from bot.db import iso
from bot.logs import aviso, log

_log = log("pauta_x")


def destaques(con: sqlite3.Connection, cfg: Config, agora: datetime, n: int = 5) -> list[dict]:
    vol_min = cfg.regras.get("filtros", {}).get("volume_min_sinal_usd", 0)
    linhas = [
        x for x in ativos(con, agora)
        if x.volume >= vol_min and not x.palavras_ditas and x.var_24h is not None and x.prob is not None
    ]  # fmt: skip
    linhas.sort(key=lambda x: abs(x.var_24h), reverse=True)
    saida = []
    for x in linhas[:n]:
        nota = manipulacao.ler(con, x.id)
        kal = con.execute("SELECT prob FROM kalshi_pares WHERE mercado_id = ?", (x.id,)).fetchone()
        tema = cfg.temas.get(x.tema, {})
        saida.append({
            "id": x.id, "tema": x.tema, "tema_nome": tema.get("nome", x.tema), "emoji": tema.get("emoji", ""),
            "pergunta": x.pergunta, "item": x.item, "prob": round(x.prob, 4), "var_24h_pp": round(x.var_24h * 100, 1),
            "volume_usd": round(x.volume), "kalshi": round(kal["prob"], 4) if kal and kal["prob"] is not None else None,
            "manipulacao": nota.nota if nota else None, "criterios_manipulacao": nota.criterios if nota else [],
            "ativos_ligados": [t.removesuffix(".SA") for t in cfg.ativos_do_tema(x.tema)][:8],
            "link": x.link,
        })  # fmt: skip
    return saida


def grafico(con: sqlite3.Connection, destaque: dict, agora: datetime, perfil: str) -> str | None:
    """PNG (base64) da probabilidade em 7 dias, com marca d'água do perfil."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except Exception as erro:
        aviso(_log, "matplotlib indisponível", erro=str(erro))
        return None
    inicio = int((agora - timedelta(days=7)).timestamp())
    pontos = con.execute(
        "SELECT t, p FROM hist_mercado WHERE mercado_id = ? AND t >= ? ORDER BY t", (destaque["id"], inicio)
    ).fetchall()
    serie = [(datetime.fromtimestamp(r["t"], tz=agora.tzinfo), r["p"]) for r in pontos]
    serie += [
        (datetime.fromisoformat(r["ts"]), r["valor"])
        for r in con.execute(
            "SELECT ts, valor FROM series WHERE tipo='mercado' AND chave=? AND ts >= ? AND valor IS NOT NULL",
            (destaque["id"], iso(agora - timedelta(days=7))),
        ).fetchall()
    ]
    serie.sort()
    if len(serie) < 2:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=120)
    fig.patch.set_facecolor("#0f1115")
    ax.set_facecolor("#0f1115")
    ax.plot([t for t, _ in serie], [p * 100 for _, p in serie], color="#f5a623", linewidth=2.2)
    ax.fill_between([t for t, _ in serie], [p * 100 for _, p in serie], color="#f5a623", alpha=0.12)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color("#555")
    ax.tick_params(colors="#bbb")
    ax.grid(axis="y", color="#333", linewidth=0.6)
    titulo = f.encurtar(destaque["pergunta"], 70)
    ax.set_title(
        f"{titulo}\nPolymarket — agora {f.prob(destaque['prob'])}", color="white", fontsize=11, loc="left"
    )
    fig.text(0.98, 0.03, f"Termômetro do Caos · {perfil}", color="#888", fontsize=10, ha="right")
    fig.text(0.5, 0.5, perfil, color="white", fontsize=40, ha="center", va="center", alpha=0.06, rotation=20)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def liquidez(con: sqlite3.Connection) -> dict[str, float]:
    """Volume financeiro médio diário por ticker (cache diário em textos.liquidez)."""
    import json

    from bot.db import ler_texto

    return json.loads(ler_texto(con, "liquidez", "{}") or "{}")


def atualizar_liquidez(con: sqlite3.Connection, tickers: list[str], obter_volume) -> dict[str, float]:
    """`obter_volume(tickers) -> {ticker: volume financeiro médio de 20 dias}`."""
    import json

    from bot.db import guardar_texto

    try:
        dados = obter_volume(tickers)
    except Exception as erro:
        aviso(_log, "liquidez indisponível", erro=str(erro))
        return liquidez(con)
    guardar_texto(con, "liquidez", json.dumps(dados))
    return dados


def pedido_fio(con: sqlite3.Connection, cfg: Config, dest: list[dict], agora: datetime) -> dict | None:
    """Evento grande (|Δ 24 h| ≥ 15 p.p. num mercado líquido) pede um fio, no máximo 1 por mercado/dia."""
    limite = cfg.regras.get("x", {}).get("fio_min_pp", 15)
    for d in dest:
        if abs(d["var_24h_pp"]) < limite:
            continue
        chave = f"fio:{d['id']}:{f.local(agora).date().isoformat()}"
        ja = con.execute("SELECT 1 FROM textos WHERE chave = ?", (chave,)).fetchone()
        if ja:
            continue
        con.execute("INSERT INTO textos (chave, valor, ts) VALUES (?, '1', ?)", (chave, iso(agora)))
        con.commit()
        return {"id": chave, "tipo": "fio", "dados": d}
    return None


def montar(
    con: sqlite3.Connection,
    cfg: Config,
    agora: datetime,
    *,
    posicoes_auto: dict[str, dict] | None,
    placar_curto: str,
) -> dict:
    rx = cfg.regras.get("x", {})
    perfil = rx.get("perfil", "@pedroloopz")
    dest = destaques(con, cfg, agora)
    png = grafico(con, dest[0], agora, perfil) if dest else None
    return {
        "versao": 1,
        "gerado_em": iso(agora),
        "perfil": perfil,
        "destaques": dest,
        "grafico_png": png,
        "grafico_de": dest[0]["id"] if (dest and png) else None,
        "placar": placar_curto,
        "liquidez": liquidez(con),
        "liquidez_min": rx.get("liquidez_min_diaria", 5_000_000),
        "posicoes_auto": posicoes_auto,
        "x": {
            "horarios": rx.get("horarios", ["08:30", "10:20", "18:30"]),
            "modelo": rx.get("modelo", "claude-opus-5-5"),
            "effort": rx.get("effort", "low"),
            "virada_z_min": rx.get("virada_z_min", 3),
        },
    }


def resumo_engajamento(registros: list[dict]) -> str:
    """Placar dos posts: quais formatos, ganchos e horários performam melhor (módulo 14)."""
    if not registros:
        return ""

    def media(grupo: list[dict]) -> float:
        return sum(r.get("curtidas", 0) + 2 * r.get("reposts", 0) for r in grupo) / len(grupo)

    partes = ["\n📣 <b>Engajamento no X</b> (curtidas + 2× reposts)"]
    for campo, titulo in (("formato", "formato"), ("gancho", "tipo de gancho"), ("horario", "horário")):
        grupos: dict[str, list[dict]] = {}
        for r in registros:
            grupos.setdefault(str(r.get(campo) or "—"), []).append(r)
        if grupos:
            melhor = max(grupos.items(), key=lambda kv: media(kv[1]))
            partes.append(
                f"• Melhor {titulo}: {f.esc(melhor[0])} (média {f.numero(media(melhor[1]), 0)}, {len(melhor[1])} posts)"
            )
    topo = max(registros, key=lambda r: r.get("curtidas", 0) + 2 * r.get("reposts", 0))
    partes.append(f"• Post campeão: {f.esc(f.encurtar(topo.get('texto', ''), 80))}")
    return "\n".join(partes)
