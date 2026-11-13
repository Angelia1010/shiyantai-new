"""固有偏差与判定阈值。

有健康基准时，每只表在当前工况（流量、油温）下的固有偏差由基准的偏差模型给出，阈值取
max(下限, 倍数 × 基准离散)；没有基准时用配置里的固定阈值。所有检查都从这里取阈值，口径一致。
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np


@dataclass(frozen=True)
class Tolerance:
    bias: float     # 固有偏差（相对）
    warn: float     # 预警阈值
    alarm: float    # 异常阈值
    sigma: float    # 换算成的噪声标准差 = 预警阈值 / 预警倍数，供故障隔离加权


def features(flow: float, temperature: float, ranges: Dict) -> List[float]:
    """偏差模型的输入；超出建基准时的范围就截断，避免外推。"""
    q = min(max(flow, ranges["flow"][0]), ranges["flow"][1]) / 100
    t = min(max(temperature, ranges["temperature"][0]), ranges["temperature"][1]) / 10
    return [1.0, q, t, q * t]


def predict_bias(meter: Dict, flow: Optional[float], temperature: Optional[float], ranges: Optional[Dict]) -> float:
    if meter.get("coef") and ranges and flow is not None and temperature is not None:
        return float(np.dot(meter["coef"], features(flow, temperature, ranges)))
    return float(meter.get("bias", 0.0))


def _scaled(th: Dict, std: Optional[float], bias: float = 0.0) -> Tolerance:
    """th：{warn, alarm[, sigma_warn, sigma_alarm]}，有基准离散 std 时阈值不低于倍数 × std。"""
    sw, sa = th.get("sigma_warn", 4), th.get("sigma_alarm", 8)
    warn, alarm = th["warn"], th["alarm"]
    if std:
        warn, alarm = max(warn, sw * std), max(alarm, sa * std)
    return Tolerance(bias, warn, alarm, warn / sw)


def meter(cfg: Dict, base: Optional[Dict], flow: Optional[float] = None, temperature: Optional[float] = None,
          ranges: Optional[Dict] = None) -> Tolerance:
    """体积流量计相对共识值的偏差。"""
    th = cfg["thresholds"]["redundancy"]
    if not base:
        return Tolerance(0.0, th["warn"], th["alarm"], th["warn"] / th["baseline_warn_sigma"])
    return _scaled({"warn": th["baseline_warn_floor"], "alarm": th["baseline_alarm_floor"],
                    "sigma_warn": th["baseline_warn_sigma"], "sigma_alarm": th["baseline_alarm_sigma"]},
                   base.get("std", 0.0), predict_bias(base, flow, temperature, ranges))


def balance(cfg: Dict, baseline: Optional[Dict], loop: str) -> Tolerance:
    """供回油平衡（泄漏、夹气、一侧整体偏移）。

    基准里的平衡离散是各表未扣除固有偏差时统计的；有逐表的固有偏差时平衡已逐表修正，
    剩下的离散小得多（60 个健康文件约 0.2%），不再用基准的平衡离散放大阈值，也不再扣除整体平衡偏差。"""
    b = (baseline or {}).get("balance", {}).get(loop, {})
    if (baseline or {}).get("meters"):
        return _scaled(cfg["thresholds"]["balance"], None)
    return _scaled(cfg["thresholds"]["balance"], b.get("std"), b.get("bias", 0.0))


def mass_volume(cfg: Dict, baseline: Optional[Dict], loop: str) -> Tolerance:
    """质量流量 ÷ 密度 与体积流量的偏差。"""
    b = (baseline or {}).get("mass_volume", {}).get(loop, {})
    return _scaled(cfg["thresholds"]["mass_volume"], b.get("std"), b.get("bias", 0.0))
