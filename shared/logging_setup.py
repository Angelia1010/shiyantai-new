"""统一日志：控制台 + 按天轮转的文件（保留 30 天），日志目录由 LOG_DIR 配置。"""
import logging
from logging.handlers import TimedRotatingFileHandler

from shared.config import get_settings

_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_logging(service_name: str, level: int = logging.INFO) -> logging.Logger:
    root = logging.getLogger()
    if not getattr(root, "_shiyantai_configured", False):
        log_dir = get_settings().log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        formatter = logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

        file_handler = TimedRotatingFileHandler(
            log_dir / f"{service_name}.log", when="midnight", backupCount=30, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        root.setLevel(level)
        root.addHandler(file_handler)
        root.addHandler(console_handler)
        root._shiyantai_configured = True  # type: ignore[attr-defined]
    return logging.getLogger(service_name)
