from datetime import UTC, datetime

from bot.config import carregar, mesclar
from bot.http import seguro
from bot.saida.telegram import Telegram, despachar, em_silencio, esvaziar_fila, informativos_pendentes, partir
from tests.conftest import FakeHttp

REGRAS = {"silencio": {"ligado": True, "inicio": "22:00", "fim": "07:00"}}
NOITE = datetime(2026, 10, 7, 2, 0, tzinfo=UTC)  # 23:00 em Brasília
DIA = datetime(2026, 10, 7, 13, 0, tzinfo=UTC)  # 10:00 em Brasília


def test_horario_de_silencio_atravessa_meia_noite():
    assert em_silencio(NOITE, REGRAS)
    assert not em_silencio(DIA, REGRAS)
    assert not em_silencio(NOITE, {"silencio": {"ligado": False}})


def test_urgente_toca_mesmo_no_silencio(con):
    tg = Telegram(FakeHttp(), token="1:abc", chat_id="42")
    assert despachar(con, tg, "🚨 x", "🚨", REGRAS, NOITE) == "enviada"
    assert tg.enviadas[-1]["disable_notification"] is False


def test_normal_vai_para_fila_e_sai_depois(con):
    tg = Telegram(FakeHttp(), token="1:abc", chat_id="42")
    assert despachar(con, tg, "🔔 a", "🔔", REGRAS, NOITE) == "fila"
    assert tg.enviadas == []
    assert esvaziar_fila(con, tg, REGRAS, DIA) == 1
    assert "🔔 a" in tg.enviadas[-1]["text"]
    assert esvaziar_fila(con, tg, REGRAS, DIA) == 0


def test_informativo_so_no_resumo(con):
    tg = Telegram(FakeHttp(), token="1:abc", chat_id="42")
    assert despachar(con, tg, "nota", "📋", REGRAS, DIA) == "resumo"
    assert tg.enviadas == []
    assert informativos_pendentes(con) == ["nota"]
    assert informativos_pendentes(con) == []


def test_mensagem_longa_e_partida():
    texto = "\n".join(f"linha {i} " + "x" * 50 for i in range(200))
    partes = partir(texto, 1000)
    assert all(len(p) <= 1000 for p in partes)
    assert "\n".join(partes) == texto


def test_token_nunca_aparece_em_log():
    assert (
        seguro("https://api.telegram.org/bot123456:AAH-abc_def/sendMessage")
        == "https://api.telegram.org/bot***/sendMessage"
    )


def test_ajustes_do_telegram_vencem_o_yaml():
    cfg = carregar({"regras": {"filtros": {"volume_min_sinal_usd": 5}}, "temas_desligados": ["taiwan"]})
    assert cfg.regras["filtros"]["volume_min_sinal_usd"] == 5
    assert cfg.regras["filtros"]["volume_min_exibir_usd"] == 50000  # o resto continua
    assert "taiwan" not in cfg.temas_ligados()


def test_mesclar_recursivo():
    assert mesclar({"a": {"b": 1, "c": 2}}, {"a": {"b": 9}}) == {"a": {"b": 9, "c": 2}}


def test_ativos_do_tema(cfg):
    ira = cfg.ativos_do_tema("ira")
    assert ira["XLE"] == -1 and ira["UAL"] == 1 and ira["PETR4.SA"] == -1
