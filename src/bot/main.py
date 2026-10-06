"""CLI: python -m bot.main coletar | resumo | placar | tempo-real | backtest"""

from __future__ import annotations

import argparse
import sys

from bot import logs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bot", description="Bot de sinais Polymarket → ações")
    parser.add_argument("comando", choices=["coletar", "resumo", "placar", "tempo-real", "backtest"])
    parser.add_argument("--db", default=None, help="caminho do SQLite (padrão: $BOT_DB ou dados/bot.sqlite)")
    args = parser.parse_args(argv)
    logs.configurar()

    if args.comando in ("tempo-real", "backtest"):
        fase = "3 (Worker a cada 1–5 min)" if args.comando == "tempo-real" else "2 (calibração)"
        print(f"'{args.comando}' chega na Fase {fase}.")
        return 0

    from bot import tarefas
    from bot.diario import placar

    ctx = tarefas.contexto(args.db)
    if args.comando == "coletar":
        tarefas.tarefa_coletar(ctx)
    elif args.comando == "resumo":
        print(tarefas.tarefa_resumo(ctx))
    elif args.comando == "placar":
        print(placar.texto(placar.calcular(ctx.con, ctx.agora)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
