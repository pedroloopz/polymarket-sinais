"""Mensagens claras: tradução, polaridade e jogada (long/short por setor)."""

import json

from bot.analise import jogada, sinais
from bot.coleta import traducao
from bot.coleta.coletor import coletar
from bot.coleta.polymarket_clob import Clob
from bot.coleta.polymarket_gamma import Gamma
from bot.saida import resumo
from tests.conftest import AGORA, cotacoes_falsas
from tests.test_fase2 import _calibrar_xle, _cenario_movimento, _hist_calmo, _ohlc


def _tradutor(polaridade=1):
    chamadas = []

    def chamar(sistema, conteudo, opcoes):
        chamadas.append(conteudo)
        itens = json.loads(conteudo.split("\n", 1)[1])
        return json.dumps({
            "itens": [
                {"id": i["id"], "pergunta_pt": f"PT: {i['pergunta']}", "item_pt": "", "titulo_pt": "",
                 "polaridade": polaridade}
                for i in itens
            ]
        })  # fmt: skip

    return chamar, chamadas


def test_traducao_grava_uma_vez_e_aparece_nas_telas(con, cfg, http):
    coletar(con, cfg, Gamma(http), Clob(http), cotacoes_falsas, AGORA)
    chamar, chamadas = _tradutor()
    n, estado = traducao.traduzir(con, cfg, AGORA, chamar)
    assert n > 0 and estado == "ok" and "Irã" in chamadas[0]  # leva o nome e o "evento" do tema
    assert traducao.traduzir(con, cfg, AGORA, chamar)[0] == 0  # não traduz de novo
    texto = resumo.texto_tema(con, cfg, "ira", AGORA)
    assert "PT: US x Iran ceasefire" in texto
    assert "📈 <b>Se a chance SOBE</b>: paz mais provável" in texto
    assert "🟢 LONG aéreas: UAL, DAL, JETS" in texto
    assert "🔴 SHORT petróleo: XLE, USO, APA" in texto


def test_sem_chave_nao_traduz(con, cfg, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    n, estado = traducao.traduzir(con, cfg, AGORA)
    assert n == 0 and estado.startswith("sem chave")


def test_falha_da_api_nao_derruba(con, cfg, http):
    coletar(con, cfg, Gamma(http), Clob(http), cotacoes_falsas, AGORA)

    def quebrado(*_):
        raise RuntimeError("fora do ar")

    n, estado = traducao.traduzir(con, cfg, AGORA, quebrado)
    assert n == 0 and estado.startswith("falhou")


def test_jogada_inverte_com_polaridade(cfg):
    a_favor = jogada.montar(None, cfg, "ira", direcao=1, polaridade=1)
    contra = jogada.montar(None, cfg, "ira", direcao=1, polaridade=-1)
    assert a_favor.longs[0][0] == "aéreas" and contra.shorts[0][0] == "aéreas"
    assert "paz" in a_favor.por_que and "guerra" in contra.por_que
    assert jogada.montar(None, cfg, "ira", polaridade=0).vazia


def test_pergunta_contra_o_tema_inverte_o_sinal(con, cfg):
    _cenario_movimento(con)  # chance sobe 62% → 78%
    con.execute(
        "INSERT INTO traducoes (mercado_id, pergunta_pt, polaridade) VALUES ('m1', 'EUA atacam o Irã?', -1)"
    )
    c = sinais.detectar(con, cfg, AGORA, _hist_calmo)[0]
    m = sinais.montar(con, cfg, c, AGORA, obter_hist=_hist_calmo, obter_ohlc=_ohlc)
    assert m.sinal.sentido == 1  # guerra mais provável → XLE sobe
    assert "EUA atacam o Irã?" in m.texto
    assert "guerra mais provável" in m.texto
    assert "🟢 LONG XLE" in m.texto


def test_cartao_do_sinal_e_curto(con, cfg):
    _cenario_movimento(con)
    _calibrar_xle(con)
    c = sinais.detectar(con, cfg, AGORA, _hist_calmo)[0]
    m = sinais.montar(con, cfg, c, AGORA, obter_hist=_hist_calmo, obter_ohlc=_ohlc)
    print("\n" + m.texto)
    assert len(m.texto.splitlines()) <= 16
    assert "z =" not in m.texto and "Latência" not in m.texto  # detalhe técnico fica no diário
