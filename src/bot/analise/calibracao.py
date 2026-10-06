"""Módulo 2 — calibração: defasagem e sensibilidade (beta) de cada par (mercado, ativo).

Método (barras de 5 min, últimos 30 dias, só horário de pregão do ativo):
- x_t = variação do log-odds da probabilidade na barra t; r_t = retorno log do ativo na barra t.
- Defasagem: deslocamento k (−60…+60 min) com maior |correlação(x_t, r_{t+k})|.
  k > 0 = a Polymarket anda antes do ativo.
- Beta: regressão de r_{t+k} na variação da probabilidade em pontos (Δp),
  expresso em "% do ativo por +10 p.p.".
- A primeira barra de cada pregão (gap de abertura) fica de fora: o movimento fora do pregão
  é "gap esperado na abertura", não reação explorável.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from bot import formato as f
from bot.config import Config
from bot.db import iso
from bot.logs import aviso, info, log

_log = log("calibracao")


@dataclass
class Par:
    mercado_id: str
    ativo: str
    tema: str
    defasagem_min: float
    correlacao: float
    beta_10pp: float
    t_beta: float
    n: int
    volume: float = 0.0

    @property
    def confirmado(self) -> bool:
        return abs(self.t_beta) >= 2.0

    @property
    def score(self) -> float:
        """Ranking: força da relação × tamanho do efeito × liquidez, premiando quem anda antes."""
        antecedencia = 1.0 if self.defasagem_min > 0 else 0.3
        return abs(self.correlacao) * abs(self.beta_10pp) * math.log10(1 + self.volume) * antecedencia


def _logit(p: pd.Series) -> pd.Series:
    q = p.clip(0.005, 0.995)
    return np.log(q / (1 - q))


def alinhar(prob: pd.Series, preco: pd.Series, intervalo_min: int) -> pd.DataFrame:
    """Põe a probabilidade na grade de barras do ativo e marca as quebras de pregão."""
    prob = prob.sort_index()
    preco = preco.dropna().sort_index()
    grade = preco.index
    p = prob.reindex(prob.index.union(grade)).ffill().reindex(grade)
    df = pd.DataFrame({"p": p, "preco": preco})
    salto = df.index.to_series().diff() > pd.Timedelta(minutes=intervalo_min * 1.5)
    df["r"] = np.log(df["preco"]).diff()
    df["dp"] = df["p"].diff()
    df["dlo"] = _logit(df["p"]).diff()
    df.loc[salto, ["r", "dp", "dlo"]] = np.nan  # gap de abertura fora
    return df


def calibrar_par(
    prob: pd.Series,
    preco: pd.Series,
    *,
    intervalo_min: int = 5,
    defasagem_max_min: int = 60,
    amostras_min: int = 150,
) -> tuple[float, float, float, float, int] | None:
    """Retorna (defasagem_min, correlação, beta_10pp, t_beta, n) ou None se faltar dado."""
    df = alinhar(prob, preco, intervalo_min)
    k_max = defasagem_max_min // intervalo_min
    melhor: tuple[int, float, int] | None = None
    for k in range(-k_max, k_max + 1):
        par = pd.DataFrame({"x": df["dlo"], "y": df["r"].shift(-k)}).dropna()
        if len(par) < amostras_min or par["x"].std() == 0 or par["y"].std() == 0:
            continue
        c = float(par["x"].corr(par["y"]))
        if math.isnan(c):
            continue
        if melhor is None or abs(c) > abs(melhor[1]):
            melhor = (k, c, len(par))
    if melhor is None:
        return None
    k, c, _ = melhor
    reg = pd.DataFrame({"x": df["dp"], "y": df["r"].shift(-k)}).dropna()
    x, y = reg["x"].to_numpy(), reg["y"].to_numpy()
    n = len(reg)
    sxx = float(((x - x.mean()) ** 2).sum())
    if n < 3 or sxx == 0:
        return None
    beta = float(((x - x.mean()) * (y - y.mean())).sum() / sxx)
    resid = y - (y.mean() + beta * (x - x.mean()))
    se = math.sqrt(float((resid**2).sum()) / (n - 2) / sxx) if n > 2 else float("inf")
    t = beta / se if se > 0 else 0.0
    # beta em retorno log por 1,0 de probabilidade → % por 0,10 (10 p.p.)
    return k * intervalo_min, c, beta * 0.10 * 100, t, n


def pares_candidatos(con: sqlite3.Connection, cfg: Config) -> list[tuple[sqlite3.Row, str]]:
    """(mercado, ativo) dos mercados mais negociados de cada tema."""
    regras = cfg.regras
    vol_min = regras.get("filtros", {}).get("volume_min_sinal_usd", 0)
    por_tema = regras.get("calibracao", {}).get("mercados_por_tema", 3)
    saida = []
    for tema in cfg.temas_ligados():
        ativos = cfg.ativos_do_tema(tema)
        if not ativos:
            continue
        mercados = con.execute(
            """SELECT * FROM mercados WHERE tema = ? AND fechado = 0 AND palavras_ditas = 0
               AND volume >= ? AND token_sim IS NOT NULL AND prob > 0.02 AND prob < 0.98
               ORDER BY volume DESC LIMIT ?""",
            (tema, vol_min, por_tema),
        ).fetchall()
        for m in mercados:
            saida.extend((m, a) for a in ativos)
    return saida


def calibrar(
    con: sqlite3.Connection,
    cfg: Config,
    agora: datetime,
    obter_prob: Callable[[str, int, int, int], list[tuple[int, float]]],
    obter_barras: Callable[[list[str], int, int], pd.DataFrame],
) -> list[Par]:
    c = cfg.regras.get("calibracao", {})
    intervalo, dias = c.get("intervalo_min", 5), c.get("dias", 30)
    pares = pares_candidatos(con, cfg)
    if not pares:
        aviso(_log, "nenhum par para calibrar (faltam mercados acima do volume mínimo)")
        return []
    tickers = sorted({a for _, a in pares})
    barras = obter_barras(tickers, dias, intervalo)
    fim = int(agora.timestamp())
    inicio = fim - dias * 86400

    probs: dict[str, pd.Series] = {}
    resultado: list[Par] = []
    for m, ativo in pares:
        if m["id"] not in probs:
            try:
                pontos = obter_prob(m["token_sim"], inicio, fim, intervalo)
            except Exception as erro:
                aviso(_log, "histórico do mercado indisponível", mercado=m["id"], erro=str(erro))
                pontos = []
            probs[m["id"]] = pd.Series(
                [p for _, p in pontos], index=pd.to_datetime([t for t, _ in pontos], unit="s", utc=True)
            )
        prob = probs[m["id"]]
        if prob.empty or ativo not in barras:
            continue
        r = calibrar_par(
            prob,
            barras[ativo],
            intervalo_min=intervalo,
            defasagem_max_min=c.get("defasagem_max_min", 60),
            amostras_min=c.get("amostras_min", 150),
        )
        if r:
            resultado.append(Par(m["id"], ativo, m["tema"], *r, volume=m["volume"] or 0.0))

    if not resultado:
        # Fontes fora do ar: mantém a calibração anterior e falha (o workflow avisa no Telegram).
        raise RuntimeError(f"nenhum par calibrado de {len(pares)} candidatos (históricos indisponíveis)")
    ts = iso(agora)
    con.execute("DELETE FROM calibracao")
    con.executemany(
        """INSERT INTO calibracao (mercado_id, ativo, tema, ts, defasagem_min, correlacao, beta_10pp,
           t_beta, n, volume, score) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                p.mercado_id,
                p.ativo,
                p.tema,
                ts,
                p.defasagem_min,
                p.correlacao,
                p.beta_10pp,
                p.t_beta,
                p.n,
                p.volume,
                p.score,
            )
            for p in resultado
        ],
    )
    con.commit()
    info(_log, "calibração concluída", pares=len(resultado), candidatos=len(pares))
    return resultado


def carregar(con: sqlite3.Connection, mercado_id: str) -> list[sqlite3.Row]:
    """Pares calibrados de um mercado, do melhor para o pior."""
    return con.execute(
        "SELECT * FROM calibracao WHERE mercado_id = ? ORDER BY score DESC", (mercado_id,)
    ).fetchall()


def texto_ranking(con: sqlite3.Connection, cfg: Config, t_min: float = 2.0) -> str:
    linhas = con.execute(
        """SELECT c.*, m.pergunta FROM calibracao c JOIN mercados m ON m.id = c.mercado_id
           ORDER BY c.tema, c.score DESC"""
    ).fetchall()
    if not linhas:
        return "📊 Calibração ainda não rodou. Actions → <b>Calibração</b> → Run workflow."
    partes = [
        f"📊 <b>Ranking da calibração</b> ({f.data(datetime.fromisoformat(linhas[0]['ts']))})",
        "defasagem (+ = Polymarket antes) | efeito por +10 p.p. | correlação",
    ]
    por_tema: dict[str, list[sqlite3.Row]] = {}
    for r in linhas:
        por_tema.setdefault(r["tema"], []).append(r)
    for tema, rs in por_tema.items():
        t = cfg.temas.get(tema, {})
        partes.append(f"\n{t.get('emoji', '')} <b>{f.esc(t.get('nome', tema))}</b>")
        for r in rs[:3]:
            ok = "✅" if abs(r["t_beta"]) >= t_min else "❔"
            partes.append(
                f"{ok} {r['ativo'].removesuffix('.SA')}: {f.numero(r['defasagem_min'], 0, sinal=True)} min | "
                f"{f.numero(r['beta_10pp'], 2, sinal=True)}% | {f.numero(r['correlacao'], 2, sinal=True)}"
            )
        partes.append(f"   ↳ {f.esc(f.encurtar(rs[0]['pergunta'], 60))}")
    partes.append("\n✅ efeito estatisticamente claro (|t| ≥ 2) · ❔ ainda incerto")
    return "\n".join(partes)
