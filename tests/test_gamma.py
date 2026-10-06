from bot.coleta.polymarket_clob import Clob
from bot.coleta.polymarket_gamma import Gamma, combina_tema, e_palavras_ditas, parse_mercado
from tests.conftest import carregar_fixture


def test_parse_mercado_campos_string_json():
    ev = carregar_fixture("gamma_busca_ira.json")["events"][0]
    m = parse_mercado(ev["markets"][0], ev)
    assert m.id == "m1"
    assert m.token_sim == "tokA"
    assert m.prob_gamma == 0.91
    assert m.volume == 5_200_000
    assert m.fim.day == 12
    assert m.link.endswith("us-iran-ceasefire-oct-12")


def test_parse_mercado_sem_id_e_descartado():
    assert parse_mercado({"question": "x"}) is None


def test_busca_filtra_por_tema_e_fechados(http, cfg):
    mercados = Gamma(http).mercados_do_tema(cfg.temas["ira"])
    ids = [m.id for m in mercados]
    assert ids == ["m1", "m2"]  # m3 fechado, m4 não fala de Irã; ordenado por volume


def test_evento_sem_mercados_busca_detalhe(http, cfg):
    mercados = Gamma(http).mercados_do_tema(cfg.temas["brasil"])
    assert {m.id for m in mercados} == {"m10", "m11", "m12"}
    assert any(c[1].endswith("/events/ev11") for c in http.chamadas)


def test_termos_com_borda_de_palavra(cfg):
    ev = {"id": "e", "title": ""}
    fedex = parse_mercado({"id": "1", "question": "Will FedEx beat earnings?"}, ev)
    fed = parse_mercado({"id": "2", "question": "Fed decision in October: 25 bps cut?"}, ev)
    assert not combina_tema(fedex, cfg.temas["fed"])
    assert combina_tema(fed, cfg.temas["fed"])


def test_palavras_ditas(cfg):
    m = parse_mercado({"id": "1", "question": "Will Coinbase say 'Bitcoin' on the earnings call?"}, {})
    assert e_palavras_ditas(m, cfg.temas["balancos_cripto"])


def test_midpoints_em_lotes(http):
    mids = Clob(http).midpoints(["tokA", "tokB", "tokA", None], lote=1)
    assert mids == {"tokA": 0.905, "tokB": 0.715}
    assert sum(1 for c in http.chamadas if c[0] == "POST") == 2  # duplicado e None ignorados


def test_balancos_so_empresas_de_cripto(cfg):
    tema = cfg.temas["balancos_cripto"]
    fedex = parse_mercado({"id": "1", "question": "Will FedEx (FDX) beat quarterly earnings?"}, {})
    jpm = parse_mercado({"id": "2", "question": "Will JPMorgan Chase (JPM) beat quarterly earnings?"}, {})
    coin = parse_mercado({"id": "3", "question": "Will Coinbase (COIN) beat quarterly earnings?"}, {})
    sem_balanco = parse_mercado({"id": "4", "question": "Will Coinbase list XRP?"}, {})
    assert not combina_tema(fedex, tema)
    assert not combina_tema(jpm, tema)
    assert combina_tema(coin, tema)
    assert not combina_tema(sem_balanco, tema)  # "exigir: earnings"
