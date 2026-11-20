"""标准台测点映射（config/signals.json）：系统 → 物理量 → 采集列 → 三维部件，以及派生测点（如涡轮流量计转速 Hz）。"""
import json
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

SIGNALS_PATH = Path(__file__).resolve().parents[1] / "config" / "signals.json"
_lock = threading.Lock()
_cache: Dict[str, Tuple[float, Dict]] = {}


def load_signals() -> Dict:
    mtime = SIGNALS_PATH.stat().st_mtime
    with _lock:
        cached = _cache.get("signals")
        if cached and cached[0] == mtime:
            return cached[1]
    data = json.loads(SIGNALS_PATH.read_text(encoding="utf-8"))
    with _lock:
        _cache["signals"] = (mtime, data)
    return data


def _override_path() -> Optional[Path]:
    try:
        from shared.config import get_settings
        return get_settings().db_path.parent / "signals_derived.json"
    except Exception:  # 离线工具没有服务配置
        return None


def _derived_override() -> Dict[str, Dict]:
    p = _override_path()
    if not p or not p.exists():
        return {}
    mtime = p.stat().st_mtime
    with _lock:
        cached = _cache.get("override")
        if cached and cached[0] == mtime:
            return cached[1]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        data = {}
    with _lock:
        _cache["override"] = (mtime, data)
    return data


def derived_specs() -> Dict[str, Dict]:
    """派生测点：signals.json 的 derived，页面上修改过的（数据库目录 signals_derived.json）优先。"""
    base = {k: v for k, v in load_signals().get("derived", {}).items() if not k.startswith("_")}
    for k, v in _derived_override().items():
        if k in base:
            base[k] = {**base[k], **{x: v[x] for x in ("scale", "offset", "min", "source", "unit") if x in v}}
    return base


def save_derived_override(items: List[Dict]) -> None:
    """保存页面上修改的派生测点换算（只允许修改已有派生测点的源列与换算系数）。"""
    p = _override_path()
    if p is None:
        raise ValueError("没有服务配置，不能保存")
    base = {k: v for k, v in load_signals().get("derived", {}).items() if not k.startswith("_")}
    out = {}
    for it in items or []:
        name = it.get("name")
        if name not in base:
            raise ValueError(f"没有这个派生测点：{name}")
        entry = {}
        for key in ("scale", "offset", "min"):
            if it.get(key) in (None, ""):
                continue
            try:
                entry[key] = float(it[key])
            except (TypeError, ValueError):
                raise ValueError(f"{name} 的 {key} 只能填数字") from None
        if entry.get("scale") == 0:
            raise ValueError(f"{name} 的换算系数不能为 0")
        if it.get("source"):
            entry["source"] = str(it["source"])
        out[name] = entry
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def derived_series(df: pd.DataFrame, name: str) -> Optional[pd.Series]:
    """派生测点的逐点值（采集列线性换算，可设下限）；源列不存在时返回 None。"""
    spec = derived_specs().get(name)
    if not spec or spec["source"] not in df.columns:
        return None
    v = pd.to_numeric(df[spec["source"]], errors="coerce") * spec.get("scale", 1.0) + spec.get("offset", 0.0)
    if "min" in spec:
        v = v.clip(lower=spec["min"])
    return v


def all_signals() -> List[Dict]:
    out = []
    for system in load_signals().get("systems", []):
        for s in system["signals"]:
            out.append({**s, "system": system["name"], "component": s.get("component") or system.get("component")})
    return out


def fuel_density(temperature: float) -> float:
    """油温下的燃油密度（kg/m³）：诊断设置里的 20 ℃ 密度优先，否则用健康基准/配置的密度-温度关系。"""
    from pump_test_bench.app.diagnosis.baseline import load_baseline
    from pump_test_bench.app.diagnosis.config import load_config
    from pump_test_bench.app.diagnosis.fuel import density as _density
    rho20 = None
    try:
        from pump_test_bench.app.diagnosis.settings import fuel_density_20
        rho20 = fuel_density_20()
    except Exception:
        pass
    return _density(load_config(), load_baseline(), temperature, rho20)[0]


def fuel_viscosity(temperature: float) -> float:
    """油温下的运动黏度（mm²/s），按 signals.json 的 fuel_properties。"""
    import math
    props = load_signals().get("fuel_properties", {})
    return props.get("nu20_mm2s", 1.25) * math.exp(props.get("nu_k", -0.0155) * (temperature - 20))


DERIVE = {"temperature": lambda t: t, "density": fuel_density, "viscosity": fuel_viscosity}
