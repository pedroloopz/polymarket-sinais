"""Logs estruturados (uma linha JSON por evento), legíveis no log do GitHub Actions."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime


class _Json(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        dados = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "nivel": record.levelname,
            "modulo": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "dados", None)
        if extra:
            dados.update(extra)
        if record.exc_info:
            dados["erro"] = self.formatException(record.exc_info)
        return json.dumps(dados, ensure_ascii=False, default=str)


def configurar(nivel: int = logging.INFO) -> None:
    raiz = logging.getLogger()
    if any(isinstance(h.formatter, _Json) for h in raiz.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_Json())
    raiz.addHandler(handler)
    raiz.setLevel(nivel)


def log(nome: str) -> logging.Logger:
    return logging.getLogger(nome)


def info(logger: logging.Logger, msg: str, **dados) -> None:
    logger.info(msg, extra={"dados": dados})


def aviso(logger: logging.Logger, msg: str, **dados) -> None:
    logger.warning(msg, extra={"dados": dados})
