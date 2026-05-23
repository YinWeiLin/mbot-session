import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler


def setup_http_logger(project_root: str) -> logging.Logger:
    log_dir = os.path.join(project_root, "data", "logs")
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("mbot.http")
    if logger.handlers:
        return logger

    log_file = os.path.join(log_dir, "http.log")
    handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger


def get_http_logger() -> logging.Logger:
    return logging.getLogger("mbot.http")
