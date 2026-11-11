"""诊断配置加载。

默认读取 pump_test_bench/config/bench.json，可用环境变量 BENCH_CONFIG 指定其他文件。
按文件修改时间缓存，修改配置后下一次诊断自动生效。
"""
import json
import os
import threading
from pathlib import Path
from typing import Dict, Tuple

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "bench.json"
_lock = threading.Lock()
_cache: Dict[str, Tuple[float, Dict]] = {}


def config_path() -> Path:
    value = os.environ.get("BENCH_CONFIG", "").strip()
    return Path(value) if value else DEFAULT_CONFIG


def load_config() -> Dict:
    path = config_path()
    mtime = path.stat().st_mtime
    with _lock:
        cached = _cache.get(str(path))
        if cached and cached[0] == mtime:
            return cached[1]
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"诊断配置文件格式错误：{path}（{exc}）") from None
    if not cfg.get("loops"):
        raise ValueError(f"诊断配置文件中没有定义管路（loops）：{path}")
    with _lock:
        _cache[str(path)] = (mtime, cfg)
    return cfg


def all_meter_columns(cfg: Dict):
    for loop in cfg["loops"]:
        for meter in loop.get("meters", []):
            yield meter["column"]
        if loop.get("mass_meter"):
            yield loop["mass_meter"]["column"]
