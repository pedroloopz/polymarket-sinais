from datetime import timedelta

from bot.analise import novos, prazos
from bot.coleta.coletor import coletar
from bot.coleta.polymarket_clob import Clob
from bot.coleta.polymarket_gamma import Gamma
from bot.saida import painel, resumo
from tests.conftest import AGORA, FakeHttp, cotacoes_falsas


def _coletar(con, cfg, http, agora=AGORA):
    return coletar(con, cfg, Gamma(http), Clob(http), cotacoes_falsas, agora)


def test_coleta_grava_series_de_mercados_e_ativos(con, cfg, http):
    res = _coletar(con, cfg, http)
    assert res.primeira_coleta
    assert res.fontes["Polymarket Gamma"] == "ok"
    assert res.fontes["Preços (yfinance)"] == "ok"
    linha = con.execute("SELECT valor, fonte FROM series WHERE tipo='mercado' AND chave='m1'").fetchone()
    assert linha["valor"] == 0.905 and linha["fonte"] == "midpoint"
    n_ativos = con.execute("SELECT COUNT(*) FROM series WHERE tipo='ativo'").fetchone()[0]
    assert n_ativos == len(cfg.todos_tickers())
    # Primeira coleta não gera aviso de "novo".
    assert novos.pendentes(con, cfg, AGORA) == []


def test_sem_midpoint_usa_preco_da_gamma(con, cfg):
    res = _coletar(con, cfg, FakeHttp(falhar_clob=True))
    assert res.fontes["Polymarket CLOB"] in ("indisponível", "sem dados")
    linha = con.execute("SELECT valor, fonte FROM series WHERE chave='m1'").fetchone()
    assert linha["valor"] == 0.91 and linha["fonte"] == "gamma"


def test_fonte_fora_do_ar_nao_derruba(con, cfg, http):
    def cotar_quebrado(_):
        raise RuntimeError("Yahoo fora")

    res = coletar(con, cfg, Gamma(http), Clob(http), cotar_quebrado, AGORA)
    assert res.fontes["Preços (yfinance)"] == "indisponível"
    assert res.mercados > 0


def test_detector_de_mercado_novo(con, cfg, http):
    _coletar(con, cfg, http)
    # Mercado novo aparece na coleta seguinte.
    con.execute("DELETE FROM mercados WHERE id='m12'")
    con.commit()
    _coletar(con, cfg, http, AGORA + timedelta(hours=1))
    pend = novos.pendentes(con, cfg, AGORA + timedelta(hours=1))
    assert [x.id for x in pend] == ["m12"]
    texto = novos.mensagem(pend, cfg)
    assert "🆕" in texto and "turnout" in texto
    novos.marcar_avisados(con)
    assert novos.pendentes(con, cfg, AGORA + timedelta(hours=1)) == []


def test_prazos_vencendo(con, cfg, http):
    _coletar(con, cfg, http)
    linhas = prazos.vencendo(con, cfg, AGORA)
    assert [x.id for x in linhas] == ["m12"]  # vence 08/10; os demais vencem depois de 3 dias
    assert "⏳" in prazos.texto(linhas, cfg)


def test_variacao_24h_pela_serie(con, cfg, http):
    _coletar(con, cfg, http, AGORA - timedelta(hours=24))
    con.execute("UPDATE series SET valor = 0.80 WHERE chave = 'm1'")
    con.commit()
    _coletar(con, cfg, http)
    linhas = resumo.linhas_tema(con, cfg, "ira", AGORA, 2)
    assert "90%" in linhas[0] or "91%" in linhas[0]
    assert "+10,5 p.p." in linhas[0]


def test_resumo_diario_formato(con, cfg, http):
    _coletar(con, cfg, http)
    texto = resumo.resumo_diario(
        con,
        cfg,
        AGORA,
        balancos=["🪙 COIN balanço: 29/10 (estimada) — mercado ainda não criado"],
        n_vencendo=1,
        n_novos=0,
        placar="📒 Placar (amostra insuficiente): 0 sinais | nenhum avaliado ainda",
        sinais_acionaveis=[],
        fontes={"Polymarket Gamma": "ok", "Preços (yfinance)": "indisponível"},
    )
    assert texto.startswith("🗓️ <b>06/10 — Mercados de previsão</b>")
    assert "🇮🇷" in texto and "🇧🇷" in texto
    assert "Flávio: 85% | Lula: 16%" in texto  # midpoint 0,155 arredonda para 16%
    assert "🎯 Sinais acionáveis: nenhum ⏸️" in texto
    assert "⚠️ Fonte Preços (yfinance): indisponível" in texto


def test_painel_para_o_worker(con, cfg, http):
    _coletar(con, cfg, http)
    p = painel.montar(con, cfg, AGORA, fontes={"x": "ok"}, textos={"resumo": "R"})
    assert p["resumo"] == "R"
    assert set(p["temas"]) >= {"ira", "brasil", "fed", "taiwan", "cripto", "balancos"}
    assert "Irã" in p["temas"]["ira"]["texto"]
    assert painel.tamanho(p) < 200_000


def test_gamma_fora_do_ar_para_cedo(con, cfg):
    class Quebrado(FakeHttp):
        def get_json(self, url, params=None, cache=True):
            self.chamadas.append(("GET", url, params))
            raise RuntimeError("fora do ar")

    http = Quebrado()
    res = _coletar(con, cfg, http)
    assert res.fontes["Polymarket Gamma"] == "indisponível"
    assert len(http.chamadas) == 2  # parou depois de 2 temas com erro


def test_mercado_vencido_sai_das_telas(con, cfg, http):
    from bot.analise.mercados import ativos

    _coletar(con, cfg, http)
    depois = AGORA + timedelta(days=2)  # m12 venceu em 08/10 03:00 UTC
    assert "m12" in {x.id for x in ativos(con, AGORA, visto_desde_h=72)}
    # Preço em aberto (31%): continua na tela mesmo vencido.
    assert "m12" in {x.id for x in ativos(con, depois, visto_desde_h=72)}
    # Preço decidido (1%): só aguarda resolução, sai da tela.
    con.execute("UPDATE mercados SET prob = 0.01 WHERE id = 'm12'")
    assert "m12" not in {x.id for x in ativos(con, depois, visto_desde_h=72)}
