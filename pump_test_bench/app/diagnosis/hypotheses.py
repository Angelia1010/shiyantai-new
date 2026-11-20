"""标准台的故障假设目录：每种原因会让哪些观测量怎样变化。

观测量（都是相对健康预期的相对偏离，见 flow_diagnosis.py）：
- 供油流量1-2、回油流量1-2：流量计读数 / 模型预期 − 1，对实际流量的灵敏度为 1；
- P5、P6：压力 / 模型预期 − 1，对实际流量的灵敏度为弹性 e（P5、P6 ≈ 0.8，流量越大压力越高）；
- 实际流量（锚点）：恒为 0，代表“模型按电传转速、油温估算的被试泵流量”，给实际流量偏移一个先验；
- 涡轮模型:<表>（二级诊断，可选）：该表按涡轮流量计模型（以回油质量流量为参照）换算的偏离，
  对实际流量不敏感（质量流量计同样测到实际流量的变化），权重较低。

原因（括号内为影响的观测量与符号）：
- meter            某只流量计偏离（该表、该表的涡轮模型观测）；
- flow_change      实际流量与模型预期不符：被试泵出力变化或电传转速信号偏差（锚点）；
- leak             供回油之间泄漏 λ ≥ 0（回油流量 −λ，P5/P6 −e·λ；供油表相对回油质量流量多 λ）；
- meters_common    两只流量计同时、同样偏离（油品粘度变化、同批次、同一采集模块）；
- return_resistance 回油管路阻力增大（P5、P6 同时升高）；
- pressure_sensor  P5 或 P6 单个传感器偏离。
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

from pump_test_bench.app.diagnosis import isolation as iso

ANCHOR = "实际流量"
METER, FLOW_CHANGE, LEAK = "meter", "flow_change", "leak"
METERS_COMMON, RETURN_RESISTANCE, PRESSURE_SENSOR = "meters_common", "return_resistance", "pressure_sensor"

# 原因 → 发现的类别（causes.py 按类别归因；沿用的类别名与历史报告兼容）
CATEGORY = {METER: "redundancy", FLOW_CHANGE: "flow_change", LEAK: "balance", METERS_COMMON: "common_mode",
            RETURN_RESISTANCE: "resistance", PRESSURE_SENSOR: "pressure"}
TITLE = {METER: "流量计读数偏离", FLOW_CHANGE: "实际流量与模型预期不符", LEAK: "供回油流量不平衡",
         METERS_COMMON: "两只流量计同时偏离", RETURN_RESISTANCE: "回油管路阻力变化", PRESSURE_SENSOR: "压力传感器偏离"}


def turbine_key(column: str) -> str:
    return f"涡轮模型:{column}"


@dataclass(frozen=True)
class Layout:
    """参与隔离的观测量所对应的列。"""
    supply: str
    ret: str
    pressures: Dict[str, float]          # 压力列 → 对实际流量的弹性（P5、P6）
    turbine: Dict[str, str]              # 流量计列 → 涡轮模型观测的 key（只含已做二级诊断的表）


def catalog(layout: Layout, present: List[str], cause_cost: float, group_cost: float) -> List[iso.Cause]:
    """present：本次实际有的观测量。只生成能被观测到的原因。"""
    have = set(present)
    c, g = cause_cost, group_cost
    S, R = layout.supply, layout.ret
    tS, tR = layout.turbine.get(S), layout.turbine.get(R)

    def eff(d: Dict[str, float]) -> Dict[str, float]:
        return {k: v for k, v in d.items() if k in have}

    out: List[iso.Cause] = []
    for col, t in ((S, tS), (R, tR)):
        if col in have:
            out.append(iso.Cause(METER, (col,), (eff({col: 1.0, t: 1.0} if t else {col: 1.0}),), (iso.FREE,), c))
    if ANCHOR in have:
        out.append(iso.Cause(FLOW_CHANGE, (ANCHOR,), ({ANCHOR: 1.0},), (iso.FREE,), c))
    if R in have and (S in have or ANCHOR in have):
        leak = {R: -1.0, **{p: -e for p, e in layout.pressures.items()}}
        if tS:
            leak[tS] = 1.0
        out.append(iso.Cause(LEAK, (R,), (eff(leak),), (iso.NON_NEGATIVE,), c))
    if S in have and R in have and ANCHOR in have:
        common = {S: 1.0, R: 1.0, **({tS: 1.0} if tS else {}), **({tR: 1.0} if tR else {})}
        out.append(iso.Cause(METERS_COMMON, (S, R), (eff(common),), (iso.FREE,), c + g))
    pressures = [p for p in layout.pressures if p in have]
    if len(pressures) == 2:
        out.append(iso.Cause(RETURN_RESISTANCE, tuple(pressures), ({p: 1.0 for p in pressures},),
                             (iso.NON_NEGATIVE,), c))
    for p in pressures:
        out.append(iso.Cause(PRESSURE_SENSOR, (p,), ({p: 1.0},), (iso.FREE,), c))
    return out


def involves(fit: iso.Fit, column: str) -> bool:
    """解释中是否有“该流量计偏离”（单表或两表同时偏）。"""
    return any(cause.kind in (METER, METERS_COMMON) and column in cause.keys for cause in fit.causes)


# --------------------------------------------------------------------------- 描述
def _pct(v: float) -> str:
    return f"{abs(v) * 100:.2f}%"


def describe_cause(cause: iso.Cause, fit: iso.Fit, labels: Dict[str, str]) -> str:
    """一个原因的简短描述，如“回油流量1-2 偏低 3.00%”。"""
    v = fit.magnitude(cause)
    hl = "偏高" if v > 0 else "偏低"
    name = labels.get(cause.keys[0], cause.keys[0])
    if cause.kind == METER:
        return f"{name} {hl} {_pct(v)}"
    if cause.kind == FLOW_CHANGE:  # 锚点偏离为正：模型预期高于实际，即实际流量偏低
        return f"实际流量比模型预期{'低' if v > 0 else '高'} {_pct(v)}（被试泵出力或电传转速信号）"
    if cause.kind == LEAK:
        return f"供回油之间泄漏 {_pct(v)}"
    if cause.kind == METERS_COMMON:
        return f"两只流量计同时{hl} {_pct(v)}"
    if cause.kind == RETURN_RESISTANCE:
        return f"回油管路阻力增大（P5、P6 升高 {_pct(v)}）"
    return f"{name} 传感器{hl} {_pct(v)}"


def describe_fit(fit: iso.Fit, labels: Dict[str, str]) -> str:
    return "、".join(describe_cause(c, fit, labels) for c in fit.causes) or "各信号都正常"


def detail(cause: iso.Cause, fit: iso.Fit, labels: Dict[str, str], readings: Dict[str, float],
           expected: Dict[str, float]) -> str:
    """发现的说明文字：用数据说明为什么是这个原因。"""
    v = fit.magnitude(cause)
    col = cause.keys[0]
    name = labels.get(col, col)

    def vs(c: str) -> str:
        if c not in readings or c not in expected:
            return ""
        return f"{labels.get(c, c)} 实测 {readings[c]:.4g}、预期 {expected[c]:.4g}（{(readings[c] / expected[c] - 1) * 100:+.1f}%）"

    if cause.kind == METER:
        return (f"{name}比其余信号推算的实际流量{'高' if v > 0 else '低'} {_pct(v)}，其余信号彼此一致。"
                + vs(col))
    if cause.kind == FLOW_CHANGE:
        parts = [vs(c) for c in readings if c in expected]
        return (f"两只流量计和 P5、P6 一致地{'低' if v > 0 else '高'}于模型按电传转速、油温给出的预期，"
                f"实际流量比预期{'少' if v > 0 else '多'}约 {_pct(v)}。" + "；".join(p for p in parts if p))
    if cause.kind == LEAK:
        return (f"供油流量与模型预期一致，回油流量以及随回油流量变化的 P5、P6 一起偏低，"
                f"回油比供油少约 {_pct(v)}，油没有全部回来。" + "；".join(p for p in (vs(c) for c in readings) if p))
    if cause.kind == METERS_COMMON:
        return (f"两只流量计一致地{'高' if v > 0 else '低'}于预期约 {_pct(v)}，而随流量变化的 P5、P6 与预期一致，"
                "说明实际流量没有变，是两只流量计共同的测量偏差")
    if cause.kind == RETURN_RESISTANCE:
        return (f"两只流量计正常，P5、P6 同时高于预期约 {_pct(v)}：流量没变而压力升高，回油管路（流量计、阀、滤网）阻力增大。"
                + "；".join(p for p in (vs(c) for c in cause.keys) if p))
    return f"{name} 偏离预期 {_pct(v)}，而与它相邻的压力和两只流量计都正常，更可能是该传感器本身偏了。" + vs(col)


def change_text(kind: str, onset_s: float, shift: Optional[float] = None) -> str:
    amount = f" {shift * 100:+.2f}%" if shift is not None else ""
    if kind == "ramp":
        return f"从第 {onset_s:.0f} 秒起逐渐变化{amount}，故障正在发展"
    return f"在第 {onset_s:.0f} 秒突然变化{amount}，结论按变化之后的数据给出"
