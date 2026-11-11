"""统一配置。

配置来源（优先级从高到低）：
1. 进程环境变量；
2. 仓库根目录下的 ``.env`` 文件（格式 ``KEY=VALUE``，可参考 ``.env.example``）；
3. 本文件中的默认值。

``SECRET_KEY`` 与 ``ADMIN_PASSWORD`` 没有默认值，缺失时服务启动即报错，
避免带着弱口令上线。
"""
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """读取简单的 .env 文件；已存在的环境变量不会被覆盖。"""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    return int(value) if value else default


def _env_path(name: str, default: Path) -> Path:
    value = _env(name)
    path = Path(value) if value else default
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


@dataclass(frozen=True)
class Settings:
    secret_key: str
    admin_username: str
    admin_password: str
    token_ttl_hours: int

    bind_host: str
    task_service_port: int
    file_service_port: int
    llm_service_port: int
    amesim_service_port: int

    data_roots: Tuple[Path, ...]
    db_path: Path
    log_dir: Path
    amesim_model_dir: Path

    ollama_url: str
    ollama_model: str
    ollama_timeout: int
    llm_max_windows: int
    redis_url: str


class ConfigError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv(REPO_ROOT / ".env")

    secret_key = _env("SECRET_KEY")
    admin_password = _env("ADMIN_PASSWORD")
    missing = [name for name, value in (("SECRET_KEY", secret_key), ("ADMIN_PASSWORD", admin_password)) if not value]
    if missing:
        raise ConfigError(
            f"缺少必需的配置项：{', '.join(missing)}。"
            f"请复制仓库根目录的 .env.example 为 .env 并填写。"
        )

    roots_value = _env("DATA_ROOTS")
    if roots_value:
        roots = tuple(_resolve(p) for p in roots_value.split(os.pathsep) if p.strip())
    else:
        roots = (REPO_ROOT / "pump_test_bench" / "samples",)

    return Settings(
        secret_key=secret_key,
        admin_username=_env("ADMIN_USERNAME", "admin"),
        admin_password=admin_password,
        token_ttl_hours=_env_int("TOKEN_TTL_HOURS", 12),
        bind_host=_env("BIND_HOST", "127.0.0.1"),
        task_service_port=_env_int("TASK_SERVICE_PORT", 5001),
        file_service_port=_env_int("FILE_SERVICE_PORT", 5002),
        llm_service_port=_env_int("LLM_SERVICE_PORT", 8999),
        amesim_service_port=_env_int("AMESIM_SERVICE_PORT", 5003),
        data_roots=roots,
        db_path=_env_path("DB_PATH", REPO_ROOT / "pump_test_bench" / "data" / "tasks.db"),
        log_dir=_env_path("LOG_DIR", REPO_ROOT / "logs"),
        amesim_model_dir=_env_path("AMESIM_MODEL_DIR", REPO_ROOT / "AMESim_server" / "model"),
        ollama_url=_env("OLLAMA_URL", "http://127.0.0.1:11439").rstrip("/"),
        ollama_model=_env("OLLAMA_MODEL", "DeepSeek-R1-Distill-Qwen-1.5B"),
        ollama_timeout=_env_int("OLLAMA_TIMEOUT", 300),
        llm_max_windows=_env_int("LLM_MAX_WINDOWS", 50),
        redis_url=_env("REDIS_URL"),
    )


def _resolve(path: str) -> Path:
    p = Path(path.strip())
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p.resolve()
