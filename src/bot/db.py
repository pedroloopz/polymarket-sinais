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

-- Módulo 2: resultado da calibração por par (mercado, ativo).
CREATE TABLE IF NOT EXISTS calibracao (
    mercado_id TEXT NOT NULL,
    ativo TEXT NOT NULL,
    tema TEXT NOT NULL,
    ts TEXT NOT NULL,
    defasagem_min REAL,          -- > 0: a Polymarket anda antes
    correlacao REAL,
    beta_10pp REAL,              -- % do ativo por +10 p.p. na probabilidade
    t_beta REAL,
    n INTEGER,
    volume REAL,
    score REAL,
    PRIMARY KEY (mercado_id, ativo)
);

-- Histórico de preços da Polymarket (cache do /prices-history) para o z-score.
CREATE TABLE IF NOT EXISTS hist_mercado (
    mercado_id TEXT NOT NULL,
    t INTEGER NOT NULL,
    p REAL NOT NULL,
    PRIMARY KEY (mercado_id, t)
);

-- Fase 3 ---------------------------------------------------------------
-- Par Polymarket × Kalshi (mesma pergunta), para a divergência entre plataformas.
CREATE TABLE IF NOT EXISTS kalshi_pares (
    mercado_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    titulo TEXT,
    similaridade REAL,
    prob REAL,
    ts TEXT NOT NULL
);

-- Módulo 5: nota de risco de manipulação por mercado.
CREATE TABLE IF NOT EXISTS manipulacao (
    mercado_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    nota TEXT NOT NULL,           -- 🟢 🟡 🔴
    detalhes TEXT
);

-- Módulo 6: carteiras vencedoras e o último retrato das posições delas.
CREATE TABLE IF NOT EXISTS carteiras (
    endereco TEXT PRIMARY KEY,
    apelido TEXT,
    resolvidos INTEGER,
    acerto REAL,
    pnl REAL,
    ranking INTEGER,
    ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posicoes_carteiras (
    endereco TEXT NOT NULL,
    condicao TEXT NOT NULL,
    lado TEXT,
    tamanho REAL,
    ts TEXT NOT NULL,
    PRIMARY KEY (endereco, condicao, lado)
);

-- Módulo 9: agenda de eventos.
CREATE TABLE IF NOT EXISTS agenda (
    id TEXT PRIMARY KEY,          -- tipo:data
    tipo TEXT NOT NULL,
    titulo TEXT NOT NULL,
    data TEXT NOT NULL,           -- AAAA-MM-DD
    status TEXT NOT NULL,         -- confirmada | estimada
    fonte TEXT,
    temas TEXT,
    avisado INTEGER DEFAULT 0
);

-- Mensagens 🔔 seguradas durante o horário de silêncio.
-- Tradução para o português e polaridade: +1 = "Sim" a favor do tema, -1 = contra, 0 = indefinido.
CREATE TABLE IF NOT EXISTS traducoes (
    mercado_id TEXT PRIMARY KEY,
    pergunta_pt TEXT,
    item_pt TEXT,
    titulo_pt TEXT,
    polaridade INTEGER,
    modelo TEXT,
    ts TEXT
);

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


# Colunas acrescentadas depois da Fase 1: o banco que já existe no branch `dados` é migrado sozinho.
COLUNAS_NOVAS = {
    "mercados": {"condicao": "TEXT"},
    "calibracao": {"estavel": "INTEGER"},
    "sinais": {
        "confianca": "TEXT",
        "status": "TEXT DEFAULT 'aberto'",
        "base_ts": "TEXT",
        "p_base": "REAL",
        "p_sinal": "REAL",
        "z": "REAL",
        "alvo_parcial": "REAL",
        "stop_tempo": "TEXT",
        "esperado": "REAL",
        "realizado": "REAL",
        "defasagem_min": "REAL",
        "beta_10pp": "REAL",
        "quantidade": "REAL",
        "avisos": "TEXT DEFAULT '[]'",
        "fechado_em": "TEXT",
        "resultado": "REAL",
    },
}


def _migrar(con: sqlite3.Connection) -> None:
    for tabela, colunas in COLUNAS_NOVAS.items():
        existentes = {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}
        for nome, tipo in colunas.items():
            if nome not in existentes:
                con.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")
    con.commit()


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
    _migrar(con)
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
