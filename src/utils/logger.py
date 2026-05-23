import logging
import os
from logging.handlers import TimedRotatingFileHandler


def setup_logger(project_root: str) -> None:
    """初始化全局应用日志，按天切割写入 data/logs/app.log"""
    logger = logging.getLogger("mbot")
    if logger.handlers:
        return

    log_dir = os.path.join(project_root, "data", "logs")
    os.makedirs(log_dir, exist_ok=True)

    handler = TimedRotatingFileHandler(
        filename=os.path.join(log_dir, "app.log"),
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    logger.setLevel(logging.INFO)
    logger.addHandler(handler)


def get_session_logger(session_id: str) -> logging.LoggerAdapter:
    """获取带 session_id 前缀的 logger，用于追踪单个会话"""
    logger = logging.getLogger("mbot.session")
    return logging.LoggerAdapter(logger, {"session_id": session_id})
