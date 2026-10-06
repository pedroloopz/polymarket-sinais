"""Painel publicado no Cloudflare KV para o Worker responder os comandos na hora.

O Python formata tudo; o Worker só repassa o texto pronto (gasta quase nada de CPU,
o que importa no plano gratuito, que dá 10 ms de CPU por requisição).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from bot import formato as f
from bot.config import Config
from bot.db import iso, ler_texto
from bot.saida.resumo import texto_tema

VERSAO = 1


def montar(
    con: sqlite3.Connection, cfg: Config, agora: datetime, *, fontes: dict[str, str], textos: dict[str, str]
) -> dict:
    temas = {}
    for chave, tema in cfg.temas.items():
        temas[tema.get("comando", chave)] = {
            "chave": chave,
            "nome": tema["nome"],
            "emoji": tema.get("emoji", ""),
            "ligado": bool(tema.get("ligado", True)),
            "texto": texto_tema(con, cfg, chave, agora),
        }
    execucoes = {}
    for tarefa in ("coletar", "resumo", "calibrar", "placar_semanal"):
        linha = con.execute(
            "SELECT fim, status FROM execucoes WHERE tarefa = ? ORDER BY id DESC LIMIT 1", (tarefa,)
        ).fetchone()
        if linha:
            execucoes[tarefa] = {"fim": linha["fim"], "status": linha["status"]}
    return {
        "versao": VERSAO,
        "atualizado_em": iso(agora),
        "atualizado_em_txt": f.data_hora(agora),
        "fontes": fontes,
        "execucoes": execucoes,
        "temas": temas,
        "resumo": textos.get("resumo") or ler_texto(con, "resumo", "Resumo ainda não gerado hoje."),
        "prazos": textos.get("prazos", ""),
        "novos": textos.get("novos") or ler_texto(con, "novos", "🆕 Nenhum mercado novo recente."),
        "balancos": textos.get("balancos") or ler_texto(con, "balancos", "🪙 Balanços ainda não levantados."),
        "placar": textos.get("placar", ""),
        "sinais": textos.get("sinais") or ler_texto(con, "sinais", "🎯 Nenhum sinal ainda."),
        "ranking": textos.get("ranking") or ler_texto(con, "ranking", "📊 Calibração ainda não rodou."),
        "placar_semanal": ler_texto(con, "placar_semanal", ""),
        # Valores em vigor (YAML + Telegram), para o menu /config mostrar o atual.
        "regras": {
            "volume_min_sinal_usd": cfg.regras.get("filtros", {}).get("volume_min_sinal_usd"),
            "zscore_min": cfg.regras.get("sinais", {}).get("zscore_min"),
            "ganho_risco_min": cfg.regras.get("risco", {}).get("ganho_risco_min"),
            "risco_por_operacao_pct": cfg.regras.get("risco", {}).get("risco_por_operacao_pct"),
            "silencio": cfg.regras.get("silencio", {}),
        },
    }


def tamanho(painel: dict) -> int:
    return len(json.dumps(painel, ensure_ascii=False).encode())
