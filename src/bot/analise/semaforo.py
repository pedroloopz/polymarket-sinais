"""Módulo 4 — semáforo cruzado.

🟢 indicadores (Brent, DXY, VIX… e o ativo-alvo) andando no sentido esperado, sem conflito.
🟡 só a Polymarket se moveu (os demais parados ou sem dado).
🔴 sinais conflitantes (algum indicador andou contra).
"""

from __future__ import annotations

from bot import formato as f

NOMES = {"BZ=F": "Brent", "DX-Y.NYB": "DXY", "^VIX": "VIX", "BRL=X": "Dólar"}


def avaliar(
    variacoes: dict[str, float | None],
    esperados: dict[str, int],
    sentido_prob: int,
    limiar_pct: float = 0.1,
) -> tuple[str, str]:
    """`variacoes`: retorno de cada indicador desde a base (fração).
    `esperados`: sentido de cada indicador quando a prob. SOBE. `sentido_prob`: +1 subiu, −1 caiu.
    Retorna (emoji, detalhe "Brent −2,1% | VIX −4,0%")."""
    a_favor = contra = 0
    partes = []
    for ticker, esperado in esperados.items():
        v = variacoes.get(ticker)
        if v is None:
            continue
        partes.append(f"{NOMES.get(ticker, ticker.removesuffix('.SA'))} {f.pct(v, 1, sinal=True)}")
        if abs(v) * 100 < limiar_pct or esperado == 0:
            continue
        if (v > 0) == (esperado * sentido_prob > 0):
            a_favor += 1
        else:
            contra += 1
    if contra and contra >= a_favor:
        cor = "🔴"
    elif a_favor >= 2 and not contra:
        cor = "🟢"
    else:
        cor = "🟡"
    return cor, " | ".join(partes) if partes else "sem dados dos indicadores"


def rebaixar(cor: str) -> str:
    return {"🟢": "🟡", "🟡": "🔴", "🔴": "🔴"}.get(cor, cor)
