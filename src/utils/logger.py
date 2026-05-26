import logging
import os
from contextvars import ContextVar
from logging.handlers import TimedRotatingFileHandler

# 每个异步任务（会话）独立持有自己的 ssid，互不干扰
_session_id_var: ContextVar[str] = ContextVar("session_id", default="-")


def set_session_id(session_id: str) -> None:
    """在会话入口处调用，设置当前异步上下文的 ssid"""
    _session_id_var.set(session_id)


class _SessionIdFilter(logging.Filter):
    """给每条日志记录注入当前上下文的 session_id"""
    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = _session_id_var.get()
        return True


def setup_logger(project_root: str) -> None:
    """初始化全局应用日志，按天切割写入 data/logs/app.log"""
    root_logger = logging.getLogger()
    if any(isinstance(h, TimedRotatingFileHandler) for h in root_logger.handlers):
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
        "%(asctime)s [%(levelname)s] [%(session_id)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    handler.addFilter(_SessionIdFilter())

    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


def get_session_logger(session_id: str) -> logging.LoggerAdapter:
    """获取带 session_id 前缀的 logger，用于追踪单个会话"""
    logger = logging.getLogger("mbot.session")
    return logging.LoggerAdapter(logger, {"session_id": session_id})
