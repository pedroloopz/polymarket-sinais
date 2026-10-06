from datetime import UTC, datetime

from bot import formato as f


def test_numeros_brasileiros():
    assert f.numero(1234.56) == "1.234,56"
    assert f.dinheiro(1234.56, "BRL") == "R$ 1.234,56"
    assert f.dinheiro(1234.56, "USD") == "US$ 1.234,56"
    assert f.dinheiro(-5, "BRL") == "−R$ 5,00"
    assert f.pct(0.125) == "12,5%"
    assert f.pct(0.021, sinal=True) == "+2,1%"
    assert f.pct(-0.021) == "−2,1%"


def test_probabilidade_e_pontos():
    assert f.prob(0.91) == "91%"
    assert f.prob(0.004) == "<1%"
    assert f.prob(0.996) == ">99%"
    assert f.prob(None) == "—"
    assert f.pp(-0.02) == "−2,0 p.p."
    assert f.pp(0.015) == "+1,5 p.p."
    assert f.pp(0.0) == "0,0 p.p."


def test_volume_compacto():
    assert f.volume(1_234_567) == "US$ 1,2 mi"
    assert f.volume(2_500_000_000) == "US$ 2,5 bi"
    assert f.volume(45_000) == "US$ 45 mil"


def test_datas_no_fuso_de_sao_paulo():
    dt = datetime(2026, 10, 6, 2, 30, tzinfo=UTC)  # 23:30 de 05/10 em Brasília
    assert f.data(dt) == "05/10"
    assert f.hora(dt) == "23:30"
    assert f.data_hora(dt) == "05/10 23:30"


def test_escape_html():
    assert f.esc("A < B & C") == "A &lt; B &amp; C"
