"""Módulo 9 — agenda de eventos (buscada a cada execução; nada de datas no código).

Fontes oficiais lidas a cada execução:
- FOMC: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm  (página HTML)
- Payroll e CPI: https://www.bls.gov/schedule/news_release/empsit.htm e /cpi.htm (páginas HTML)
- Balanços das empresas de cripto: Yahoo (módulo 10)
Sem fonte oficial legível por máquina (verificado em 06/10/2026): Copom (o BCB só publica atas
passadas na API), OPEP+ e eleição → ficam em config/agenda.yaml, editável pelo GitHub no celular,
com a fonte anotada. A leitura de HTML é tolerante; se o formato mudar, a fonte aparece como
"⚠️ indisponível" no resumo em vez de quebrar o bot.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from bot.config import PASTA_CONFIG

FED = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS = {
    "payroll": "https://www.bls.gov/schedule/news_release/empsit.htm",
    "cpi": "https://www.bls.gov/schedule/news_release/cpi.htm",
}
MESES = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], start=1)}  # fmt: skip
ABREV = {k[:3]: v for k, v in MESES.items()} | {"sept": 9}


@dataclass
class Evento:
    tipo: str  # fomc | copom | payroll | cpi | opep | eleicao | balanco
    titulo: str
    data: date
    status: str  # confirmada | estimada
    fonte: str
    temas: list[str]

    @property
    def id(self) -> str:
        return f"{self.tipo}:{self.titulo}:{self.data.isoformat()}"


def _texto(pagina: str) -> str:
    sem_tags = re.sub(r"<script.*?</script>|<style.*?</style>", " ", pagina, flags=re.S | re.I)
    sem_tags = re.sub(r"<[^>]+>", " ", sem_tags)
    return re.sub(r"\s+", " ", html.unescape(sem_tags))


def fomc(pagina: str) -> list[date]:
    """Datas de decisão (último dia de cada reunião), por ano."""
    texto = _texto(pagina)
    saida: list[date] = []
    blocos = re.split(r"(\d{4}) FOMC Meetings", texto)
    for i in range(1, len(blocos) - 1, 2):
        ano, corpo = int(blocos[i]), blocos[i + 1]
        padrao = (
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
            r"Jan/Feb|Apr/May|Jul/Aug|Oct/Nov|Nov/Dec)\s+(\d{1,2})(?:\s*-\s*(\d{1,2}))?\*?"
        )
        for mes, d1, d2 in re.findall(padrao, corpo):
            # "Apr/May 30-1": termina no segundo mês; "March 17-18": no próprio mês
            vira_mes = "/" in mes and d2 and int(d2) < int(d1)
            nome = (mes.split("/")[-1] if vira_mes else mes.split("/")[0]).lower()
            num = MESES.get(nome) or ABREV.get(nome[:3])
            try:
                saida.append(date(ano, num, int(d2 or d1)))
            except (TypeError, ValueError):
                continue
    return sorted(set(saida))


def bls(pagina: str) -> list[date]:
    """Datas de divulgação na tabela do BLS ("Oct. 02, 2026", "Sept. 11, 2026")."""
    saida = []
    for mes, dia, ano in re.findall(r"\b([A-Z][a-z]{2,4})\.?\s+(\d{1,2}),\s+(\d{4})", _texto(pagina)):
        num = ABREV.get(mes.lower()[:4] if mes.lower().startswith("sept") else mes.lower()[:3])
        if num:
            try:
                saida.append(date(int(ano), num, int(dia)))
            except ValueError:
                continue
    return sorted(set(saida))


def manuais(pasta: Path = PASTA_CONFIG) -> list[Evento]:
    caminho = pasta / "agenda.yaml"
    if not caminho.exists():
        return []
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    saida = []
    for e in dados.get("eventos") or []:
        try:
            d = (
                e["data"]
                if isinstance(e["data"], date)
                else datetime.strptime(str(e["data"]), "%Y-%m-%d").date()
            )
        except (KeyError, ValueError):
            continue
        saida.append(
            Evento(
                e.get("tipo", "outro"),
                e.get("titulo", ""),
                d,
                e.get("status", "estimada"),
                e.get("fonte", "config/agenda.yaml"),
                e.get("temas") or [],
            )
        )
    return saida


def buscar(obter_pagina, hoje: date) -> tuple[list[Evento], dict[str, str]]:
    """`obter_pagina(url) -> str`. Retorna (eventos futuros, estado de cada fonte)."""
    eventos: list[Evento] = []
    fontes: dict[str, str] = {}
    try:
        datas = [d for d in fomc(obter_pagina(FED)) if d >= hoje]
        eventos += [Evento("fomc", "Decisão do FOMC (Fed)", d, "confirmada", FED, ["fed"]) for d in datas]
        fontes["Agenda FOMC"] = "ok" if datas else "sem datas"
    except Exception:
        fontes["Agenda FOMC"] = "indisponível"
    for tipo, url in BLS.items():
        nome = "Payroll (EUA)" if tipo == "payroll" else "CPI (EUA)"
        try:
            datas = [d for d in bls(obter_pagina(url)) if d >= hoje]
            eventos += [Evento(tipo, nome, d, "confirmada", url, ["fed"]) for d in datas]
            fontes[f"Agenda {nome}"] = "ok" if datas else "sem datas"
        except Exception:
            fontes[f"Agenda {nome}"] = "indisponível"
    eventos += [e for e in manuais() if e.data >= hoje]
    return sorted(eventos, key=lambda e: e.data), fontes
