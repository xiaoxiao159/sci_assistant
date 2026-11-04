"""统一日志(控制台 + 文件可选)。

整个应用共用一个 logger,避免每个模块各配一套。
"""
import logging
import sys

from app.core.config import settings


def _build_logger() -> logging.Logger:
    log = logging.getLogger("sci_assistant")
    log.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    if log.handlers:  # 防止重复添加
        return log

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)
    return log


logger = _build_logger()
