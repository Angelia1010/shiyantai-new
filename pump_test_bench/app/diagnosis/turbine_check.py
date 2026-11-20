"""涡轮流量计二级诊断：用涡轮流量计模型复核一级诊断怀疑的流量计。

涡轮流量计的叶轮转速（Hz）由流过的质量流量、介质密度决定（模型见 config/simulation/turbine_large.json）。
以回油质量流量计为参照算出该表“应有”的转速，与该表读数按 K 系数换算的转速比较：
    残差 = 实测转速 / 模型转速 − 1 − 该表在当前工况下的固有偏差（健康基准标定）
K 系数漂移（磨损、沉积）时残差与该表的偏离一致；实际流量变化时质量流量计同样测到，残差不变。

只在一级诊断怀疑流量计时运行，且权重低于主信号（bench.json turbine.weight），因为它依赖不在主信号中的
回油质量流量2、回油压力1-1，质量流量计本身的漂移也会混进来。
"""
import copy
from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
import pandas as pd

from pump_test_bench.app.diagnosis import checks as ck
from pump_test_bench.app.diagnosis.tolerances import features
from pump_test_bench.app.simulation.calibration import bias_at
from pump_test_bench.app.simulation.condition import DensityFn, condition_of


@dataclass
class TurbineCheck:
    meter: str
    available: bool
    note: str = ""
    measured_hz: Optional[float] = None
    expected_hz: Optional[float] = None
    raw: Optional[float] = None          # 实测/模型 − 1（未扣除固有偏差）
    residual: Optional[float] = None     # 扣除固有偏差后
    sigma: Optional[float] = None
    condition: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> Dict:
        keys = ("meter", "available", "note", "measured_hz", "expected_hz", "residual", "sigma", "condition")
        return {k: getattr(self, k) for k in keys}


def _model(sims, model_id: str):
    return next(((m, t) for m, t in sims or [] if m["id"] == model_id), (None, None))


def _with_temperature(mcfg: Dict, column: str) -> Dict:
    """把模型的油温输入（温度、密度的温度来源）换成指定的温度测点。"""
    out = copy.deepcopy(mcfg)
    for spec in out["inputs"]:
        if spec.get("derived") in ("density", "viscosity"):
            spec["temperature_column"], spec["fallback_columns"] = column, []
        elif spec.get("unit") == "℃" or "温度" in spec["name"]:
            spec["column"], spec["fallback_columns"] = column, []
    return out


def _hz_spec(spec: Dict) -> Optional[Dict]:
    from pump_test_bench.app.signals import derived_specs
    return derived_specs().get(spec.get("hz_column") or spec.get("hz_from"))


def raw_residual(seg: pd.DataFrame, cfg: Dict, meter: str, sims, density_fn: Optional[DensityFn]) -> TurbineCheck:
    """实测转速 / 模型转速 − 1（未扣除固有偏差）。建健康基准时用来标定固有偏差。"""
    tcfg = cfg.get("turbine") or {}
    spec = (tcfg.get("meters") or {}).get(meter)
    if not spec:
        return TurbineCheck(meter, False, "该流量计没有配置涡轮流量计模型")
    mcfg, table = _model(sims, tcfg.get("model", ""))
    if mcfg is None:
        return TurbineCheck(meter, False, f"涡轮流量计模型 {tcfg.get('model')} 没有可用的基准表")
    mass_col = tcfg.get("mass_column")
    if not mass_col or mass_col not in seg.columns:
        return TurbineCheck(meter, False, f"数据中没有参照用的质量流量（{mass_col}）")
    mass = ck.mean_of(seg[mass_col])
    if mass is None or mass < 1 or ck.is_stuck(seg[mass_col]):
        return TurbineCheck(meter, False, f"参照用的 {mass_col} 读数无效或卡死，无法复核")
    hz = _hz_spec(spec)
    if not hz or meter not in seg.columns:
        return TurbineCheck(meter, False, "缺少该流量计的转速换算（config/signals.json 的 derived）")
    flow = ck.mean_of(seg[meter])
    measured = max(flow * hz.get("scale", 1.0) + hz.get("offset", 0.0), hz.get("min", float("-inf")))
    model_cfg = _with_temperature(mcfg, spec["temperature_column"])
    cond, notes = condition_of(seg, model_cfg, density_fn)
    if len(cond) < len(table["inputs"]):
        return TurbineCheck(meter, False, "；".join(notes) or "涡轮流量计模型的工况不完整")
    from pump_test_bench.app.simulation.table import predict
    pred, _ = predict(table, cond)
    expected = pred.get(mcfg["outputs"][0]["name"])
    if not expected or expected <= 0:
        return TurbineCheck(meter, False, "涡轮流量计模型没有给出有效的转速")
    return TurbineCheck(meter, True, measured_hz=float(measured), expected_hz=float(expected),
                        raw=float(measured / expected - 1), condition=cond)


def check(seg: pd.DataFrame, cfg: Dict, meter: str, sims, density_fn: Optional[DensityFn],
          baseline: Optional[Dict], temperature: Optional[float]) -> TurbineCheck:
    """二级诊断：扣除该表在当前工况下的固有偏差。固有偏差优先用健康基准的标定，
    没有时用涡轮流量计基准表对该转速列的标定（只有回油流量计有）。"""
    tc = raw_residual(seg, cfg, meter, sims, density_fn)
    if not tc.available:
        return tc
    flow = ck.mean_of(seg[meter])
    calib = ((baseline or {}).get("turbine") or {}).get(meter)
    if calib and calib.get("coef") and temperature is not None:
        bias = float(np.dot(calib["coef"], features(flow, temperature, calib["ranges"])))
        tc.sigma = calib["std"]
    else:
        tcfg = cfg["turbine"]
        mcfg, table = _model(sims, tcfg["model"])
        col = cfg["turbine"]["meters"][meter].get("hz_column")
        c = ((table.get("calibration") or {}).get("columns") or {}).get(col) if col else None
        if not c:
            tc.available, tc.note = False, "该流量计还没有涡轮流量计模型的固有偏差标定（用健康数据重建健康基准后可用）"
            return tc
        bias, tc.sigma = bias_at(c, mcfg, tc.condition), c["std"]
    tc.residual = tc.raw - bias
    tc.expected_hz *= 1 + bias
    return tc
