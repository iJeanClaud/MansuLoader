"""Registro de erros e crashes do MansuLoader em %APPDATA%\\.mansu-loader\\crash.log."""

from __future__ import annotations

import faulthandler
import logging
import os
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_FAULTHANDLER_FILE = None


def get_log_dir() -> Path:
    """Retorna o diretório %APPDATA%\\.mansu-loader e o cria se não existir."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home()
    log_dir = base / ".mansu-loader"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_file() -> Path:
    """Retorna o caminho completo do arquivo crash.log."""
    return get_log_dir() / "crash.log"


def setup_crash_logging() -> logging.Logger:
    """Configura logging rotativo, sys.excepthook, threading.excepthook e faulthandler."""
    global _FAULTHANDLER_FILE

    log_file = get_log_file()
    logger = logging.getLogger("mansuloader")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = RotatingFileHandler(
            log_file,
            maxBytes=1_048_576,
            backupCount=3,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    try:
        _FAULTHANDLER_FILE = log_file.open("a", encoding="utf-8")
        faulthandler.enable(file=_FAULTHANDLER_FILE, all_threads=True)
    except Exception:
        pass

    def handle_sys_exception(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical("Exceção não tratada na thread principal:\n%s", details)

    def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        details = "".join(
            traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        )
        thread_name = args.thread.name if args.thread else "desconhecida"
        logger.critical("Exceção não tratada na thread '%s':\n%s", thread_name, details)

    sys.excepthook = handle_sys_exception
    threading.excepthook = handle_thread_exception
    return logger


def log_exception(context: str, exc: Optional[BaseException] = None) -> None:
    """Registra uma exceção capturada com stacktrace no crash.log."""
    logger = logging.getLogger("mansuloader")
    if exc is not None:
        logger.error("%s: %s", context, exc, exc_info=(type(exc), exc, exc.__traceback__))
    else:
        logger.error("%s\n%s", context, traceback.format_exc())
