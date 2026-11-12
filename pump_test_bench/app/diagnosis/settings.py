"""诊断的运行设置（前端可改，所有服务共用）：当前燃油的 20 ℃ 密度，以及诊断方案（各仿真模型怎样参与诊断）。

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
DEFAULTS: Dict = {"fuel_density_20": None, "fuel_note": "", "models": {}}
MODES = {"decisive": "参与结论", "reference": "仅作参考", "off": "关闭"}


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
    if "models" in data:
        current["models"] = check_models(data["models"])
    path = settings_path()
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    return current


def fuel_density_20() -> Optional[float]:
    return load_settings().get("fuel_density_20")


def check_models(value) -> Dict[str, Dict]:
    """诊断方案：{模型 id: {mode: decisive|reference|off, sigma_warn?, sigma_alarm?}}。"""
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValueError("models 必须是 {模型 id: {mode, sigma_warn, sigma_alarm}} 格式")
    out = {}
    for mid, spec in value.items():
        if not isinstance(spec, dict):
            raise ValueError(f"模型 {mid} 的设置格式错误")
        mode = spec.get("mode", "decisive")
        if mode not in MODES:
            raise ValueError(f"模型 {mid} 的 mode 只能是 decisive、reference 或 off")
        item = {"mode": mode}
        for key in ("sigma_warn", "sigma_alarm"):
            v = spec.get(key)
            if v in (None, ""):
                continue
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"模型 {mid} 的 {key} 必须是数字") from None
            if not 1 <= v <= 20:
                raise ValueError(f"模型 {mid} 的 {key} 应在 1 到 20 之间")
            item[key] = v
        if "sigma_warn" in item and "sigma_alarm" in item and item["sigma_alarm"] < item["sigma_warn"]:
            raise ValueError(f"模型 {mid} 的异常倍数不能小于预警倍数")
        out[str(mid)] = item
    return out


def profile(override: Optional[Dict] = None, saved: Optional[Dict] = None) -> Dict[str, Dict]:
    """生效的诊断方案：模型配置的默认值 ← 保存的方案 ← 本次诊断的临时设置。"""
    from pump_test_bench.app.simulation.config import list_models
    if saved is None:
        try:
            saved = load_settings().get("models", {})
        except Exception:  # 没有服务配置（离线工具）时只用默认值
            saved = {}
    override = check_models(override) if override else {}
    out = {}
    for m in list_models():
        th = m.get("thresholds", {})
        item = {"mode": m.get("default_mode", "decisive"), "sigma_warn": th.get("sigma_warn", 3),
                "sigma_alarm": th.get("sigma_alarm", 5)}
        item.update(saved.get(m["id"], {}))
        item.update(override.get(m["id"], {}))
        out[m["id"]] = item
    return out
