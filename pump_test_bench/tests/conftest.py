import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = REPO_ROOT / "pump_test_bench" / "samples"
SAMPLE_XLSX = "标准泵3.14（调喷嘴）.xlsx"
SAMPLE_TXT = "03月21日-14时36分曲线数据.txt"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """每个测试一套独立的配置：临时数据目录、临时数据库、临时日志目录。"""
    data_root = tmp_path / "data"
    data_root.mkdir()
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "pass123")
    monkeypatch.setenv("DATA_ROOTS", str(data_root))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))

    from shared.config import get_settings
    get_settings.cache_clear()
    yield data_root
    get_settings.cache_clear()


@pytest.fixture()
def sample_dir(env):
    for name in (SAMPLE_XLSX, SAMPLE_TXT):
        shutil.copy(SAMPLES / name, env / name)
    return env


@pytest.fixture()
def token(env):
    from shared.auth import issue_token
    return issue_token("admin")
