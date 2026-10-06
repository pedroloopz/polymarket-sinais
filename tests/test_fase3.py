"""Fase 3: manipulação, Kalshi, GDELT, carteiras, agenda e a ponte com o Worker (sem rede)."""

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from bot import db
from bot.analise import baleias, manipulacao, plataformas
from bot.coleta import agenda, gdelt, kalshi
from bot.db import iso
from bot.saida import vigia

AGORA = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)


@pytest.fixture
def con(tmp_path):
    c = db.conectar(tmp_path / "f3.sqlite")
    yield c
    c.close()


def _mercado(
    con,
    mid="m1",
    prob=0.78,
    liquidez=500_000,
    palavras=0,
    condicao="0xabc",
    tema="ira",
    pergunta="US x Iran ceasefire by December 31?",
    fim="2026-12-31T00:00:00+00:00",
    volume=5e6,
):
    con.execute(
        """INSERT INTO mercados (id, tema, pergunta, token_sim, fim, primeiro_visto, ultimo_visto, volume, liquidez,
           prob, palavras_ditas, condicao, evento_titulo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')""",
        (mid, tema, pergunta, f"tok-{mid}", fim, iso(AGORA - timedelta(days=5)), iso(AGORA), volume, liquidez, prob,
         palavras, condicao),
    )  # fmt: skip
    con.commit()
    return con.execute("SELECT * FROM mercados WHERE id = ?", (mid,)).fetchone()


def _serie(con, mid, pontos):
    con.executemany(
        "INSERT OR REPLACE INTO series (ts, tipo, chave, valor, volume) VALUES (?, 'mercado', ?, ?, ?)",
        [(iso(ts), mid, v, vol) for ts, v, vol in pontos],
    )
    con.commit()


# ---------- módulo 5 ----------


def test_concentracao():
    holders = [
        {"proxyWallet": f"w{i}", "amount": a} for i, a in enumerate([500, 300, 100, 50, 20, 10, 10, 10])
    ]
    assert manipulacao.concentracao(holders) == pytest.approx(970 / 1000)
    assert manipulacao.concentracao(holders[:3]) is None  # poucas carteiras


def test_palavras_ditas_sempre_vermelho(con, cfg):
    m = _mercado(con, palavras=1)
    assert manipulacao.avaliar(con, m, AGORA, regras=cfg.regras).nota == "🔴"


def test_nota_limpa(con, cfg):
    m = _mercado(con)
    nota = manipulacao.avaliar(con, m, AGORA, regras=cfg.regras, concentracao_top5=0.3, prob_kalshi=0.76)
    assert nota.nota == "🟢" and nota.criterios == []


def test_nota_com_varios_criterios(con, cfg):
    m = _mercado(con, liquidez=5_000)
    _serie(con, "m1", [(AGORA - timedelta(hours=5), 0.60, 1_000_000), (AGORA - timedelta(hours=1), 0.70, 1_010_000),
                       (AGORA, 0.78, 1_020_000)])  # fmt: skip
    nota = manipulacao.avaliar(con, m, AGORA, regras=cfg.regras, concentracao_top5=0.8, prob_kalshi=0.60,
                               pico_noticias=0.9)  # fmt: skip
    assert nota.nota == "🔴"
    texto = " ".join(nota.criterios)
    for trecho in ("5 carteiras", "Kalshi diverge", "livro raso", "sem pico de notícias", "negociados"):
        assert trecho in texto, trecho
    assert "risco" not in nota.texto.lower() or "manipulado" not in nota.texto.lower()


def test_reversao_rapida(con, cfg):
    m = _mercado(con, prob=0.61)
    _serie(con, "m1", [(AGORA - timedelta(hours=4), 0.60, 1e6), (AGORA - timedelta(hours=2), 0.70, 1.2e6),
                       (AGORA, 0.61, 1.4e6)])  # fmt: skip
    nota = manipulacao.avaliar(con, m, AGORA, regras=cfg.regras)
    assert any("subiu e voltou" in c for c in nota.criterios)


# ---------- Kalshi ----------


def test_kalshi_parse_e_casamento(con):
    ev = {"title": "US-Iran ceasefire"}
    k = kalshi.parse({"ticker": "KXIRAN-26DEC31", "title": "US Iran ceasefire by December 31",
                      "yes_bid_dollars": "0.7200", "yes_ask_dollars": "0.7400",
                      "close_time": "2026-12-31T23:59:00Z", "volume": 1000}, ev)  # fmt: skip
    assert k.prob == pytest.approx(0.73)
    centavos = kalshi.parse({"ticker": "X", "title": "t", "yes_bid": 40, "yes_ask": 44}, {})
    assert centavos.prob == pytest.approx(0.42)
    _mercado(con)
    _mercado(con, mid="m2", pergunta="Will Bitcoin reach $150k by December 31?", tema="btc")
    outro = kalshi.parse({"ticker": "KXFED", "title": "Fed cuts rates in December", "yes_bid": 10, "yes_ask": 12,
                          "close_time": "2026-12-31T00:00:00Z"}, {})  # fmt: skip
    assert plataformas.casar(con, [k, outro], AGORA, volume_min=0) == 1
    assert plataformas.prob_kalshi(con, "m1", AGORA) == pytest.approx(0.73)
    assert plataformas.prob_kalshi(con, "m2", AGORA) is None


# ---------- GDELT ----------


def test_gdelt_pico():
    pontos = [(AGORA - timedelta(hours=h), 0.1) for h in range(7 * 24, 6, -1)]
    pontos += [(AGORA - timedelta(hours=h), 0.4) for h in range(5, -1, -1)]
    assert gdelt.pico(pontos, AGORA) == pytest.approx(4.0)
    assert gdelt.consulta_do_tema({"incluir": ["iran", "red sea"]}) == '(iran OR "red sea")'


# ---------- módulo 6 ----------


def test_carteira_avaliada_so_em_mercados_relevantes():
    encerradas = (
        [{"title": "Will Iran strike Israel by June?", "realizedPnl": 100}] * 15
        + [{"title": "US x Iran ceasefire by July?", "realizedPnl": -50}] * 10
        + [{"title": "Will Taylor Swift marry?", "realizedPnl": 999}] * 30
    )
    c = baleias.avaliar_carteira("0x1234567890", encerradas)
    assert c.resolvidos == 25 and c.acerto == pytest.approx(0.6)


def test_ranking_e_alerta_de_baleia(con, cfg):
    _mercado(con)
    holders = lambda cond: [{"proxyWallet": "0xbaleia", "amount": 1e6, "name": "Baleia"}]  # noqa: E731
    encerradas = lambda w: [{"title": "Fed decision in March?", "realizedPnl": 10}] * 25  # noqa: E731
    top = baleias.ranquear(con, cfg, AGORA, holders, encerradas)
    assert [c.endereco for c in top] == ["0xbaleia"]
    assert "Baleia" in baleias.texto(con)

    posicoes = [{"conditionId": "0xabc", "outcome": "Yes", "currentValue": 20_000}]
    assert baleias.vigiar(con, cfg, AGORA, lambda w: posicoes) == []  # 1º retrato: sem alerta
    posicoes[0]["currentValue"] = 40_000
    alertas = baleias.vigiar(con, cfg, AGORA + timedelta(hours=1), lambda w: posicoes)
    assert len(alertas) == 1 and "aumentou" in alertas[0] and "Yes" in alertas[0]


# ---------- módulo 9 ----------

FED_HTML = """<div><h4><a>2026 FOMC Meetings</a></h4>
<div class="fomc-meeting"><div class="fomc-meeting__month"><strong>September</strong></div>
<div class="fomc-meeting__date">15-16*</div></div>
<div class="fomc-meeting"><div class="fomc-meeting__month"><strong>October</strong></div>
<div class="fomc-meeting__date">27-28</div></div>
<div class="fomc-meeting"><div class="fomc-meeting__month"><strong>December</strong></div>
<div class="fomc-meeting__date">8-9*</div></div>
<h4><a>2027 FOMC Meetings</a></h4>
<div class="fomc-meeting__month"><strong>Jan/Feb</strong></div><div class="fomc-meeting__date">31-1</div></div>"""

BLS_HTML = """<table><tr><th>Reference Month</th><th>Release Date</th><th>Release Time</th></tr>
<tr><td>Sept. 2026</td><td>Oct. 02, 2026</td><td>08:30 AM</td></tr>
<tr><td>Oct. 2026</td><td>Nov. 06, 2026</td><td>08:30 AM</td></tr></table>"""


def test_parsers_oficiais():
    assert agenda.fomc(FED_HTML) == [
        date(2026, 9, 16),
        date(2026, 10, 28),
        date(2026, 12, 9),
        date(2027, 2, 1),
    ]
    assert agenda.bls(BLS_HTML) == [date(2026, 10, 2), date(2026, 11, 6)]


def test_buscar_agenda_com_fonte_fora():
    def pagina(url):
        if "federalreserve" in url:
            return FED_HTML
        raise RuntimeError("403")

    eventos, fontes = agenda.buscar(pagina, date(2026, 10, 6))
    assert fontes["Agenda FOMC"] == "ok"
    assert fontes["Agenda Payroll (EUA)"] == "indisponível"
    tipos = {e.tipo for e in eventos}
    assert {"fomc", "copom", "eleicao"} <= tipos  # Copom e eleição vêm de config/agenda.yaml
    assert all(e.data >= date(2026, 10, 6) for e in eventos)


# ---------- ponte com o Worker ----------


def test_ingerir_eventos_do_worker(con, cfg):
    _mercado(con)
    rt = {
        "atualizado_em": iso(AGORA),
        "eventos": [
            {"seq": 1, "tipo": "sinal", "linha": "📋 linha curta",
             "sinal": {"ts": iso(AGORA), "tema": "ira", "ativo": "XLE", "sentido": -1, "entrada": 90.1,
                       "mercado_id": "m1", "urgencia": "📋", "acionavel": False, "p_base": 0.6, "p_sinal": 0.78}},
            {"seq": 2, "tipo": "sinal",
             "sinal": {"ts": iso(AGORA), "tema": "ira", "ativo": "UAL", "sentido": 1, "entrada": 50.0,
                       "mercado_id": "m1", "urgencia": "🚨", "acionavel": True}},
            {"seq": 3, "tipo": "fechamento", "ref": "rt-2", "status": "alvo", "resultado": 0.012, "ts": iso(AGORA)},
            {"seq": 4, "tipo": "segurada", "texto": "🔔 segurada no silêncio"},
        ],
    }  # fmt: skip
    seguradas, ack = vigia.ingerir(con, cfg, rt, AGORA)
    assert ack == 4 and seguradas == ["🔔 segurada no silêncio"]
    linhas = con.execute("SELECT ativo, status, resultado, detalhes FROM sinais ORDER BY id").fetchall()
    assert [(r["ativo"], r["status"]) for r in linhas] == [("XLE", "aberto"), ("UAL", "alvo")]
    assert json.loads(linhas[1]["detalhes"])["origem"] == "worker"
    assert con.execute("SELECT texto FROM fila WHERE urgencia='📋'").fetchone()["texto"] == "📋 linha curta"
    # reprocessar não duplica
    assert vigia.ingerir(con, cfg, rt, AGORA) == ([], 4)
    assert con.execute("SELECT COUNT(*) FROM sinais").fetchone()[0] == 2


def test_worker_vivo():
    assert vigia.worker_vivo({"atualizado_em": iso(AGORA - timedelta(minutes=6))}, AGORA)
    assert not vigia.worker_vivo({"atualizado_em": iso(AGORA - timedelta(hours=1))}, AGORA)
    assert not vigia.worker_vivo(None, AGORA)


def test_montar_vigia(con, cfg):
    import math

    import numpy as np
    import pandas as pd

    _mercado(con, prob=0.6)
    con.execute(
        """INSERT INTO calibracao (mercado_id, ativo, tema, ts, defasagem_min, correlacao, beta_10pp, t_beta, n,
           volume, score, estavel) VALUES ('m1', 'XLE', 'ira', ?, 45, -0.2, -1.5, -5, 900, 5e6, 1.0, 1)""",
        (iso(AGORA),),
    )
    con.commit()

    def hist(token, inicio, fim, fid):
        lo = np.cumsum(np.random.default_rng(0).normal(0, 0.02, (fim - inicio) // 3600))
        return [(inicio + i * 3600, float(1 / (1 + math.exp(-x)))) for i, x in enumerate(lo)]

    ohlc = pd.DataFrame(
        {"High": 90.5, "Low": 90.0, "Close": 90.2}, index=pd.bdate_range(end="2026-10-05", periods=30)
    )
    v = vigia.montar(con, cfg, AGORA, obter_hist=hist, obter_ohlc=lambda t: ohlc, pausado_ate=None)
    assert len(v["mercados"]) == 1
    m = v["mercados"][0]
    assert m["par"]["ativo"] == "XLE" and m["par"]["atr"] == pytest.approx(0.5) and m["sigma_h"] > 0
    assert m["semaforo"] == {"BZ=F": -1, "^VIX": -1}
    assert v["regras"]["zscore_min"] == 2.0 and "EUA" in v["pregoes"]
    json.dumps(v)  # serializável para o KV
