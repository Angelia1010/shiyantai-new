"""从试验数据（稳定段）取出模型输入（工况）与各测点均值。

输入有三种取法：
- column（+ fallback_columns）：单个测点的均值，主测点无效时用备用测点；
- columns + aggregate：多个测点的中位数（如多只流量计的共识值）；
- derived = density / viscosity：由油温按燃油密度模型（需要调用方提供 density_fn）/ 黏度模型计算；
- constant：常数（公式里要用、但不来自测点的量）。
取得的值再按 scale、offset 换算单位：值 × scale + offset（如 kg/h → kg/s：scale = 1/3600）。
测点也可以是派生测点（config/signals.json 的 derived），如由涡轮流量计流量换算的转速 Hz。
"""
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

DensityFn = Callable[[float], Optional[float]]


def _mean(seg: pd.DataFrame, col: str) -> Optional[float]:
    """测点均值；不是采集列时按派生测点（config/signals.json 的 derived，如涡轮流量计转速 Hz）换算。"""
    if col in seg.columns:
        series = pd.to_numeric(seg[col], errors="coerce")
    else:
        from pump_test_bench.app.signals import derived_series
        series = derived_series(seg, col)
        if series is None:
            return None
    values = series.dropna()
    return float(values.mean()) if len(values) else None


def _first_valid(seg: pd.DataFrame, cols: List[str], lo: float, hi: float) -> Tuple[Optional[float], int]:
    for i, col in enumerate(cols):
        value = _mean(seg, col)
        if value is not None and lo <= value <= hi:
            return value, i
    return None, -1


def condition_of(seg: pd.DataFrame, cfg: Dict, density_fn: Optional[DensityFn] = None) -> Tuple[Dict[str, float], List[str]]:
    """返回 (工况 {输入名: 值}, 说明)。"""
    cond: Dict[str, float] = {}
    notes: List[str] = []
    for spec in cfg["inputs"]:
        lo, hi = spec.get("valid", [float("-inf"), float("inf")])
        derived = spec.get("derived")
        if derived in ("density", "viscosity"):
            cols = [spec["temperature_column"]] + spec.get("fallback_columns", [])
            temp, i = _first_valid(seg, cols, -40, 120)
            if derived == "density":
                value = density_fn(temp) if (temp is not None and density_fn) else None
            else:
                from pump_test_bench.app.signals import fuel_viscosity
                value = fuel_viscosity(temp) if temp is not None else None
            if value is None:
                notes.append(f"无法计算{spec['name']}（缺少有效油温" + ("或密度模型）" if derived == "density" else "）"))
                continue
            if i > 0:
                notes.append(f"{cols[0]} 读数无效，{spec['name']}改用 {cols[i]} 计算")
        elif spec.get("constant") is not None and not spec.get("column") and not spec.get("columns"):
            value = float(spec["constant"])
        elif spec.get("columns"):
            vals = [v for v in (_mean(seg, c) for c in spec["columns"]) if v is not None]
            value = float(np.median(vals)) if vals else None
            if value is None or not lo <= value <= hi:
                notes.append(f"缺少有效的{spec['name']}")
                continue
        else:
            cols = [spec["column"]] + spec.get("fallback_columns", [])
            value, i = _first_valid(seg, cols, lo, hi)
            if value is None:
                notes.append(f"缺少有效的{spec['name']}（{spec['column']}）")
                continue
            if i > 0:
                notes.append(f"{spec['column']} 读数无效，{spec['name']}改用 {cols[i]}")
        cond[spec["name"]] = value * float(spec.get("scale", 1.0)) + float(spec.get("offset", 0.0))
    return cond, notes


def measured_means(seg: pd.DataFrame, cfg: Dict) -> Dict[str, float]:
    """各输出测点列的均值 {列: 值}。"""
    out = {}
    for o in cfg["outputs"]:
        for col in o["columns"]:
            value = _mean(seg, col)
            if value is not None:
                out[col] = value
    return out


def input_columns(cfg: Dict) -> List[str]:
    cols: List[str] = []
    for spec in cfg["inputs"]:
        cols += spec.get("columns", []) or [c for c in [spec.get("column"), spec.get("temperature_column")] if c]
        cols += spec.get("fallback_columns", [])
    return cols


def applicable(seg: pd.DataFrame, cfg: Dict) -> Tuple[bool, str]:
    """模型的适用条件（active_if）：如“大流量管路工作”= 回油流量1-1 ≥ 20 L/h。不满足时不做该模型的对比。"""
    for cond in cfg.get("active_if") or []:
        value = _mean(seg, cond["column"])
        lo, hi = cond.get("min", float("-inf")), cond.get("max", float("inf"))
        if value is None or not lo <= value <= hi:
            what = cond.get("note") or f"{cond['column']} 在 {lo}–{hi} 之间"
            return False, f"不在模型适用范围（需要{what}）"
    return True, ""
