"""单信号自检：每个信号自己的读数是否可信（不需要和其他信号比较）。

检查项由 bench.json 中每个信号的 checks 决定：
- stuck    整个稳定段读数不变（卡死）；
- frozen   读数连续不变超过 max(min_s, min_ratio × 稳定段时长)（叶轮卡滞、变送器死机）；
- range    超出合理范围的读数超过 5%（断线、未接入、量程设置错误），按整个文件统计；
- dropout  流量计有流量时读数接近 0（信号线断开、叶轮卡死不转）；
- noise    流量计 1 秒内的波动超过 max(下限, 倍数 × 健康时的波动)；
- spike    毛刺（鲁棒 z 分数超限的点占比过高）；
- setpoint 被控量（P1）偏离最近的设定档位。
卡死、冻结、超量程、掉零的信号判为不可用，不参与后面的模型比较与故障隔离；噪声、毛刺不影响均值，仍可用。
"""
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from pump_test_bench.app.diagnosis import checks as ck
from pump_test_bench.app.diagnosis.bench_signals import Signal, SignalSet
from pump_test_bench.app.diagnosis.checks import ABNORMAL, INFO, WARNING, finding

KIND_NAME = {"flow": "流量计", "pressure": "压力传感器", "temperature": "温度传感器", "speed": "转速信号"}


@dataclass
class SensorStatus:
    signal: Signal
    mean: Optional[float]
    usable: bool = True
    severity: str = INFO
    cv: Optional[float] = None
    flags: Set[str] = field(default_factory=set)

    def as_dict(self) -> Dict:
        return {"column": self.signal.column, "label": self.signal.label, "unit": self.signal.unit,
                "kind": self.signal.kind, "mean": self.mean, "usable": self.usable, "severity": self.severity,
                "cv": self.cv, "flags": sorted(self.flags)}


def _frozen_limit(cfg: Dict, duration: float) -> float:
    fz = cfg["thresholds"].get("frozen", {})
    return max(fz.get("min_s", 2.0), fz.get("min_ratio", 0.2) * duration)


def _unusable(st: SensorStatus, flag: str, title: str, detail: str, value=None, threshold=None) -> Dict:
    st.usable, st.severity = False, ABNORMAL
    st.flags.add(flag)
    s = st.signal
    return finding("sensor" if flag in ("missing", "stuck", "range") else flag, ABNORMAL, title, detail,
                   s.column, s.label, s.component, value, threshold)


def _check_one(s: Signal, df: pd.DataFrame, seg: pd.DataFrame, seg_t: np.ndarray, duration: float,
               flow_level: float, cfg: Dict, baseline: Optional[Dict]) -> Tuple[SensorStatus, List[Dict]]:
    th, name = cfg["thresholds"], KIND_NAME.get(s.kind, "传感器")
    col = s.column
    st = SensorStatus(s, ck.mean_of(seg[col]))
    out: List[Dict] = []
    if st.mean is None:
        return st, [_unusable(st, "missing", f"{name}无有效数据", f"{s.label}在稳定段内没有有效读数")]
    if "range" in s.checks:
        rule = ck.range_rule(col, cfg.get("sensor_ranges", []))
        ratio = ck.out_of_range_ratio(df[col], rule) if rule else 0.0
        if ratio > 0.05:
            return st, [_unusable(st, "range", "传感器读数超出合理范围",
                                  f"{s.label} 有 {ratio * 100:.0f}% 的读数超出 [{rule['min']}, {rule['max']}]，"
                                  "可能是断线、未接入或量程设置错误", ck.mean_of(df[col]),
                                  f"[{rule['min']}, {rule['max']}]")]
    if "stuck" in s.checks and ck.is_stuck(seg[col]):
        return st, [_unusable(st, "stuck", f"{name}读数卡死",
                              f"{s.label}在 {duration:.0f} 秒内读数始终为 {st.mean:.3f}", st.mean)]
    if "dropout" in s.checks:
        zero = ck.zero_fraction(seg[col], flow_level)
        if zero >= th.get("dropout_ratio", 0.1):
            return st, [_unusable(st, "dropout", f"{name}读数掉零",
                                  f"管路流量约 {flow_level:.0f} L/h，{s.label}有 {zero * 100:.0f}% 的时间读数接近 0，"
                                  "可能是信号线断开、接插件脱落或叶轮卡死不转", zero * 100)]
    if "frozen" in s.checks:
        frozen, limit = ck.longest_constant_run(seg[col], seg_t), _frozen_limit(cfg, duration)
        if frozen >= limit:
            return st, [_unusable(st, "frozen", f"{name}读数冻结",
                                  f"{s.label}有 {frozen:.1f} 秒读数完全不变（健康数据中最长约 0.4 秒），"
                                  "可能是叶轮卡滞、变送器死机或采集通道停止更新", frozen, f"<{limit:.1f} 秒")]
    if "noise" in s.checks:
        st.cv = ck.window_cv(seg[col], seg_t, cfg["steady"]["window_s"])
        base_cv = ((baseline or {}).get("signals", {}).get(col) or {}).get("cv")
        limit = max(th["noise"]["floor"], th["noise"]["ratio"] * base_cv) if base_cv else th["noise"]["floor"]
        if st.cv is not None and st.cv > limit:
            st.flags.add("noise")
            out.append(finding("noise", WARNING, f"{name}读数波动过大",
                               f"{s.label}短时波动 {st.cv * 100:.2f}%，超过 {limit * 100:.2f}%",
                               col, s.label, s.component, st.cv * 100, f"≤{limit * 100:.2f}%"))
    if "spike" in s.checks:
        ratio = ck.spike_ratio(seg[col], th["spike"]["z"])
        if ratio > th["spike"]["ratio"]:
            st.flags.add("spike")
            out.append(finding("spike", WARNING, f"{name}读数有毛刺",
                               f"{s.label}有 {ratio * 100:.2f}% 的读数明显偏离（突跳），可能是接插件松动、干扰或脉冲丢失",
                               col, s.label, s.component, ratio * 100, f"≤{th['spike']['ratio'] * 100:.1f}%"))
    if "setpoint" in s.checks and s.setpoints:
        target = min(s.setpoints, key=lambda p: abs(p - st.mean))
        dev = st.mean - target
        sev = ck.grade(dev, th["setpoint"]["warn"], th["setpoint"]["alarm"])
        st.flags.add("setpoint")
        if sev != INFO:
            out.append(finding("setpoint", sev, "被控压力偏离设定值",
                               f"{s.label}为 {st.mean:.3f} {s.unit}，最近的设定档位是 {target:.2f} {s.unit}，"
                               f"相差 {dev:+.3f} {s.unit}；可能是增压泵控制不稳、或该传感器偏差",
                               col, s.label, s.component, dev,
                               f"±{th['setpoint']['warn']} / ±{th['setpoint']['alarm']} {s.unit}"))
    if out:
        st.severity = WARNING
    return st, out


def check_signals(df: pd.DataFrame, seg: pd.DataFrame, seg_t: np.ndarray, duration: float, signals: SignalSet,
                  cfg: Dict, baseline: Optional[Dict], flow_level: float,
                  only: Optional[Tuple[str, ...]] = None) -> Tuple[Dict[str, SensorStatus], List[Dict]]:
    """返回 ({列: 状态}, 发现)。flow_level：稳定段内的流量水平（掉零判断用）；only：只做这些检查。"""
    status, findings = {}, []
    for s in signals:
        if only is not None:
            s = replace(s, checks=tuple(c for c in s.checks if c in only))
        st, out = _check_one(s, df, seg, seg_t, duration, flow_level, cfg, baseline)
        status[s.column] = st
        findings += out
    return status, findings
