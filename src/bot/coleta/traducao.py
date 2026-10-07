"""Tradução das perguntas da Polymarket para o português e polaridade em relação ao tema.

Polaridade: o tema "Irã (paz)" espera que a chance subir signifique paz. Uma pergunta como
"EUA atacam o Irã até dezembro?" anda ao contrário: o "Sim" é guerra. A polaridade (+1 / −1)
corrige o sentido da jogada (long/short) para cada mercado; 0 = sem relação clara (não gera jogada).

Usa a API da Anthropic (Secret ANTHROPIC_API_KEY). Cada mercado é traduzido uma vez só e fica
guardado na tabela `traducoes`. Sem chave, as telas mostram a pergunta original em inglês.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable
from datetime import datetime

from bot.config import Config
from bot.db import iso
from bot.logs import aviso, info, log

_log = log("traducao")

SISTEMA = """Você traduz perguntas de mercados de previsão (Polymarket) para o português do Brasil.
Regras da tradução:
- Curta e natural, como manchete de jornal brasileiro. Até 80 caracteres.
- Mantenha nomes próprios, tickers e números. Datas no formato dd/mm (ex.: "até 31/12").
- "by <data>" = "até <data>". "Will X happen?" = "X vai acontecer?" (ou forma mais natural).
- Termine a pergunta com "?".
- item: nome curto da opção (candidato, faixa, mês). Vazio se não houver.
Polaridade, em relação ao que o tema espera quando a chance SOBE (campo "evento"):
- 1 se o "Sim" da pergunta é esse evento (ou o deixa mais provável).
- -1 se o "Sim" é o oposto (ex.: tema "paz", pergunta "vai haver ataque?").
- 0 se não dá para dizer."""

ESQUEMA = {
    "type": "object",
    "properties": {
        "itens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "pergunta_pt": {"type": "string"},
                    "item_pt": {"type": "string"},
                    "titulo_pt": {"type": "string"},
                    "polaridade": {"type": "integer", "enum": [-1, 0, 1]},
                },
                "required": ["id", "pergunta_pt", "item_pt", "titulo_pt", "polaridade"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["itens"],
    "additionalProperties": False,
}

# (sistema, conteúdo do usuário, configuração) → texto JSON da resposta
Chamar = Callable[[str, str, dict], str]


def pendentes(con: sqlite3.Connection, limite: int) -> list[sqlite3.Row]:
    return con.execute(
        """SELECT m.id, m.tema, m.pergunta, m.item, m.evento_titulo FROM mercados m
           LEFT JOIN traducoes t ON t.mercado_id = m.id
           WHERE m.fechado = 0 AND t.mercado_id IS NULL ORDER BY m.volume DESC LIMIT ?""",
        (limite,),
    ).fetchall()


def _pedido(cfg: Config, lote: list[sqlite3.Row]) -> str:
    itens = []
    for m in lote:
        tema = cfg.temas.get(m["tema"], {})
        itens.append({
            "id": m["id"], "tema": tema.get("nome", m["tema"]), "evento": tema.get("evento", ""),
            "pergunta": m["pergunta"], "item": m["item"] or "", "titulo": m["evento_titulo"] or "",
        })  # fmt: skip
    return "Traduza e classifique estes mercados:\n" + json.dumps(itens, ensure_ascii=False)


def chamar_anthropic(sistema: str, conteudo: str, opcoes: dict) -> str:
    import anthropic

    cliente = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=3)
    modelo = opcoes.get("modelo", "claude-opus-5-5")
    extra: dict = {}
    if not modelo.startswith("claude-haiku"):
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    config_saida: dict = {"format": {"type": "json_schema", "schema": ESQUEMA}}
    if opcoes.get("effort") and not modelo.startswith("claude-haiku"):
        config_saida["effort"] = opcoes["effort"]
    resp = cliente.beta.messages.create(
        model=modelo,
        max_tokens=16000,
        system=sistema,
        messages=[{"role": "user", "content": conteudo}],
        output_config=config_saida,
        **extra,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("tradução recusada pelo modelo")
    return next(b.text for b in resp.content if b.type == "text")


def traduzir(
    con: sqlite3.Connection,
    cfg: Config,
    agora: datetime,
    chamar: Chamar | None = None,
) -> tuple[int, str]:
    """Traduz os mercados ainda sem tradução. Retorna (quantos foram gravados, estado da fonte)."""
    regras = cfg.regras.get("traducao", {})
    if not regras.get("ligada", True):
        return 0, "ok"
    if chamar is None:
        chave = os.getenv("ANTHROPIC_API_KEY", "")
        if not chave or chave == "-":
            return 0, "sem chave: perguntas em inglês (Secret ANTHROPIC_API_KEY)"
        chamar = chamar_anthropic
    estado = "ok"
    fila = pendentes(con, regras.get("max_por_execucao", 60))
    lote_max = regras.get("lote", 20)
    gravados = 0
    for i in range(0, len(fila), lote_max):
        lote = fila[i : i + lote_max]
        try:
            bruto = chamar(SISTEMA, _pedido(cfg, lote), regras)
            itens = json.loads(bruto).get("itens", [])
        except Exception as erro:
            aviso(_log, "tradução falhou; tenta de novo na próxima coleta", erro=str(erro)[:300])
            estado = "falhou (tenta de novo na próxima coleta)"
            break
        ids = {m["id"] for m in lote}
        for it in itens:
            if it.get("id") not in ids or not it.get("pergunta_pt"):
                continue
            pol = it.get("polaridade")
            con.execute(
                """INSERT OR REPLACE INTO traducoes
                   (mercado_id, pergunta_pt, item_pt, titulo_pt, polaridade, modelo, ts)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    it["id"], it["pergunta_pt"].strip(), (it.get("item_pt") or "").strip(),
                    (it.get("titulo_pt") or "").strip(), pol if pol in (-1, 0, 1) else 0,
                    regras.get("modelo", "claude-opus-5-5"), iso(agora),
                ),
            )  # fmt: skip
            gravados += 1
        con.commit()
    if gravados:
        info(_log, "mercados traduzidos", n=gravados)
    return gravados, estado


def polaridade(con: sqlite3.Connection, mercado_id: str) -> int:
    """+1 quando não há tradução (mantém o comportamento antigo); −1/0 quando classificado."""
    linha = con.execute("SELECT polaridade FROM traducoes WHERE mercado_id = ?", (mercado_id,)).fetchone()
    if not linha or linha["polaridade"] is None:
        return 1
    return int(linha["polaridade"])


def pergunta_pt(con: sqlite3.Connection, mercado_id: str, original: str) -> str:
    linha = con.execute("SELECT pergunta_pt FROM traducoes WHERE mercado_id = ?", (mercado_id,)).fetchone()
    return (linha["pergunta_pt"] if linha and linha["pergunta_pt"] else None) or original
