"""GDELT DOC 2.0 — volume de notícias por tema (há notícia por trás do movimento?).

Endpoint: GET https://api.gdeltproject.org/api/v2/doc/doc?query=...&mode=TimelineVol&format=json&timespan=7d
Resposta: {"timeline": [{"data": [{"date": "20261006T120000Z", "value": 0.12}, ...]}]}
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta

from bot.http import Http

URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def consulta_do_tema(tema: dict) -> str:
    termos = tema.get("noticias") or tema.get("incluir") or []
    partes = [f'"{t}"' if " " in t else t for t in termos[:6]]
    return "(" + " OR ".join(partes) + ")" if len(partes) > 1 else (partes[0] if partes else "")


def serie(http: Http, consulta: str, dias: int = 7) -> list[tuple[datetime, float]]:
    dados = http.get_json(
        URL, {"query": consulta, "mode": "TimelineVol", "format": "json", "timespan": f"{dias}d"}
    )
    pontos = []
    for linha in (dados or {}).get("timeline") or []:
        for p in linha.get("data") or []:
            try:
                ts = datetime.strptime(p["date"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                pontos.append((ts, float(p["value"])))
            except (KeyError, ValueError):
                continue
    return sorted(pontos)


def pico(pontos: list[tuple[datetime, float]], agora: datetime, janela_h: int = 6) -> float | None:
    """Volume médio das últimas `janela_h` horas ÷ mediana da semana (1,0 = normal; ≥ 2 = pico)."""
    recentes = [v for ts, v in pontos if ts >= agora - timedelta(hours=janela_h)]
    base = [v for ts, v in pontos if ts < agora - timedelta(hours=janela_h)]
    if not recentes or len(base) < 10:
        return None
    mediana = statistics.median(base)
    return (sum(recentes) / len(recentes)) / mediana if mediana > 0 else None
