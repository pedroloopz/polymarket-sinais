"""Fase 4 (módulo 14): pauta dos posts do X e posições do alerta-ema (sem rede)."""

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest

from bot import db
from bot.coleta import carteira_externa
from bot.db import iso
from bot.saida import pauta_x

AGORA = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)


@pytest.fixture
def con(tmp_path):
    c = db.conectar(tmp_path / "x.sqlite")
    yield c
    c.close()


def _mercado(con, mid, prob, antes, volume=5e6, tema="ira", pergunta="US x Iran ceasefire by December 31?"):
    con.execute(
        """INSERT INTO mercados (id, tema, pergunta, token_sim, fim, primeiro_visto, ultimo_visto, volume, prob,
           evento_slug) VALUES (?, ?, ?, ?, '2026-12-31T00:00:00+00:00', ?, ?, ?, ?, 'slug')""",
        (mid, tema, pergunta, f"t{mid}", iso(AGORA - timedelta(days=9)), iso(AGORA), volume, prob),
    )
    con.executemany(
        "INSERT INTO series (ts, tipo, chave, valor) VALUES (?, 'mercado', ?, ?)",
        [(iso(AGORA - timedelta(hours=24)), mid, antes), (iso(AGORA), mid, prob)],
    )
    con.executemany(
        "INSERT INTO hist_mercado (mercado_id, t, p) VALUES (?, ?, ?)",
        [
            (mid, int((AGORA - timedelta(hours=h)).timestamp()), antes + (prob - antes) * (1 - h / 160))
            for h in range(160, 0, -4)
        ],
    )
    con.commit()


def test_destaques_ordenados_pelo_movimento(con, cfg):
    _mercado(con, "m1", 0.78, 0.62)
    _mercado(con, "m2", 0.30, 0.28, pergunta="Fed decision in October?", tema="fed")
    _mercado(con, "m3", 0.90, 0.50, volume=10_000)  # ilíquido: fora
    dest = pauta_x.destaques(con, cfg, AGORA)
    assert [d["id"] for d in dest] == ["m1", "m2"]
    assert dest[0]["var_24h_pp"] == pytest.approx(16.0) and "XLE" in dest[0]["ativos_ligados"]


def test_grafico_com_marca_dagua(con, cfg):
    _mercado(con, "m1", 0.78, 0.62)
    d = pauta_x.destaques(con, cfg, AGORA)[0]
    png = base64.b64decode(pauta_x.grafico(con, d, AGORA, "@pedroloopz"))
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 10_000


def test_pauta_completa_serializavel(con, cfg):
    _mercado(con, "m1", 0.78, 0.62)
    p = pauta_x.montar(
        con, cfg, AGORA, posicoes_auto={"ABNB": {"lado": "comprado"}}, placar_curto="📒 0 sinais"
    )
    assert p["perfil"] == "@pedroloopz" and p["grafico_de"] == "m1"
    assert p["x"]["horarios"] == ["08:30", "10:20", "18:30"] and p["x"]["modelo"] == "claude-opus-5-5"
    assert len(json.dumps(p)) < 1_000_000
    ids = {e["id"] for e in p["estudos"]}
    assert {"berg2008_74", "snowberg2010"} <= ids and all(
        e["link"].startswith("https://") for e in p["estudos"]
    )
    assert any("curiosidade" in g for g in p["ganchos"])
    assert p["x"]["premium"] is True and p["x"]["tamanho_max"] == 1500
    d = p["destaques"][0]
    assert d["quem_ganha"] and d["quem_perde"] and d["leitura_tema"]


def test_pedido_de_fio_uma_vez_por_dia(con, cfg):
    _mercado(con, "m1", 0.78, 0.62)
    dest = pauta_x.destaques(con, cfg, AGORA)
    pedido = pauta_x.pedido_fio(con, cfg, dest, AGORA)
    assert pedido and pedido["tipo"] == "fio" and pedido["dados"]["id"] == "m1"
    assert pauta_x.pedido_fio(con, cfg, dest, AGORA + timedelta(hours=1)) is None


def test_resumo_de_engajamento():
    regs = [
        {
            "formato": "diario",
            "gancho": "contraste",
            "horario": "08h",
            "curtidas": 50,
            "reposts": 5,
            "texto": "a",
        },
        {
            "formato": "virada",
            "gancho": "numero_choque",
            "horario": "10h",
            "curtidas": 300,
            "reposts": 40,
            "texto": "b",
        },
    ]
    t = pauta_x.resumo_engajamento(regs)
    assert "Melhor formato: virada" in t and "Melhor horário: 10h" in t and "campeão: b" in t
    assert pauta_x.resumo_engajamento([]) == ""


def test_posicoes_do_alerta_ema_sem_quantidade():
    eua = {"ativos": {"ABNB": {"unidades": 6.9, "preco_entrada": 158.31, "data_entrada": "2026-09-25"},
                      "ZERO": {"unidades": 0, "preco_entrada": 1}}}  # fmt: skip
    b3 = {"ativos": {"LREN3": {"qtd": 401, "pm": 11.46, "desde": "2026-09-21"}}}
    pos = {**carteira_externa.converter(eua, "EUA"), **carteira_externa.converter(b3, "B3")}
    assert set(pos) == {"ABNB", "LREN3.SA"}
    assert pos["LREN3.SA"] == {
        "lado": "comprado",
        "preco": 11.46,
        "desde": "2026-09-21",
        "origem": "alerta-ema",
    }
    assert all("qtd" not in v and "unidades" not in v for v in pos.values())
    assert carteira_externa.ler(None, token="") == {}  # sem token: nada
