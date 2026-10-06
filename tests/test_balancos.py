from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from bot.analise import balancos
from tests.conftest import AGORA

NY = ZoneInfo("America/New_York")


def _fechamentos():
    dias = pd.bdate_range("2026-07-27", "2026-08-07")
    return pd.Series(range(100, 100 + len(dias)), index=dias, dtype=float)


def test_dia_de_reacao_depois_do_fechamento():
    idx = pd.DatetimeIndex(_fechamentos().index)
    # Divulgou quinta 30/07 às 16:05 NY → reage sexta 31/07.
    assert balancos.dia_de_reacao(datetime(2026, 7, 30, 16, 5, tzinfo=NY), idx) == pd.Timestamp("2026-07-31")
    # Antes da abertura (07:00) → reage no mesmo dia.
    assert balancos.dia_de_reacao(datetime(2026, 7, 30, 7, 0, tzinfo=NY), idx) == pd.Timestamp("2026-07-30")
    # Sexta depois do fechamento → segunda.
    assert balancos.dia_de_reacao(datetime(2026, 7, 31, 16, 30, tzinfo=NY), idx) == pd.Timestamp("2026-08-03")


def test_reacoes_historicas():
    serie = _fechamentos()
    momentos = [datetime(2026, 7, 30, 16, 5, tzinfo=NY), datetime(2026, 8, 4, 7, 0, tzinfo=NY)]
    r = balancos.reacoes(momentos, serie, n=8)
    assert [d for d, _ in r] == [date(2026, 8, 4), date(2026, 7, 30)]
    assert all(v > 0 for _, v in r)


def test_levantar_e_textos(con, cfg):
    def datas(ticker):
        idx = pd.DatetimeIndex(
            [datetime(2026, 10, 29, 16, 5, tzinfo=NY), datetime(2026, 7, 30, 16, 5, tzinfo=NY)]
        )
        return pd.DataFrame({"EPS Estimate": [1.0, 0.9], "Reported EPS": [None, 1.1]}, index=idx)

    def calendario(ticker):
        if ticker == "COIN":
            return {"Earnings Date": [date(2026, 10, 14)]}
        return {"Earnings Date": [date(2026, 10, 28), date(2026, 11, 3)]}

    def historico(tickers):
        s = _fechamentos()
        return pd.DataFrame({t: s for t in tickers})

    lista = balancos.levantar(con, cfg, AGORA, datas, calendario, historico)
    coin = next(b for b in lista if b.ticker == "COIN")
    assert coin.status == "confirmada" and coin.proxima.day == 14
    assert coin.reacoes and coin.reacoes[0][0] == date(2026, 7, 30)
    mstr = next(b for b in lista if b.ticker == "MSTR")
    assert mstr.status == "estimada"

    linhas = balancos.no_resumo(lista, cfg, AGORA)
    assert len(linhas) == 1 and linhas[0].startswith("🪙 COIN balanço: 14/10 (confirmada) ⏳ 8 d")
    completo = balancos.texto_completo(lista, AGORA)
    assert balancos.LEMBRETE in completo


def test_dias_ate_usa_data_de_ny():
    b = balancos.Balanco("COIN", proxima=datetime(2026, 10, 7, tzinfo=NY))
    assert b.dias_ate(datetime(2026, 10, 6, 23, 0, tzinfo=UTC)) == 1
