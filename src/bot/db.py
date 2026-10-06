"""Banco SQLite do histórico (fica no branch `dados`; ver README → Persistência)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS mercados (
    id TEXT PRIMARY KEY,
    tema TEXT NOT NULL,
    evento_id TEXT,
    evento_titulo TEXT,
    pergunta TEXT NOT NULL,
    item TEXT,
    slug TEXT,
    evento_slug TEXT,
    token_sim TEXT,
    fim TEXT,
    criado_em TEXT,
    primeiro_visto TEXT NOT NULL,
    ultimo_visto TEXT NOT NULL,
    volume REAL,
    liquidez REAL,
    prob REAL,
    var_24h_gamma REAL,
    palavras_ditas INTEGER DEFAULT 0,
    fechado INTEGER DEFAULT 0,
    novo_avisado INTEGER DEFAULT 0
);

-- Tabela única de séries temporais: mercados (tipo='mercado') e ativos (tipo='ativo').
CREATE TABLE IF NOT EXISTS series (
    ts TEXT NOT NULL,
    tipo TEXT NOT NULL,
    chave TEXT NOT NULL,
    valor REAL,
    volume REAL,
    liquidez REAL,
    bid REAL,
    ask REAL,
    fonte TEXT,
    ts_fonte TEXT,
    PRIMARY KEY (ts, tipo, chave)
);
CREATE INDEX IF NOT EXISTS ix_series_chave ON series (tipo, chave, ts);

CREATE TABLE IF NOT EXISTS sinais (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    tema TEXT NOT NULL,
    mercado_id TEXT,
    ativo TEXT NOT NULL,
    sentido INTEGER NOT NULL,          -- +1 long, -1 short
    entrada REAL NOT NULL,
    stop REAL,
    alvo REAL,
    semaforo TEXT,
    manipulacao TEXT,
    urgencia TEXT,
    acionavel INTEGER DEFAULT 0,
    latencia_s REAL,
    detalhes TEXT
);

CREATE TABLE IF NOT EXISTS avaliacoes (
    sinal_id INTEGER NOT NULL REFERENCES sinais(id),
    horizonte TEXT NOT NULL,
    ts TEXT NOT NULL,
    preco REAL NOT NULL,
    retorno_bruto REAL NOT NULL,
    retorno_liquido REAL NOT NULL,
    PRIMARY KEY (sinal_id, horizonte)
);

-- Mensagens 🔔 seguradas durante o horário de silêncio.
CREATE TABLE IF NOT EXISTS fila (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    texto TEXT NOT NULL,
    urgencia TEXT NOT NULL,
    enviada INTEGER DEFAULT 0
);

-- Textos prontos reaproveitados entre execuções (ex.: balanços, calculados 1×/dia).
CREATE TABLE IF NOT EXISTS textos (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarefa TEXT NOT NULL,
    inicio TEXT NOT NULL,
    fim TEXT,
    status TEXT,
    fontes TEXT
);
"""


def agora() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def de_iso(texto: str | None) -> datetime | None:
    if not texto:
        return None
    texto = texto.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def conectar(caminho: str | Path) -> sqlite3.Connection:
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(caminho))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    return con


def registrar_execucao(
    con: sqlite3.Connection, tarefa: str, inicio: datetime, status: str, fontes: dict
) -> None:
    con.execute(
        "INSERT INTO execucoes (tarefa, inicio, fim, status, fontes) VALUES (?, ?, ?, ?, ?)",
        (tarefa, iso(inicio), iso(agora()), status, json.dumps(fontes, ensure_ascii=False)),
    )
    con.commit()


def guardar_texto(con: sqlite3.Connection, chave: str, valor: str) -> None:
    con.execute(
        "INSERT OR REPLACE INTO textos (chave, valor, ts) VALUES (?, ?, ?)", (chave, valor, iso(agora()))
    )
    con.commit()


def ler_texto(con: sqlite3.Connection, chave: str, padrao: str = "") -> str:
    linha = con.execute("SELECT valor FROM textos WHERE chave = ?", (chave,)).fetchone()
    return linha["valor"] if linha else padrao


def ultima_execucao(con: sqlite3.Connection, tarefa: str) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM execucoes WHERE tarefa = ? ORDER BY id DESC LIMIT 1", (tarefa,)
    ).fetchone()
