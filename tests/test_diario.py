from datetime import timedelta

import pytest

from bot.db import iso
from bot.diario import avaliacao, placar
from bot.diario.registro import Sinal, registrar
from tests.conftest import AGORA


def _preco(con, ts, ativo, valor):
    con.execute(
        "INSERT INTO series (ts, tipo, chave, valor) VALUES (?, 'ativo', ?, ?)", (iso(ts), ativo, valor)
    )
    con.commit()


def test_retorno_short_desconta_custo():
    bruto, liquido = avaliacao.retorno(-1, 100.0, 98.0, custo_pct=0.2)
    assert bruto == pytest.approx(0.02)
    assert liquido == pytest.approx(0.018)


def test_sentido_invalido(con):
    with pytest.raises(ValueError):
        registrar(con, Sinal(ts=AGORA, tema="ira", ativo="XLE", sentido=0, entrada=1))


def test_avaliacao_por_horizonte(con):
    sid = registrar(con, Sinal(ts=AGORA, tema="ira", ativo="XLE", sentido=-1, entrada=90.0))
    _preco(con, AGORA + timedelta(hours=1, minutes=7), "XLE", 89.0)
    _preco(con, AGORA + timedelta(days=1, minutes=7), "XLE", 91.0)
    feitas = avaliacao.avaliar_pendentes(con, AGORA + timedelta(days=2), custo_pct=0.2)
    assert feitas == 2  # 1h e 1d; 1w ainda não venceu
    linhas = {r["horizonte"]: r for r in con.execute("SELECT * FROM avaliacoes WHERE sinal_id=?", (sid,))}
    assert linhas["1h"]["retorno_liquido"] > 0
    assert linhas["1d"]["retorno_liquido"] < 0
    # Rodar de novo não duplica.
    assert avaliacao.avaliar_pendentes(con, AGORA + timedelta(days=2), custo_pct=0.2) == 0


def test_placar_com_aviso_de_amostra(con):
    for i, saida in enumerate([91.0, 89.0, 88.0]):
        t = AGORA + timedelta(hours=i)
        registrar(con, Sinal(ts=t, tema="ira", ativo="XLE", sentido=1, entrada=90.0))
        _preco(con, t + timedelta(days=1), "XLE", saida)
    avaliacao.avaliar_pendentes(con, AGORA + timedelta(days=3), custo_pct=0.2)
    p = placar.calcular(con, AGORA + timedelta(days=3))
    assert (p.sinais, p.avaliados, p.acertos, p.pior_sequencia) == (3, 3, 1, 2)
    assert placar.AVISO_AMOSTRA in placar.texto(p)
    assert "(amostra insuficiente)" in placar.linha_resumo(p)
