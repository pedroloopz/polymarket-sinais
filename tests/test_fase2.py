"""Fase 2: calibração, sinais, semáforo, risco, acompanhamento, trava e placar semanal (sem rede)."""

import json
import math
import sqlite3
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from bot import db
from bot.analise import acompanhamento, calibracao, protecao, risco, semaforo, sinais
from bot.db import iso
from bot.diario import placar
from bot.diario.registro import Sinal, registrar

# Terça 06/10/2026 15:00 UTC = 11:00 em Nova York (pregão aberto)
AGORA = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)


# ---------- helpers ----------


def _mercado(
    con, mid="m1", tema="ira", volume=5e6, prob=0.78, fim="2026-12-31T00:00:00+00:00", pergunta=None
):
    con.execute(
        """INSERT INTO mercados (id, tema, pergunta, token_sim, fim, primeiro_visto, ultimo_visto, volume, prob)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            mid,
            tema,
            pergunta or "US x Iran ceasefire by December 31?",
            f"tok-{mid}",
            fim,
            iso(AGORA - timedelta(days=10)),
            iso(AGORA),
            volume,
            prob,
        ),
    )
    con.commit()


def _serie(con, tipo, chave, pontos):
    con.executemany(
        "INSERT OR REPLACE INTO series (ts, tipo, chave, valor) VALUES (?, ?, ?, ?)",
        [(iso(ts), tipo, chave, v) for ts, v in pontos],
    )
    con.commit()


def _hist_calmo(token, inicio, fim, fidelidade):
    """30 dias de histórico horário com ruído pequeno (desvio do log-odds ≈ 0,02)."""
    if fidelidade == 1:  # histórico por minuto, para a latência: movimento há 10 min
        return [(int((AGORA - timedelta(minutes=10)).timestamp()), 0.78)]
    rng = np.random.default_rng(0)
    ts = range(inicio, fim, 3600)
    lo = np.cumsum(rng.normal(0, 0.02, len(ts)))
    return [(t, float(1 / (1 + math.exp(-x)))) for t, x in zip(ts, lo, strict=False)]


def _ohlc(_):
    idx = pd.bdate_range(end="2026-10-05", periods=30)
    return pd.DataFrame({"High": 90.5, "Low": 90.0, "Close": 90.2}, index=idx)


def _cenario_movimento(con, reverter=False):
    _mercado(con)
    base = AGORA - timedelta(hours=2)
    p_final = 0.64 if reverter else 0.78
    _serie(con, "mercado", "m1", [(base, 0.62), (base + timedelta(hours=1), 0.78), (AGORA, p_final)])
    # ativo e indicadores: XLE caiu 0,6%, Brent −2,1%, VIX −4%
    _serie(con, "ativo", "XLE", [(base, 90.65), (AGORA, 90.10)])
    _serie(con, "ativo", "BZ=F", [(base, 70.0), (AGORA, 70.0 * 0.979)])
    _serie(con, "ativo", "^VIX", [(base, 20.0), (AGORA, 19.2)])


def _calibrar_xle(con, defasagem=120, beta=-1.5, t=-5.0):
    con.execute(
        """INSERT INTO calibracao (mercado_id, ativo, tema, ts, defasagem_min, correlacao, beta_10pp, t_beta, n,
           volume, score) VALUES ('m1', 'XLE', 'ira', ?, ?, -0.3, ?, ?, 900, 5e6, 1.0)""",
        (iso(AGORA), defasagem, beta, t),
    )
    con.commit()


@pytest.fixture
def con(tmp_path):
    c = db.conectar(tmp_path / "f2.sqlite")
    yield c
    c.close()


# ---------- módulo 2 ----------


def _sintetico(lag_barras=3, beta_frac=-0.15):
    rng = np.random.default_rng(1)
    dias = pd.bdate_range("2026-09-01", periods=22, tz="UTC")
    idx = pd.DatetimeIndex(
        [
            d + pd.Timedelta(hours=13, minutes=30) + pd.Timedelta(minutes=5 * i)
            for d in dias
            for i in range(78)
        ]
    )
    dp = np.where(rng.random(len(idx)) < 0.08, rng.normal(0, 0.02, len(idx)), 0.0)
    p = pd.Series(np.clip(0.5 + np.cumsum(dp), 0.05, 0.95), index=idx)
    r = np.zeros(len(idx))
    r[lag_barras:] = beta_frac * np.diff(np.r_[0.5, p.values])[:-lag_barras]
    r += rng.normal(0, 0.001, len(idx))
    return p, pd.Series(100 * np.exp(np.cumsum(r)), index=idx)


def test_calibracao_recupera_defasagem_e_beta():
    p, preco = _sintetico()
    defasagem, corr, beta, t, n = calibracao.calibrar_par(p, preco)
    assert defasagem == 15  # 3 barras de 5 min: a Polymarket anda antes
    assert beta == pytest.approx(-1.5, abs=0.1)  # % do ativo por +10 p.p.
    assert corr < 0 and abs(t) > 2 and n > 1000


def test_calibracao_sem_relacao_nao_confirma():
    p, _ = _sintetico()
    ruido = pd.Series(
        100 * np.exp(np.cumsum(np.random.default_rng(9).normal(0, 0.001, len(p)))), index=p.index
    )
    _, _, _, t, _ = calibracao.calibrar_par(p, ruido)
    assert abs(t) < 3


def test_calibrar_grava_e_ranking(con, cfg):
    _mercado(con, prob=0.5)
    p, preco = _sintetico()

    def obter_prob(token, inicio, fim, fid):
        return [(int(ts.timestamp()), float(v)) for ts, v in p.items()]

    def obter_barras(tickers, dias, intervalo):
        return pd.DataFrame({t: preco for t in tickers})

    pares = calibracao.calibrar(con, cfg, AGORA, obter_prob, obter_barras)
    assert pares and all(x.mercado_id == "m1" for x in pares)
    assert con.execute("SELECT COUNT(*) FROM calibracao").fetchone()[0] == len(pares)
    texto = calibracao.texto_ranking(con, cfg)
    assert "📊" in texto and "XLE" in texto and "+15 min" in texto


# ---------- módulo 4 ----------


def test_semaforo():
    esperados = {"BZ=F": -1, "^VIX": -1}
    assert semaforo.avaliar({"BZ=F": -0.021, "^VIX": -0.04}, esperados, +1)[0] == "🟢"
    assert semaforo.avaliar({"BZ=F": 0.0, "^VIX": 0.0}, esperados, +1)[0] == "🟡"
    assert semaforo.avaliar({"BZ=F": 0.02, "^VIX": 0.03}, esperados, +1)[0] == "🔴"
    # prob caiu: o esperado se inverte
    assert semaforo.avaliar({"BZ=F": 0.02, "^VIX": 0.03}, esperados, -1)[0] == "🟢"
    cor, detalhe = semaforo.avaliar({"BZ=F": -0.021}, esperados, +1)
    assert "Brent −2,1%" in detalhe


# ---------- módulos 11 e 11b ----------


def test_atr_e_plano():
    assert risco.atr(_ohlc(None), 14) == pytest.approx(0.5)
    plano = risco.montar_plano(
        entrada=90.10, sentido=-1, espaco=-0.018, atr_valor=0.5, regras={"risco": {}},
        capital_moeda_ativo=10_000, defasagem_min=120,
        fim_pregao=datetime(2026, 10, 6, 20, 0, tzinfo=UTC), agora=AGORA,
    )  # fmt: skip
    assert plano.stop == pytest.approx(90.85)
    assert plano.alvo == pytest.approx(90.10 * (1 - 0.018))
    assert plano.ganho_risco == pytest.approx(90.10 * 0.018 / 0.75)
    assert plano.quantidade == 110  # 1% de 10.000 ÷ risco de 0,75 por ação... limitado pelo capital
    assert plano.stop_tempo == AGORA + timedelta(minutes=240)


def test_pregao_aberto():
    pregoes = {"EUA": {"fuso": "America/New_York", "abre": "09:30", "fecha": "16:00"}}
    assert risco.pregao_aberto(pregoes, "EUA", AGORA)
    assert not risco.pregao_aberto(pregoes, "EUA", AGORA.replace(hour=23))
    assert not risco.pregao_aberto(pregoes, "EUA", datetime(2026, 10, 10, 15, tzinfo=UTC))  # sábado


# ---------- módulo 3 ----------


def test_detecta_movimento_persistente(con, cfg):
    _cenario_movimento(con)
    cands = sinais.detectar(con, cfg, AGORA, _hist_calmo)
    assert len(cands) == 1
    c = cands[0]
    assert c.dp == pytest.approx(0.16) and c.z > 2


def test_movimento_devolvido_nao_vira_sinal(con, cfg):
    _cenario_movimento(con, reverter=True)
    assert sinais.detectar(con, cfg, AGORA, _hist_calmo) == []


def test_sem_historico_sem_sinal(con, cfg):
    _cenario_movimento(con)
    assert sinais.detectar(con, cfg, AGORA, lambda *a: []) == []


def test_sinal_acionavel_com_plano_completo(con, cfg):
    _cenario_movimento(con)
    _calibrar_xle(con)
    cfg.regras["risco"]["capital"] = 50_000
    _serie(con, "ativo", "BRL=X", [(AGORA, 5.0)])
    c = sinais.detectar(con, cfg, AGORA, _hist_calmo)[0]
    m = sinais.montar(con, cfg, c, AGORA, obter_hist=_hist_calmo, obter_ohlc=_ohlc)
    assert m.acionavel, m.sinal.detalhes["motivos"]
    s = m.sinal
    assert s.sentido == -1 and s.ativo == "XLE" and s.urgencia == "🚨" and s.semaforo == "🟢"
    assert s.esperado == pytest.approx(-0.024)
    assert s.latencia_s == pytest.approx(600)
    for trecho in (
        "🚨 SINAL",
        "🔻 SHORT XLE",
        "🎯 Alvo: US$",
        "🛑 Stop: US$",
        "Ganho/risco",
        "⏱️ Sair até",
        "Esperado −2,4% | realizado −0,6%",
        "Latência do alerta: 10 min",
        "não recomendação",
    ):
        assert trecho in m.texto, trecho
    sid = registrar(con, s)
    linha = con.execute("SELECT * FROM sinais WHERE id = ?", (sid,)).fetchone()
    assert linha["status"] == "aberto" and linha["acionavel"] == 1 and linha["alvo_parcial"]


def test_sem_calibracao_vira_informativo(con, cfg):
    _cenario_movimento(con)
    c = sinais.detectar(con, cfg, AGORA, _hist_calmo)[0]
    m = sinais.montar(con, cfg, c, AGORA, obter_hist=_hist_calmo, obter_ohlc=_ohlc)
    assert not m.acionavel and m.sinal.urgencia == "📋"
    assert "par ainda não calibrado" in m.sinal.detalhes["motivos"]
    assert m.sinal.sentido == -1  # hipótese: XLE − quando a paz sobe


def test_defasagem_curta_para_a_latencia(con, cfg):
    _cenario_movimento(con)
    _calibrar_xle(con, defasagem=15)  # 15 min < 3 × 10 min de latência
    c = sinais.detectar(con, cfg, AGORA, _hist_calmo)[0]
    m = sinais.montar(con, cfg, c, AGORA, obter_hist=_hist_calmo, obter_ohlc=_ohlc)
    assert not m.acionavel
    assert any("latência" in x for x in m.sinal.detalhes["motivos"])


def test_pregao_fechado_e_gap(con, cfg):
    _cenario_movimento(con)
    _calibrar_xle(con)
    noite = AGORA.replace(hour=23)
    c = sinais.detectar(con, cfg, AGORA, _hist_calmo)[0]
    m = sinais.montar(con, cfg, c, noite, obter_hist=_hist_calmo, obter_ohlc=_ohlc)
    assert not m.acionavel
    assert any("gap esperado na abertura" in x for x in m.sinal.detalhes["motivos"])


def test_trava_bloqueia_acionavel(con, cfg):
    _cenario_movimento(con)
    _calibrar_xle(con)
    c = sinais.detectar(con, cfg, AGORA, _hist_calmo)[0]
    m = sinais.montar(con, cfg, c, AGORA, obter_hist=_hist_calmo, obter_ohlc=_ohlc, pausado=True)
    assert not m.acionavel


# ---------- acompanhamento e trava ----------


def _sinal_aberto(con, **kw):
    base = dict(
        ts=AGORA,
        tema="ira",
        ativo="XLE",
        sentido=-1,
        entrada=90.10,
        mercado_id="m1",
        stop=90.85,
        alvo=88.48,
        alvo_parcial=89.29,
        acionavel=True,
        p_base=0.62,
        p_sinal=0.78,
        stop_tempo=AGORA + timedelta(hours=4),
        detalhes={"pergunta": "Iran?"},
    )
    base.update(kw)
    return registrar(con, Sinal(**base))


def test_acompanha_parcial_e_stop(con, cfg):
    _mercado(con)
    _serie(con, "mercado", "m1", [(AGORA, 0.78)])
    sid = _sinal_aberto(con)
    _serie(con, "ativo", "XLE", [(AGORA + timedelta(hours=1), 89.20)])
    ev = acompanhamento.acompanhar(con, cfg.regras, AGORA + timedelta(hours=1))
    assert [e.tipo for e in ev] == ["parcial"]
    _serie(con, "ativo", "XLE", [(AGORA + timedelta(hours=2), 91.0)])
    ev = acompanhamento.acompanhar(con, cfg.regras, AGORA + timedelta(hours=2))
    assert [e.tipo for e in ev] == ["stop"] and ev[0].urgencia == "🚨"
    linha = con.execute("SELECT status, resultado FROM sinais WHERE id = ?", (sid,)).fetchone()
    assert linha["status"] == "stop" and linha["resultado"] < 0


def test_invalidacao_pela_probabilidade(con, cfg):
    _mercado(con)
    _sinal_aberto(con)
    _serie(con, "ativo", "XLE", [(AGORA + timedelta(hours=1), 90.0)])
    _serie(con, "mercado", "m1", [(AGORA + timedelta(hours=1), 0.66)])  # devolveu 75% do movimento
    ev = acompanhamento.acompanhar(con, cfg.regras, AGORA + timedelta(hours=1))
    assert [e.tipo for e in ev] == ["invalidado"]
    assert "❌ Sinal invalidado — sair" in ev[0].texto


def test_stop_de_tempo(con, cfg):
    _mercado(con)
    _serie(con, "mercado", "m1", [(AGORA, 0.78)])
    _sinal_aberto(con)
    depois = AGORA + timedelta(hours=5)
    _serie(con, "ativo", "XLE", [(depois, 90.0)])
    _serie(con, "mercado", "m1", [(depois, 0.78)])
    assert [e.tipo for e in acompanhamento.acompanhar(con, cfg.regras, depois)] == ["tempo"]


def test_trava_apos_duas_perdas(con, cfg):
    for i in range(2):
        sid = _sinal_aberto(con, ts=AGORA + timedelta(minutes=i))
        con.execute(
            "UPDATE sinais SET status='stop', resultado=-0.01, fechado_em=? WHERE id=?",
            (iso(AGORA + timedelta(hours=i + 1)), sid),
        )
    con.commit()
    msg = protecao.verificar(con, cfg.regras, AGORA + timedelta(hours=3))
    assert msg and "Trava ligada" in msg
    assert protecao.pausado_ate(con, AGORA + timedelta(hours=4))
    assert protecao.verificar(con, cfg.regras, AGORA + timedelta(hours=4)) is None  # não repete
    assert protecao.pausado_ate(con, AGORA + timedelta(hours=30)) is None


# ---------- placar semanal e migração ----------


def test_placar_semanal(con):
    for i, r in enumerate([0.01, -0.005, 0.02]):
        sid = _sinal_aberto(con, ts=AGORA - timedelta(days=2, hours=i), semaforo=["🟢", "🟡", "🟢"][i])
        con.execute("INSERT INTO avaliacoes VALUES (?, '1d', ?, 1, ?, ?)", (sid, iso(AGORA), r, r))
    con.commit()
    texto = placar.semanal(con, AGORA)
    assert "Placar da semana" in texto and "Por tema" in texto and "Por semáforo" in texto
    assert "3 | 67% acerto" in texto
    assert placar.AVISO_AMOSTRA in texto


def test_migracao_do_banco_da_fase_1(tmp_path):
    caminho = tmp_path / "antigo.sqlite"
    antigo = sqlite3.connect(caminho)
    antigo.execute("""CREATE TABLE sinais (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, tema TEXT NOT NULL,
        mercado_id TEXT, ativo TEXT NOT NULL, sentido INTEGER NOT NULL, entrada REAL NOT NULL, stop REAL, alvo REAL,
        semaforo TEXT, manipulacao TEXT, urgencia TEXT, acionavel INTEGER DEFAULT 0, latencia_s REAL, detalhes TEXT)""")
    antigo.commit()
    antigo.close()
    con = db.conectar(caminho)
    colunas = {r[1] for r in con.execute("PRAGMA table_info(sinais)")}
    assert {"status", "alvo_parcial", "stop_tempo", "resultado", "avisos"} <= colunas
    registrar(con, Sinal(ts=AGORA, tema="ira", ativo="XLE", sentido=1, entrada=1.0))
    assert json.loads(con.execute("SELECT avisos FROM sinais").fetchone()[0]) == []


def test_calibracao_sem_dados_preserva_a_anterior(con, cfg):
    _mercado(con, prob=0.5)
    _calibrar_xle(con)
    with pytest.raises(RuntimeError):
        calibracao.calibrar(con, cfg, AGORA, lambda *a: [], lambda t, d, i: pd.DataFrame())
    assert con.execute("SELECT COUNT(*) FROM calibracao").fetchone()[0] == 1
