"""模型残差的阈值与显示格式：实测 与 模型在同一工况下的预期值 比较时共用。

诊断如何使用模型预期值见 diagnosis/expectation.py（各信号的预期值）与 diagnosis/flow_diagnosis.py（故障隔离）。
"""
from typing import Dict, List, Optional

import numpy as np

from pump_test_bench.app.diagnosis.checks import ABNORMAL, WARNING


def thresholds(th: Dict, kind: str, std: Optional[float], sigma: Optional[Dict] = None, mode: str = "relative"):
    """返回 (预警, 异常) 阈值 = max(下限, 倍数 × 标定离散)。绝对偏差的下限在 floor_warn_abs / floor_alarm_abs
    （温度沿用 floor_warn，单位 ℃），相对偏差的下限在 floor_warn / floor_alarm。"""
    sw = (sigma or {}).get("sigma_warn") or th.get("sigma_warn", 3)
    sa = (sigma or {}).get("sigma_alarm") or th.get("sigma_alarm", 5)
    if mode == "absolute":
        from pump_test_bench.app.simulation.config import DEFAULT_ABS_FLOORS
        dw, da = DEFAULT_ABS_FLOORS.get(kind, (1.0, 2.0))
        fw = th.get("floor_warn_abs", {}).get(kind, th.get("floor_warn", {}).get(kind, dw) if kind == "temperature" else dw)
        fa = th.get("floor_alarm_abs", {}).get(kind, th.get("floor_alarm", {}).get(kind, da) if kind == "temperature" else da)
    else:
        fw = th.get("floor_warn", {}).get(kind, 0.05)
        fa = th.get("floor_alarm", {}).get(kind, 0.08)
    if std:
        return max(fw, sw * std), max(fa, sa * std)
    return fw, fa


def _num(v: float) -> str:
    return f"{v:.0f}" if abs(v) >= 100 else f"{v:.1f}" if abs(v) >= 1 else f"{v:.3f}"


def _fmt(value: float, unit: str) -> str:
    return f"{value:.3f} {unit}" if unit == "MPa" else f"{value:.1f} {unit}"


def fmt_residual(r: float, mode: str, unit: str = "") -> str:
    return f"{r:+.1f} {unit}".rstrip() if mode == "absolute" else f"{r * 100:+.2f}%"


def fmt_limit(v: float, mode: str, unit: str = "") -> str:
    return f"±{v:.1f} {unit}".rstrip() if mode == "absolute" else f"±{v * 100:.1f}%"


def summary_rows(result: Dict) -> List[Dict]:
    """报告“检测明细”用：每个模型输出一行（多个测点取中位数）。"""
    out = []
    by_output: Dict[str, List[Dict]] = {}
    for r in result.get("rows", []):
        by_output.setdefault(r["output"], []).append(r)
    for name, rs in by_output.items():
        res = float(np.median([r["residual"] for r in rs]))
        expected = float(np.median([r["expected"] for r in rs]))
        mode, unit = rs[0]["mode"], rs[0]["unit"]
        out.append({"name": f"{result['name']}：{name}",
                    "reference": f"预期 {_fmt(expected, unit)}，{fmt_limit(rs[0]['warn'], mode, unit)}",
                    "value": fmt_residual(res, mode, unit) + (f"（{len(rs)} 个测点中位数）" if len(rs) > 1 else ""),
                    "abnormal": any(r["severity"] in (WARNING, ABNORMAL) for r in rs)})
    return out
