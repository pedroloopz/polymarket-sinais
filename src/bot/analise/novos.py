"""Módulo 7 — detector de mercado novo."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from bot import formato as f
from bot.analise.mercados import Linha, ativos
from bot.config import Config
from bot.db import iso


def pendentes(con: sqlite3.Connection, cfg: Config, agora: datetime) -> list[Linha]:
    """Mercados vistos pela primeira vez, ainda não avisados e criados recentemente."""
    idade = timedelta(days=cfg.regras.get("novos", {}).get("idade_max_dias", 7))
    ids = {r["id"] for r in con.execute("SELECT id FROM mercados WHERE novo_avisado = 0").fetchall()}
    if not ids:
        return []
    saida = []
    for linha in ativos(con, agora, visto_desde_h=48):
        if linha.id not in ids:
            continue
        if linha.criado_em and agora - linha.criado_em > idade:
            continue
        saida.append(linha)
    return saida


def recentes(con: sqlite3.Connection, agora: datetime, dias: int = 7) -> list[Linha]:
    """Mercados que o bot viu pela primeira vez nos últimos N dias (para o comando /novos)."""
    corte = agora - timedelta(days=dias)
    ids = {
        r["id"]
        for r in con.execute(
            """SELECT id FROM mercados WHERE primeiro_visto >= ? AND novo_avisado = 1
           AND primeiro_visto > (SELECT MIN(primeiro_visto) FROM mercados)""",
            (iso(corte),),
        ).fetchall()
    }
    return [x for x in ativos(con, agora, visto_desde_h=48) if x.id in ids]


def marcar_avisados(con: sqlite3.Connection, ids: list[str] | None = None) -> None:
    if ids is None:
        con.execute("UPDATE mercados SET novo_avisado = 1 WHERE novo_avisado = 0")
    else:
        con.executemany("UPDATE mercados SET novo_avisado = 1 WHERE id = ?", [(i,) for i in ids])
    con.commit()


def mensagem(linhas: list[Linha], cfg: Config) -> str | None:
    if not linhas:
        return None
    partes = ["🆕 <b>Mercados novos na Polymarket</b>"]
    for linha in linhas[:10]:
        tema = cfg.temas.get(linha.tema, {})
        ligados = ", ".join(t.removesuffix(".SA") for t in cfg.ativos_do_tema(linha.tema)) or "—"
        prazo = f"até {f.data(linha.fim)}" if linha.fim else "sem prazo"
        partes.append(
            f'{tema.get("emoji", "•")} <a href="{linha.link}">{f.esc(f.encurtar(linha.pergunta, 90))}</a>\n'
            f"   {f.prob(linha.prob)} | {prazo} | vol. {f.volume(linha.volume)}\n"
            f"   Ativos: {f.esc(f.encurtar(ligados, 80))}"
        )
    if len(linhas) > 10:
        partes.append(f"…e mais {len(linhas) - 10}. Veja /novos.")
    return "\n".join(partes)
