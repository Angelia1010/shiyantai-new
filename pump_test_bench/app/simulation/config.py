"""仿真配置加载：默认 pump_test_bench/config/simulation.json，可用环境变量 SIM_CONFIG 指定。按修改时间缓存。"""
import json
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_SIM_CONFIG = Path(__file__).resolve().parents[2] / "config" / "simulation.json"
_lock = threading.Lock()
_cache: Dict[str, Tuple[float, Dict]] = {}


def sim_config_path() -> Path:
    value = os.environ.get("SIM_CONFIG", "").strip()
    return Path(value) if value else DEFAULT_SIM_CONFIG


def load_sim_config() -> Dict:
    path = sim_config_path()
    mtime = path.stat().st_mtime
    with _lock:
        cached = _cache.get(str(path))
        if cached and cached[0] == mtime:
            return cached[1]
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"仿真配置文件格式错误：{path}（{exc}）") from None
    if not cfg.get("inputs") or not cfg.get("outputs"):
        raise ValueError(f"仿真配置缺少 inputs 或 outputs：{path}")
    with _lock:
        _cache[str(path)] = (mtime, cfg)
    return cfg


def input_names(cfg: Dict) -> List[str]:
    return [i["name"] for i in cfg["inputs"]]


def output_names(cfg: Dict) -> List[str]:
    return [o["name"] for o in cfg["outputs"]]


def output_of_column(cfg: Dict) -> Dict[str, Dict]:
    """测点列 → 它所属的模型输出。"""
    return {c: o for o in cfg["outputs"] for c in o["columns"]}


def find_input(cfg: Dict, name: str) -> Optional[Dict]:
    return next((i for i in cfg["inputs"] if i["name"] == name), None)
