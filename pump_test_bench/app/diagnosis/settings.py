"""诊断的运行设置（前端可改，所有服务共用）：目前是当前燃油的 20 ℃ 密度。

保存在 ``<DB_PATH 所在目录>/diagnosis_settings.json``。和 bench.json 的区别：bench.json 是试验台结构
（管路、测点、阈值），由工程师维护；这里是随油品、批次变化的运行参数，由操作人员在前端填写。
"""
import json
import threading
from pathlib import Path
from typing import Dict, Optional

from shared.config import get_settings

DENSITY_RANGE = (700.0, 900.0)  # kg/m³，航空煤油/柴油的合理范围，超出多半是单位填错
_lock = threading.Lock()
DEFAULTS: Dict = {"fuel_density_20": None, "fuel_note": ""}


def settings_path() -> Path:
    return get_settings().db_path.parent / "diagnosis_settings.json"


def load_settings() -> Dict:
    path = settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        data = {}
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def check_density(value) -> Optional[float]:
    """校验 20 ℃ 密度（kg/m³）；空值返回 None。"""
    if value in (None, ""):
        return None
    try:
        density = float(value)
    except (TypeError, ValueError):
        raise ValueError("燃油密度必须是数字（kg/m³）") from None
    lo, hi = DENSITY_RANGE
    if not lo <= density <= hi:
        raise ValueError(f"燃油密度应在 {lo:.0f}–{hi:.0f} kg/m³ 之间（20 ℃），请检查单位")
    return density


def save_settings(data: Dict) -> Dict:
    current = load_settings()
    if "fuel_density_20" in data:
        current["fuel_density_20"] = check_density(data["fuel_density_20"])
    if "fuel_note" in data:
        current["fuel_note"] = str(data["fuel_note"] or "")[:200]
    path = settings_path()
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    return current


def fuel_density_20() -> Optional[float]:
    return load_settings().get("fuel_density_20")
