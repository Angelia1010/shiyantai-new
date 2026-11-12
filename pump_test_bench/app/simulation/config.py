"""仿真模型注册表：pump_test_bench/config/simulation/ 下每个 .json 是一个模型（可用环境变量 SIM_CONFIG_DIR 指定目录）。

加一个模型 = 加一份配置 + 建一张基准表，诊断代码不用改。按文件修改时间缓存。
"""
import json
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_SIM_DIR = Path(__file__).resolve().parents[2] / "config" / "simulation"
_lock = threading.Lock()
_cache: Dict[str, Tuple[float, Dict]] = {}


def sim_config_dir() -> Path:
    value = os.environ.get("SIM_CONFIG_DIR", "").strip()
    return Path(value) if value else DEFAULT_SIM_DIR


def _load(path: Path) -> Dict:
    mtime = path.stat().st_mtime
    with _lock:
        cached = _cache.get(str(path))
        if cached and cached[0] == mtime:
            return cached[1]
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"仿真模型配置格式错误：{path.name}（{exc}）") from None
    for key in ("id", "name", "engine", "inputs", "outputs"):
        if not cfg.get(key):
            raise ValueError(f"仿真模型配置 {path.name} 缺少 {key}")
    with _lock:
        _cache[str(path)] = (mtime, cfg)
    return cfg


def list_models() -> List[Dict]:
    d = sim_config_dir()
    models = [_load(p) for p in sorted(d.glob("*.json"))] if d.exists() else []
    return sorted(models, key=lambda m: (m.get("order", 99), m["id"]))


def load_model_cfg(model_id: str) -> Dict:
    for m in list_models():
        if m["id"] == model_id:
            return m
    raise ValueError(f"没有这个仿真模型：{model_id}")


def input_names(cfg: Dict) -> List[str]:
    return [i["name"] for i in cfg["inputs"]]


def output_names(cfg: Dict) -> List[str]:
    return [o["name"] for o in cfg["outputs"]]


def find_output(cfg: Dict, name: str) -> Optional[Dict]:
    return next((o for o in cfg["outputs"] if o["name"] == name), None)


def residual_mode(output: Dict) -> str:
    """relative：相对偏差（流量、压力）；absolute：绝对偏差（温度，零点没有物理意义）。"""
    return output.get("residual", "relative")
