"""主油路的流量诊断：把两只流量计、P5、P6 与模型预期一起做故障隔离，必要时做涡轮流量计二级诊断。

流程：
1. 变点检测：各观测信号相对模型预期的偏离在稳定段内是否突变或渐变；有则只用变化之后的数据；
2. 构造观测量（hypotheses.py 说明了含义），在故障假设中找最简洁一致的解释（isolation.py）；
3. 一级结论怀疑某只流量计（可能性 ≥ turbine.trigger_probability）时，用涡轮流量计模型复核该表，
   以较低权重并入观测量后重新隔离（turbine_check.py）；
4. 最可能解释中超过阈值的原因成为发现；输出管路摘要（各表偏差、供回油平衡、隔离结论）。
模型不可用时退化为两只流量计互相比较（扣除健康基准中的固有差异），只能发现“不一致”，不能定位。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from pump_test_bench.app.diagnosis import changepoint, checks as ck, hypotheses as hy, isolation as iso, turbine_check
from pump_test_bench.app.diagnosis.bench_signals import (BACK_PRESSURE, OUTLET_PRESSURE, RETURN_FLOW,
                                                          SUPPLY_FLOW, SignalSet)
from pump_test_bench.app.diagnosis.changepoint import RAMP, Change
from pump_test_bench.app.diagnosis.checks import INFO, NOTICE, SEVERITY_RANK, WARNING, finding, grade
from pump_test_bench.app.diagnosis.expectation import REFERENCE, ModelView
from pump_test_bench.app.diagnosis.sensor_checks import SensorStatus
from pump_test_bench.app.diagnosis.tolerances import features

METER_KINDS = (hy.METER, hy.METERS_COMMON)


@dataclass
class FlowContext:
    cfg: Dict
    baseline: Optional[Dict]
    seg: pd.DataFrame
    seg_t: np.ndarray
    signals: SignalSet
    status: Dict[str, SensorStatus]
    view: ModelView
    sims: list = field(default_factory=list)
    density_fn: object = None
    temperature: Optional[float] = None

    def usable(self, key: str) -> Optional[str]:
        col = self.signals.column(key)
        st = self.status.get(col) if col else None
        return col if st and st.usable else None

    def label(self, col: str) -> str:
        s = self.signals.by_column(col)
        return s.label if s else col


@dataclass
class FlowResult:
    findings: List[Dict]
    loop: Dict
    observations: List[iso.Observation] = field(default_factory=list)   # 建健康基准时估计离散用
    change: Optional[Change] = None


# --------------------------------------------------------------------------- 阈值与离散
def _sigma(ctx: FlowContext, key: str, kind: str) -> float:
    iso_cfg = ctx.cfg["isolation"]
    learned = ((ctx.baseline or {}).get("isolation") or {}).get("sigma", {}).get(key)
    floor = iso_cfg.get("sigma_floor", {}).get(kind, 0.0)
    return max(learned or iso_cfg["sigma"].get(key, 0.01), floor)


def _limits(ctx: FlowContext, kind: str, sigma: float) -> Tuple[float, float]:
    th = ctx.cfg["thresholds"]["faults"][kind]
    if (ctx.baseline or {}).get("isolation"):
        return max(th["warn"], 4 * sigma), max(th["alarm"], 8 * sigma)
    return th["warn"], th["alarm"]


def _cause_sigma(ctx: FlowContext, cause: iso.Cause, obs: Dict[str, iso.Observation]) -> float:
    if cause.kind == hy.FLOW_CHANGE:
        return obs[hy.ANCHOR].sigma
    return max(obs[k].sigma for k in cause.keys if k in obs)


# --------------------------------------------------------------------------- 读数与变点
def _observed_columns(ctx: FlowContext) -> List[str]:
    cols = [ctx.usable(k) for k in (SUPPLY_FLOW, RETURN_FLOW, OUTLET_PRESSURE, BACK_PRESSURE)]
    return [c for c in cols if c and (ctx.view.get(c) or c in (ctx.usable(SUPPLY_FLOW), ctx.usable(RETURN_FLOW)))]


def _scale(ctx: FlowContext, col: str) -> float:
    s = ctx.signals.by_column(col)
    kind = "meter" if s and s.kind == "flow" else "pressure_sensor"
    return ctx.cfg["thresholds"]["faults"][kind]["warn"]


def _current_state(ctx: FlowContext, cols: List[str]) -> Tuple[Optional[Change], Dict[str, float], pd.DataFrame]:
    """返回 (变化, 代表当前状态的各信号均值, 当前状态的数据行)。"""
    frame = ctx.seg[cols].apply(pd.to_numeric, errors="coerce")
    full = {c: float(frame[c].mean()) for c in cols}
    window = ctx.cfg["steady"]["window_s"]
    wm = ck.window_means(frame, ctx.seg_t, window).dropna()
    if wm.empty:
        return None, full, ctx.seg
    rel = {}
    for c in cols:
        e = ctx.view.get(c)
        ref = e.value if e and e.mode == "relative" else float(wm[c].mean())
        rel[c] = wm[c].to_numpy(dtype=float) / ref - 1
    change = changepoint.detect(wm.index.to_numpy(dtype=float) * window, rel, {c: _scale(ctx, c) for c in cols},
                                changepoint.Options.from_config(ctx.cfg.get("changepoint")))
    if change is None:
        return None, full, ctx.seg
    first = wm.index[change.current_from]
    ids = np.floor((ctx.seg_t - ctx.seg_t[0]) / window).astype(int)
    current = ctx.seg.iloc[np.flatnonzero(ids >= first)]
    return change, {c: float(wm[c].iloc[change.current_from:].mean()) for c in cols}, current


# --------------------------------------------------------------------------- 观测量
def _observations(ctx: FlowContext, readings: Dict[str, float]) -> Tuple[List[iso.Observation], hy.Layout]:
    S, R = ctx.usable(SUPPLY_FLOW), ctx.usable(RETURN_FLOW)
    obs = []
    for col in (S, R):
        e = ctx.view.get(col) if col else None
        if e and col in readings:
            obs.append(iso.Observation(col, e.residual(readings[col]), _sigma(ctx, col, "flow")))
    pressures = {}
    for key in (OUTLET_PRESSURE, BACK_PRESSURE):
        col = ctx.usable(key)
        e = ctx.view.get(col) if col else None
        if e and e.mode == "relative" and col in readings:
            elastic = ctx.view.elasticity.get(col, 0.8)
            pressures[col] = elastic
            obs.append(iso.Observation(col, e.residual(readings[col]), _sigma(ctx, col, "pressure"), elastic))
    obs.append(iso.Observation(hy.ANCHOR, 0.0, _sigma(ctx, hy.ANCHOR, "anchor")))
    return obs, hy.Layout(S or ctx.signals.column(SUPPLY_FLOW), R or ctx.signals.column(RETURN_FLOW), pressures, {})


def _isolate(ctx: FlowContext, obs: List[iso.Observation], layout: hy.Layout) -> Optional[iso.Isolation]:
    o = ctx.cfg["isolation"]
    pool = hy.catalog(layout, [x.key for x in obs], o["cause_cost"], o["group_cost"])
    return iso.isolate(obs, pool, iso.Options(o.get("max_causes", 2)))


def _second_tier(ctx: FlowContext, result: iso.Isolation, obs: List[iso.Observation], layout: hy.Layout,
                 current: pd.DataFrame) -> Tuple[iso.Isolation, List[iso.Observation], hy.Layout, List[Dict]]:
    """一级结论怀疑流量计时做涡轮流量计复核，以较低权重并入观测后重新隔离。"""
    tcfg = ctx.cfg.get("turbine") or {}
    weight, trigger = tcfg.get("weight", 0.3), tcfg.get("trigger_probability", 0.05)
    checks, extra = [], []
    for col in (layout.supply, layout.ret):
        if col not in [x.key for x in obs]:
            continue
        before = result.probability_of(lambda f, c=col: hy.involves(f, c))
        if before < trigger:
            continue
        tc = turbine_check.check(current, ctx.cfg, col, ctx.sims, ctx.density_fn, ctx.baseline, ctx.temperature)
        item = {**tc.as_dict(), "label": ctx.label(col), "probability_before": round(before, 3)}
        checks.append(item)
        if tc.available:
            key = hy.turbine_key(col)
            extra.append(iso.Observation(key, tc.residual, tc.sigma / np.sqrt(weight), 0.0))
            layout.turbine[col] = key
    if not extra:
        return result, obs, layout, checks
    obs = obs + extra
    result = _isolate(ctx, obs, layout) or result
    for item in checks:
        if not item["available"]:
            continue
        after = result.probability_of(lambda f, c=item["meter"]: hy.involves(f, c))
        item["probability_after"] = round(after, 3)
        item["verdict"] = "支持" if after > item["probability_before"] + 0.05 else (
            "不支持" if after < item["probability_before"] - 0.05 else "无明显影响")
    return result, obs, layout, checks


# --------------------------------------------------------------------------- 结论
def _change_finding(fault: Dict, cause: iso.Cause, change: Change) -> Optional[Dict]:
    moved = {k: v for k, v in change.shifts.items() if k in cause.keys or (cause.kind == hy.LEAK and k == cause.keys[0])}
    if not moved:
        return None
    key = max(moved, key=lambda k: abs(moved[k]))
    title = "偏差在测试中持续变化" if change.kind == RAMP else "偏差在测试中突然变化"
    f = finding("trend", WARNING, title, f"{fault['label']}{hy.change_text(change.kind, change.onset_s, moved[key])}",
                fault["target"], fault["label"], fault["component"], moved[key] * 100)
    f["change"] = {"kind": change.kind, "onset_s": change.onset_s}
    return f


def _unexplained_change(ctx: FlowContext, change: Change, explained: List[str]) -> Optional[Dict]:
    """测试中出现了明显变化，但当前状态没有超过阈值的故障（如间歇性故障已恢复）：作为预警报出。"""
    rest = {k: v for k, v in change.shifts.items() if k not in explained and abs(v) > _scale(ctx, k)}
    if not rest:
        return None
    key = max(rest, key=lambda k: abs(rest[k]))
    s = ctx.signals.by_column(key)
    how = "逐渐" if change.kind == RAMP else "突然"
    f = finding("trend", WARNING, "偏差在测试中发生变化",
                f"{ctx.label(key)}相对模型预期的偏离在第 {change.onset_s:.0f} 秒起{how}变化了 {rest[key] * 100:+.2f}%，"
                "测试末段未超过阈值，可能是间歇性故障", key, ctx.label(key), s.component if s else None,
                rest[key] * 100, f"±{_scale(ctx, key) * 100:.1f}%")
    f["change"] = {"kind": change.kind, "onset_s": change.onset_s}
    return f


def _explain(ctx: FlowContext, result: iso.Isolation, readings: Dict[str, float], change: Optional[Change],
             turbine: List[Dict]) -> Tuple[List[Dict], Dict[str, str]]:
    labels = {c: ctx.label(c) for c in readings}
    labels[hy.ANCHOR] = "实际流量"
    expected = {c: ctx.view.get(c).value for c in readings if ctx.view.get(c)}
    fit, alt_p = result.best, ctx.cfg["isolation"].get("alternative_probability", 0.05)
    obs = {o.key: o for o in result.observations}
    reference_only = ctx.view.mode == REFERENCE
    findings, faulty = [], {}
    for cause in fit.causes:
        v = fit.magnitude(cause)
        warn, alarm = _limits(ctx, cause.kind, _cause_sigma(ctx, cause, obs))
        sev = grade(v, warn, alarm)
        if sev == INFO:
            continue
        col = cause.keys[0]
        s = ctx.signals.by_column(col)
        if cause.kind in (hy.METER, hy.PRESSURE_SENSOR):
            target, label, component = col, labels.get(col, col), s.component if s else None
        elif cause.kind == hy.FLOW_CHANGE:
            target, label, component = "被试泵", "被试泵/电传", "被试件1高低压双联泵"
        elif cause.kind == hy.RETURN_RESISTANCE:
            target, label, component = "回油管路", "回油管路", "回油管路"
        else:
            target, label, component = "主油路", "主油路", "回油管路" if cause.kind == hy.LEAK else None
        f = finding(hy.CATEGORY[cause.kind], sev, hy.TITLE[cause.kind],
                    hy.detail(cause, fit, labels, readings, expected), target, label, component, v * 100,
                    f"预警 ±{warn * 100:.1f}%，异常 ±{alarm * 100:.1f}%")
        # 原因的可能性：包含该原因的所有解释的可能性之和；其他可能：不包含该原因的解释
        others = [f2 for f2 in result.ranked if cause.id not in f2.ids and f2.probability >= alt_p][:3]
        f["fault"] = {"kind": cause.kind, "keys": list(cause.keys), "summary": hy.describe_fit(fit, labels),
                      "probability": round(result.probability_of(lambda f2, i=cause.id: i in f2.ids), 3),
                      "alternatives": [{"text": hy.describe_fit(f2, labels), "probability": round(f2.probability, 3)}
                                       for f2 in others],
                      "turbine": [t for t in turbine if t["meter"] in cause.keys]}
        if reference_only:
            f["raw_severity"], f["severity"], f["reference_only"] = sev, NOTICE, True
        findings.append(f)
        if change:
            extra = _change_finding({**f, "target": target, "label": label, "component": component}, cause, change)
            if extra:
                f["fault"]["change"] = extra["change"]
                if reference_only:
                    extra["severity"] = NOTICE
                findings.append(extra)
        if cause.kind in METER_KINDS + (hy.PRESSURE_SENSOR,):
            for k in cause.keys:
                if SEVERITY_RANK[sev] > SEVERITY_RANK[faulty.get(k, INFO)]:
                    faulty[k] = sev
    if change:
        explained = [k for f in findings for k in (f.get("fault") or {}).get("keys", [])]
        extra = _unexplained_change(ctx, change, explained)
        if extra:
            findings.append(extra)
    return findings, faulty


def _meter_part(fit: iso.Fit, obs: List[iso.Observation], flows: List[str], column: str) -> float:
    """流量计自身的偏差：该表读数相对“不依赖流量计的实际流量估计”的偏离。
    实际流量由 P5、P6 与模型参照估计（考虑最可能解释中与流量计无关的原因，如泄漏、实际流量变化）。
    两只流量计不互相参照：否则一只表漂移会让另一只看起来也偏了，没选出故障的小偏差也会被吸收一部分，
    历史趋势就看不出慢漂移。"""
    target = next(o for o in obs if o.key == column)
    others = [o for o in obs if o.key not in flows and not o.key.startswith("涡轮模型:")]
    causes = tuple(c for c in fit.causes if c.kind not in METER_KINDS and not set(c.keys) & set(flows)
                   or c.kind == hy.LEAK)
    ref = iso.fit(others, causes, strict=False)
    if ref is None:
        return fit.residuals[column] + sum(v * c.effects[j].get(column, 0.0) for c in fit.causes
                                           if c.kind in METER_KINDS for j, v in enumerate(fit.params[c.id]))
    explained = ref.level * target.level + sum(v * c.effects[j].get(column, 0.0) for c in causes
                                               for j, v in enumerate(ref.params[c.id]))
    return target.value - explained


# --------------------------------------------------------------------------- 无模型时：两只流量计互相比较
def _pair_bias(ctx: FlowContext, flow: float) -> Tuple[float, float]:
    b = ((ctx.baseline or {}).get("pair") or {})
    if b.get("coef") and ctx.temperature is not None:
        return float(np.dot(b["coef"], features(flow, ctx.temperature, b["ranges"]))), b.get("std", 0.0)
    return float(b.get("bias", 0.0)), float(b.get("std", 0.0))


def _compare_pair(ctx: FlowContext, readings: Dict[str, float]) -> Tuple[List[Dict], Optional[Dict]]:
    S, R = ctx.usable(SUPPLY_FLOW), ctx.usable(RETURN_FLOW)
    if not (S and R and S in readings and R in readings):
        return [], None
    mean = (readings[S] + readings[R]) / 2
    raw = (readings[S] - readings[R]) / mean
    bias, std = _pair_bias(ctx, mean)
    th = ctx.cfg["thresholds"]["faults"]["meter"]
    warn, alarm = max(th["warn"], 4 * std), max(th["alarm"], 8 * std)
    d = raw - bias
    sev = grade(d, warn, alarm)
    balance = {"raw": raw, "bias": bias, "corrected": d, "warn": warn, "alarm": alarm, "severity": sev}
    if sev == INFO:
        return [], balance
    f = finding("pair", sev, "两只流量计不一致",
                f"{ctx.label(S)} 比 {ctx.label(R)} {'高' if d > 0 else '低'} {abs(d) * 100:.2f}%（已扣除健康时的固有差异）。"
                "没有可用的仿真模型参照，无法判断是哪一只流量计、还是供回油之间泄漏",
                "主油路", "主油路", None, d * 100, f"预警 ±{warn * 100:.1f}%，异常 ±{alarm * 100:.1f}%")
    return [f], balance


# --------------------------------------------------------------------------- 入口
def diagnose(ctx: FlowContext) -> FlowResult:
    cols = _observed_columns(ctx)
    flows = [c for c in (ctx.usable(SUPPLY_FLOW), ctx.usable(RETURN_FLOW)) if c]
    change, readings, current = _current_state(ctx, cols) if cols else (None, {}, ctx.seg)
    loop = {"name": "主油路", "active": True, "temperature": ctx.temperature,
            "consensus": float(np.mean([readings[c] for c in flows])) if flows else None,
            "meters": [], "balance": None, "mass": None, "checked": False}
    findings: List[Dict] = []
    observations: List[iso.Observation] = []
    faulty: Dict[str, str] = {}
    corrected: Dict[str, float] = {}

    use_model = ctx.view.available and any(ctx.view.get(c) for c in flows)
    if use_model:
        obs, layout = _observations(ctx, readings)
        result = _isolate(ctx, obs, layout)
        if result is not None:
            result, obs, layout, turbine = _second_tier(ctx, result, obs, layout, current)
            findings, faulty = _explain(ctx, result, readings, change, turbine)
            observations = [o for o in obs if not o.key.startswith("涡轮模型:")]
            fit = result.best
            labels = {o.key: ctx.label(o.key) for o in obs}
            labels[hy.ANCHOR] = "实际流量"
            loop["isolation"] = {
                "explanation": hy.describe_fit(fit, labels), "probability": round(fit.probability, 3),
                "alternatives": [{"text": hy.describe_fit(f, labels), "probability": round(f.probability, 3)}
                                 for f in result.alternatives(ctx.cfg["isolation"].get("alternative_probability", 0.05))],
                "change": {"kind": change.kind, "onset_s": change.onset_s} if change else None,
                "level": fit.level,
                "observations": [{"key": o.key, "value": o.value, "sigma": o.sigma, "fitted": o.value - fit.residuals[o.key],
                                  "residual": fit.residuals[o.key]} for o in obs],
                "turbine": turbine,
            }
            corrected = {c: _meter_part(fit, obs, flows, c) for c in flows if c in [o.key for o in obs]}
            S, R = layout.supply, layout.ret
            if S in readings and R in readings and ctx.view.get(S) and ctx.view.get(R):
                mean = (readings[S] + readings[R]) / 2
                raw = (readings[S] - readings[R]) / mean
                leak = [f for f in findings if f["category"] == "balance"]
                th = ctx.cfg["thresholds"]["faults"]["leak"]
                loop["balance"] = {"raw": raw, "bias": raw - (ctx.view.get(S).residual(readings[S])
                                                               - ctx.view.get(R).residual(readings[R])),
                                   "corrected": ctx.view.get(S).residual(readings[S]) - ctx.view.get(R).residual(readings[R]),
                                   "warn": th["warn"], "alarm": th["alarm"],
                                   "severity": leak[0]["severity"] if leak else INFO}
            loop["checked"] = True
    if not use_model or ctx.view.mode == REFERENCE:
        pair, balance = _compare_pair(ctx, readings)
        findings += pair
        if balance and not loop.get("balance"):
            loop["balance"] = balance
        loop["checked"] = loop["checked"] or balance is not None

    th = ctx.cfg["thresholds"]["faults"]["meter"]
    for col in [c for c in (ctx.signals.column(SUPPLY_FLOW), ctx.signals.column(RETURN_FLOW)) if c]:
        s, st = ctx.signals.by_column(col), ctx.status.get(col)
        entry = {"column": col, "label": s.label, "group": "供油" if col == ctx.signals.column(SUPPLY_FLOW) else "回油",
                 "component": s.component, "mean": readings.get(col, st.mean if st else None),
                 "cv": st.cv if st else None, "severity": st.severity if st else INFO}
        if col in corrected:
            entry.update(corrected=corrected[col], warn=th["warn"], alarm=th["alarm"],
                         severity=max(entry["severity"], faulty.get(col, INFO), key=lambda x: SEVERITY_RANK[x]))
        if st and not st.usable:
            entry["stuck"] = True
        loop["meters"].append(entry)
    return FlowResult(findings, loop, observations, change)
