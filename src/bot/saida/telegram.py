"""Envio para o Telegram (Bot API) com níveis de urgência e horário de silêncio (módulo 12).

🚨 urgente: toca a qualquer hora.
🔔 normal: toca fora do silêncio; durante o silêncio fica na fila e sai depois.
📋 informativo: não é enviado sozinho, só aparece no resumo.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, time

from bot import formato as f
from bot.db import iso
from bot.http import Http
from bot.logs import aviso, log

API = "https://api.telegram.org"
LIMITE = 4000  # o Telegram aceita 4096 caracteres por mensagem
_log = log("telegram")


def _hhmm(texto: str) -> time:
    h, m = texto.split(":")
    return time(int(h), int(m))


def em_silencio(agora: datetime, regras: dict) -> bool:
    cfg = regras.get("silencio", {})
    if not cfg.get("ligado", True):
        return False
    inicio, fim = _hhmm(cfg.get("inicio", "22:00")), _hhmm(cfg.get("fim", "07:00"))
    t = f.local(agora).time()
    if inicio <= fim:
        return inicio <= t < fim
    return t >= inicio or t < fim


def partir(texto: str, limite: int = LIMITE) -> list[str]:
    """Quebra em pedaços ≤ limite, preferindo quebras de linha."""
    if len(texto) <= limite:
        return [texto]
    partes, atual = [], ""
    for linha in texto.split("\n"):
        while len(linha) > limite:
            if atual:
                partes.append(atual)
                atual = ""
            partes.append(linha[:limite])
            linha = linha[limite:]
        if len(atual) + len(linha) + 1 > limite:
            partes.append(atual)
            atual = linha
        else:
            atual = f"{atual}\n{linha}" if atual else linha
    if atual:
        partes.append(atual)
    return partes


class Telegram:
    def __init__(
        self, http: Http | None = None, token: str | None = None, chat_id: str | None = None
    ) -> None:
        self.token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "")
        self.http = http or Http(tentativas=3)
        self.enviadas: list[dict] = []  # útil para testes e para o log

    @property
    def ativo(self) -> bool:
        return bool(self.token and self.chat_id)

    def enviar(self, texto: str, silencioso: bool = False, botoes: list[list[dict]] | None = None) -> bool:
        ok = True
        pedacos = partir(texto)
        for i, pedaco in enumerate(pedacos):
            corpo = {
                "chat_id": self.chat_id,
                "text": pedaco,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "disable_notification": silencioso,
            }
            if botoes and i == len(pedacos) - 1:
                corpo["reply_markup"] = {"inline_keyboard": botoes}
            self.enviadas.append(corpo)
            if not self.ativo:
                aviso(_log, "Telegram não configurado; mensagem só no log", texto=pedaco[:500])
                continue
            try:
                self.http.post_json(f"{API}/bot{self.token}/sendMessage", corpo)
            except Exception as erro:
                ok = False
                # Nunca logar a URL: ela contém o token.
                aviso(_log, "falha ao enviar mensagem", erro=str(erro).replace(self.token, "***"))
        return ok


def despachar(
    con: sqlite3.Connection,
    tg: Telegram,
    texto: str,
    urgencia: str,
    regras: dict,
    agora: datetime,
    botoes: list[list[dict]] | None = None,
) -> str:
    """Envia ou enfileira conforme a urgência. Retorna 'enviada', 'fila' ou 'resumo'."""
    if urgencia == "🚨":
        tg.enviar(texto, silencioso=False, botoes=botoes)
        return "enviada"
    if urgencia == "📋":
        con.execute("INSERT INTO fila (ts, texto, urgencia) VALUES (?, ?, ?)", (iso(agora), texto, "📋"))
        con.commit()
        return "resumo"
    if em_silencio(agora, regras):
        con.execute("INSERT INTO fila (ts, texto, urgencia) VALUES (?, ?, ?)", (iso(agora), texto, "🔔"))
        con.commit()
        return "fila"
    tg.enviar(texto, silencioso=False, botoes=botoes)
    return "enviada"


def esvaziar_fila(con: sqlite3.Connection, tg: Telegram, regras: dict, agora: datetime) -> int:
    """Fora do silêncio, entrega as mensagens 🔔 seguradas (numa mensagem só)."""
    if em_silencio(agora, regras):
        return 0
    linhas = con.execute(
        "SELECT id, ts, texto FROM fila WHERE enviada = 0 AND urgencia = '🔔' ORDER BY id"
    ).fetchall()
    if not linhas:
        return 0
    texto = "🌙 <b>Seguradas durante o silêncio</b>\n\n" + "\n\n".join(r["texto"] for r in linhas)
    tg.enviar(texto, silencioso=True)
    con.executemany("UPDATE fila SET enviada = 1 WHERE id = ?", [(r["id"],) for r in linhas])
    con.commit()
    return len(linhas)


def informativos_pendentes(con: sqlite3.Connection, marcar: bool = True) -> list[str]:
    """Mensagens 📋 que só aparecem no resumo diário."""
    linhas = con.execute(
        "SELECT id, texto FROM fila WHERE enviada = 0 AND urgencia = '📋' ORDER BY id"
    ).fetchall()
    if marcar and linhas:
        con.executemany("UPDATE fila SET enviada = 1 WHERE id = ?", [(r["id"],) for r in linhas])
        con.commit()
    return [r["texto"] for r in linhas]
