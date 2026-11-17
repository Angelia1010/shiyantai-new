"""分段检查：只有一个信号可比、不参与流量隔离的部分。

- 供油段：P9 在供油流量计上游、P1 在被试泵进口，P1 由增压泵闭环控制在设定值。P9 相对模型预期的偏离
  反映供油段（流量计、滤网、管路）的阻力，或 P9 / P1 传感器的偏差。单次测试分不清三者，按偏离方向
  给出可能性的先后；偏差随流量变大更像阻力（堵塞），各流量下相同更像传感器零点漂移（看历史趋势）。
- 温升：回油温度1-1 相对模型预期（由供油温度1-2、电传转速、P1 给出）的偏离，反映被试泵发热异常或
  两只温度传感器之一偏差（现在没有同位置的冗余温度传感器，分不清是哪一只）。
"""
from typing import Dict, List, Optional

from pump_test_bench.app.diagnosis.bench_signals import (CONTROL_PRESSURE, INLET_PRESSURE, RETURN_TEMPERATURE,
                                                          SUPPLY_TEMPERATURE, SignalSet)
from pump_test_bench.app.diagnosis.checks import INFO, NOTICE, finding, grade
from pump_test_bench.app.diagnosis.expectation import REFERENCE, ModelView
from pump_test_bench.app.diagnosis.sensor_checks import SensorStatus


def _limits(th: Dict, sigma: float, scaled: bool):
    if scaled and sigma:
        return max(th["warn"], 4 * sigma), max(th["alarm"], 8 * sigma)
    return th["warn"], th["alarm"]


def _usable(signals: SignalSet, status: Dict[str, SensorStatus], key: str) -> Optional[str]:
    col = signals.column(key)
    st = status.get(col) if col else None
    return col if st and st.usable else None


def _make(view: ModelView, category: str, sev: str, title: str, detail: str, target: str, label: str,
          component: Optional[str], value: float, limit: str, hypotheses: List[str]) -> Dict:
    f = finding(category, sev, title, detail, target, label, component, value, limit)
    f["hypotheses"] = hypotheses
    if view.mode == REFERENCE:
        f["raw_severity"], f["severity"], f["reference_only"] = sev, NOTICE, True
    return f


def supply_section(signals: SignalSet, status: Dict[str, SensorStatus], view: ModelView, cfg: Dict,
                   scaled: bool) -> List[Dict]:
    p9, p1 = _usable(signals, status, CONTROL_PRESSURE), _usable(signals, status, INLET_PRESSURE)
    e = view.get(p9) if p9 else None
    if not e or not p1:
        return []
    measured = status[p9].mean
    r = e.residual(measured)
    th = cfg["thresholds"]["supply_drop"]
    warn, alarm = _limits(th, e.sigma, scaled)
    sev = grade(r, warn, alarm)
    if sev == INFO:
        return []
    p1v = status[p1].mean
    drop, exp_drop = measured - p1v, e.value - p1v
    if r > 0:
        hyps = ["供油段阻力增大（供油流量计、滤网或管路堵塞）", "P9控制腔压力 传感器偏高", "P1进口压力 传感器偏低（实际进口压力高于读数）"]
    else:
        hyps = ["P1进口压力 传感器偏高（读数在设定值，实际进口压力偏低）", "P9控制腔压力 传感器偏低"]
    detail = (f"P9 实测 {measured:.3f} MPa，模型预期 {e.value:.3f} MPa，偏离 {r:+.3f} MPa；"
              f"P9 与 P1 之差 {drop:.3f} MPa（预期 {exp_drop:.3f} MPa）。可能：" + "；".join(hyps))
    s = signals.by_column(p9)
    return [_make(view, "supply_drop", sev, "供油段压差异常", detail, p9, "供油段（P9–P1）", s.component, r,
                  f"预警 ±{warn:.3f} MPa，异常 ±{alarm:.3f} MPa", hyps)]


def temperature_rise(signals: SignalSet, status: Dict[str, SensorStatus], view: ModelView, cfg: Dict,
                     scaled: bool) -> List[Dict]:
    tr, ts = _usable(signals, status, RETURN_TEMPERATURE), _usable(signals, status, SUPPLY_TEMPERATURE)
    e = view.get(tr) if tr else None
    if not e or not ts:
        return []
    measured = status[tr].mean
    r = e.residual(measured)
    th = cfg["thresholds"]["temperature_rise"]
    warn, alarm = _limits(th, e.sigma, scaled)
    sev = grade(r, warn, alarm)
    if sev == INFO:
        return []
    supply = status[ts].mean
    if r > 0:
        hyps = ["被试泵发热增大（容积效率下降、内泄漏增大）", "回油温度1-1 传感器偏高", "供油温度1-2 传感器偏低"]
    else:
        hyps = ["回油温度1-1 传感器偏低", "供油温度1-2 传感器偏高"]
    detail = (f"回油温度1-1 实测 {measured:.1f} ℃，按供油温度1-2（{supply:.1f} ℃）与工况预期 {e.value:.1f} ℃，"
              f"偏离 {r:+.1f} ℃；温升 {measured - supply:+.1f} ℃（预期 {e.value - supply:+.1f} ℃）。可能："
              + "；".join(hyps))
    s = signals.by_column(tr)
    return [_make(view, "temperature_rise", sev, "温升异常", detail, tr, "温升（回油−供油）", s.component, r,
                  f"预警 ±{warn:.1f} ℃，异常 ±{alarm:.1f} ℃", hyps)]
