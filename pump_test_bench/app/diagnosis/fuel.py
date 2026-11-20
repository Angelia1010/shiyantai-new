"""燃油物性：油温与密度（质量-体积校核、仿真模型工况都要用）。"""
from typing import Dict, Optional, Tuple

import pandas as pd

from pump_test_bench.app.diagnosis import checks as ck


def density_model(cfg: Dict, baseline: Optional[Dict]) -> Dict:
    """密度-温度关系：健康基准拟合的优先，否则用配置。"""
    return (baseline or {}).get("density") or cfg.get("fuel") or {}


def density(cfg: Dict, baseline: Optional[Dict], temperature: Optional[float],
            rho20: Optional[float]) -> Tuple[Optional[float], str]:
    """返回 (密度 kg/m³, 来源说明)。rho20 = 当前燃油 20 ℃ 密度（合格证上的值），有则按油温修正后使用。"""
    model = density_model(cfg, baseline)
    slope = model.get("slope", -0.7)
    if rho20:
        if temperature is None:
            return float(rho20), f"设置的燃油密度 {rho20:.1f} kg/m³（20 ℃，缺少油温未修正）"
        return float(rho20) + slope * (temperature - 20), f"设置的燃油密度 {rho20:.1f} kg/m³（20 ℃）按油温修正"
    if temperature is None or "rho15" not in model:
        return None, "无法计算（缺少温度）"
    rho = model["rho15"] + model["slope"] * (temperature - 15)
    return rho, "健康基准拟合" if (baseline or {}).get("density") else "配置（密度-温度模型）"


def valid_temperature(seg: pd.DataFrame, col: Optional[str], cfg: Dict) -> Optional[float]:
    """稳定段油温均值；列不存在或读数超出合理范围（传感器故障）时返回 None。"""
    if not col or col not in seg.columns:
        return None
    value = ck.mean_of(seg[col])
    rule = ck.range_rule(col, cfg.get("sensor_ranges", []))
    if value is not None and rule and not (rule["min"] <= value <= rule["max"]):
        return None
    return value
