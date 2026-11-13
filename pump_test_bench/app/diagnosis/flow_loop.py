"""单条管路的流量诊断。

1. 无流量的管路：读数应接近零；
2. 有流量的管路：
   a. 传感器自检（无数据、卡死、掉零、冻结），坏掉的表不参与后面的比较；噪声与毛刺单独报；
   b. 变点检测：各表相对读数在稳定段内是否突变或渐变，有则只用变化之后（渐变取末段）的数据判断当前状态；
   c. 流量协调与故障隔离（见 reconcile.py / isolation.py）：在“单表偏离、泄漏、夹气、一侧整体偏、
      模型参照偏离……”等假设中找出最简洁一致的解释；
   d. 管路摘要：各表偏差、供回油平衡、质量-体积偏差，以及原经验公式（仅参考）。
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from pump_test_bench.app.core import flow_meter as legacy
from pump_test_bench.app.diagnosis import changepoint, checks as ck, isolation as iso, reconcile, tolerances
from pump_test_bench.app.diagnosis.checks import ABNORMAL, INFO, NOTICE, WARNING, finding
from pump_test_bench.app.diagnosis.fuel import density, valid_temperature
from pump_test_bench.app.diagnosis.signals import Segment


@dataclass
class Context:
    """一次诊断中各管路共用的输入。"""
    cfg: Dict
    baseline: Optional[Dict]
    segment: Segment
    seg: pd.DataFrame
    seg_t: np.ndarray
    fuel_density_20: Optional[float] = None
    anchor: Optional[reconcile.Anchor] = None

    @property
    def th(self) -> Dict:
        return self.cfg["thresholds"]

    @property
    def baseline_meters(self) -> Dict:
        return (self.baseline or {}).get("meters", {})


@dataclass
class LoopResult:
    summary: Dict
    findings: List[Dict]
    columns: Set[str]          # 诊断用到的测点（量程自检时影响结论）


# --------------------------------------------------------------------------- 无流量管路
def _idle(ctx: Context, loop: Dict, meters: List[Dict], mass_cfg: Optional[Dict]) -> LoopResult:
    zero = ctx.th["zero"]
    summary = {"name": loop["name"], "active": False, "meters": [], "balance": None, "mass": None,
               "legacy": None, "consensus": None}
    findings = []
    for m in meters:
        mean = ck.mean_of(ctx.seg[m["column"]])
        sev = WARNING if mean is not None and abs(mean) > zero["volume"] else INFO
        summary["meters"].append({**m, "mean": mean, "severity": sev})
        if sev == WARNING:
            findings.append(finding("zero", WARNING, "无流量时读数不为零",
                                    f"{loop['name']}没有流量，但{m['label']}读数均值为 {mean:.2f} L/h",
                                    m["column"], m["label"], m.get("component"), mean, f"≤{zero['volume']} L/h"))
    if mass_cfg:
        col = mass_cfg["column"]
        mean = ck.mean_of(ctx.seg[col])
        sev = WARNING if mean is not None and abs(mean) > zero["mass"] else INFO
        summary["mass"] = {"column": col, "label": mass_cfg["label"], "mean": mean, "severity": sev}
        findings.append(finding(
            "zero", sev, "质量流量计零点偏移" if sev == WARNING else "质量流量计零点",
            f"{loop['name']}没有流量，{mass_cfg['label']}读数均值为 {mean:.2f} kg/h（零点）",
            col, mass_cfg["label"], None, mean, f"≤{zero['mass']} kg/h"))
    return LoopResult(summary, findings, set())


# --------------------------------------------------------------------------- 传感器自检
def _self_check(ctx: Context, meters: List[Dict], level: float) -> Tuple[List[Dict], Dict[str, float], List[Dict]]:
    """返回 (各表条目, 有效表的均值, 发现)。"""
    th, seg, seg_t, segment = ctx.th, ctx.seg, ctx.seg_t, ctx.segment
    frozen_limit = max(th.get("frozen", {}).get("min_s", 2.0), th.get("frozen", {}).get("min_ratio", 0.2) * segment.duration)
    entries, means, findings = [], {}, []
    for m in meters:
        col = m["column"]
        entry = {**m, "mean": ck.mean_of(seg[col]), "severity": INFO}
        entries.append(entry)
        if entry["mean"] is None:
            entry["severity"] = ABNORMAL
            findings.append(finding("sensor", ABNORMAL, "流量计无有效数据", f"{m['label']}在稳定段内没有有效读数",
                                    col, m["label"], m.get("component")))
            continue
        if ck.is_stuck(seg[col]):
            entry.update(severity=ABNORMAL, stuck=True)
            findings.append(finding("sensor", ABNORMAL, "流量计读数卡死",
                                    f"{m['label']}在 {segment.duration:.0f} 秒内读数始终为 {entry['mean']:.3f}",
                                    col, m["label"], m.get("component"), entry["mean"]))
            continue
        zero = ck.zero_fraction(seg[col], level)
        if zero >= th.get("dropout_ratio", 0.1):
            entry.update(severity=ABNORMAL, dropout=True)
            findings.append(finding("dropout", ABNORMAL, "流量计读数掉零",
                                    f"管路流量约 {level:.0f} L/h，{m['label']}有 {zero * 100:.0f}% 的时间读数接近 0，"
                                    "可能是信号线断开、接插件脱落或叶轮卡死不转",
                                    col, m["label"], m.get("component"), zero * 100))
            continue
        frozen = ck.longest_constant_run(seg[col], seg_t)
        if frozen >= frozen_limit:
            entry.update(severity=ABNORMAL, stuck=True)
            findings.append(finding("frozen", ABNORMAL, "流量计读数冻结",
                                    f"{m['label']}有 {frozen:.1f} 秒读数完全不变（正常时传感器约每 0.1 秒更新一次，"
                                    "最长不变约 0.2 秒），可能是叶轮卡滞或变送器死机",
                                    col, m["label"], m.get("component"), frozen, f"<{frozen_limit:.1f} 秒"))
            continue
        means[col] = entry["mean"]
    return entries, means, findings


def _signal_quality(ctx: Context, entries: List[Dict], valid: Dict[str, float]) -> List[Dict]:
    """噪声与毛刺（不影响均值比较）。"""
    th, findings = ctx.th, []
    for entry in entries:
        col = entry["column"]
        if col not in valid:
            continue
        cv = ck.window_cv(ctx.seg[col], ctx.seg_t, ctx.cfg["steady"]["window_s"])
        entry["cv"] = cv
        base_cv = ctx.baseline_meters.get(col, {}).get("cv")
        limit = max(th["noise"]["floor"], th["noise"]["ratio"] * base_cv) if base_cv else th["noise"]["floor"]
        if cv is not None and cv > limit:
            entry["noisy"] = True
            findings.append(finding("noise", WARNING, "流量计读数波动过大",
                                    f"{entry['label']}短时波动 {cv * 100:.2f}%，超过 {limit * 100:.2f}%",
                                    col, entry["label"], entry.get("component"), cv * 100, f"≤{limit * 100:.2f}%"))
        ratio = ck.spike_ratio(ctx.seg[col], th["spike"]["z"])
        if ratio > th["spike"]["ratio"]:
            entry["noisy"] = True
            findings.append(finding("spike", WARNING, "流量计读数有毛刺",
                                    f"{entry['label']}有 {ratio * 100:.2f}% 的读数明显偏离（突跳）",
                                    col, entry["label"], entry.get("component"), ratio * 100,
                                    f"≤{th['spike']['ratio'] * 100:.1f}%"))
    return findings


# --------------------------------------------------------------------------- 质量流量计
def _mass_reading(ctx: Context, mass_cfg: Dict, temp_col: Optional[str], temperature: Optional[float]):
    """返回 (质量流量计摘要, 换算后的体积流量序列（不可用时为 None）, 发现)。"""
    col, seg = mass_cfg["column"], ctx.seg
    mean = ck.mean_of(seg[col])
    # 密度按质量流量计所在位置的油温修正（回油比供油高 1–4 ℃）；该测点不可用时退回管路油温
    mass_temp_col = mass_cfg.get("temperature_column")
    mass_temp = valid_temperature(seg, mass_temp_col, ctx.cfg)
    if mass_temp is None:
        mass_temp, mass_temp_col = temperature, temp_col
    rho, source = density(ctx.cfg, ctx.baseline, mass_temp, ctx.fuel_density_20)
    summary = {"column": col, "label": mass_cfg["label"], "mean": mean, "density": rho, "density_source": source,
               "temperature": mass_temp, "temperature_column": mass_temp_col, "severity": INFO}
    frozen_limit = max(ctx.th.get("frozen", {}).get("min_s", 2.0),
                       ctx.th.get("frozen", {}).get("min_ratio", 0.2) * ctx.segment.duration)
    if mean is None or ck.is_stuck(seg[col]) or ck.longest_constant_run(seg[col], ctx.seg_t) >= frozen_limit:
        summary["severity"] = ABNORMAL
        return summary, None, [finding("sensor", ABNORMAL, "质量流量计无有效读数或卡死",
                                       f"{mass_cfg['label']}在稳定段内没有变化的有效读数", col, mass_cfg["label"])]
    if rho is None:
        return summary, None, [finding("mass_volume", NOTICE, "无法做质量-体积校核", source, col, mass_cfg["label"])]
    summary["q_mass"] = mean / rho * 1000.0
    return summary, pd.to_numeric(seg[col], errors="coerce") / rho * 1000.0, []


# --------------------------------------------------------------------------- 协调与隔离
def _channels(ctx: Context, entries: List[Dict], valid: Dict[str, float], mass_cfg: Optional[Dict],
              loop_name: str, level: float, temperature: Optional[float]) -> List[reconcile.Channel]:
    ranges = (ctx.baseline or {}).get("ranges")
    out = []
    for e in entries:
        if e["column"] in valid and e.get("group") in reconcile.SIDE:
            tol = tolerances.meter(ctx.cfg, ctx.baseline_meters.get(e["column"]), level, temperature, ranges)
            out.append(reconcile.Channel(e["column"], e["label"], e.get("component"), reconcile.SIDE[e["group"]],
                                         iso.VOLUME, tol))
    if mass_cfg:
        side = reconcile.SIDE.get(mass_cfg.get("group", ""), iso.RETURN)
        out.append(reconcile.Channel(mass_cfg["column"], mass_cfg["label"], None, side, iso.MASS,
                                     tolerances.mass_volume(ctx.cfg, ctx.baseline, loop_name)))
    return out


def _detect_change(ctx: Context, channels: List[reconcile.Channel], series: Dict[str, pd.Series]):
    """返回 (变化, 代表当前状态的各表均值)；没有变化时为整个稳定段的均值。"""
    frame = pd.DataFrame({k: v.to_numpy(dtype=float) for k, v in series.items()})
    full = {k: float(frame[k].mean()) for k in frame.columns}
    window = ctx.cfg["steady"]["window_s"]
    wm = ck.window_means(frame, ctx.seg_t, window).dropna()
    if wm.empty:
        return None, full
    rel = reconcile.relative_series(channels, {k: wm[k].to_numpy(dtype=float) for k in wm.columns})
    change = changepoint.detect(wm.index.to_numpy(dtype=float) * window, rel,
                                {ch.key: ch.tol.warn for ch in channels},
                                changepoint.Options.from_config(ctx.cfg.get("changepoint")))
    if change is None:
        return None, full
    return change, {k: float(wm[k].iloc[change.current_from:].mean()) for k in wm.columns}


def _reconcile(ctx: Context, loop: Dict, channels: List[reconcile.Channel], series: Dict[str, pd.Series],
               entries: List[Dict], valid: Dict[str, float]):
    """变点检测 → 故障隔离 → 发现。返回 (当前状态的各表读数, 有故障的表, 发现, 隔离摘要)。"""
    change, readings = _detect_change(ctx, channels, series)
    obs, ref = reconcile.observations(channels, readings, ctx.anchor)
    opts = reconcile.Options.from_config(ctx.cfg)
    result = iso.isolate(obs, opts.isolation) if ref else None
    if result is None:
        return readings, {}, [], None
    mass_tol = next((ch.tol for ch in channels if ch.kind == iso.MASS), None)
    outcome = reconcile.explain(result, channels, loop, ref, tolerances.balance(ctx.cfg, ctx.baseline, loop["name"]),
                                mass_tol, opts, change)
    findings = list(outcome.findings)
    if change:
        explained = [k for f in outcome.findings for k in (f.get("fault") or {}).get("meters", [])]
        extra = reconcile.unexplained_change(change, channels, explained)
        if extra:
            findings.append(extra)
    _update_meters(entries, channels, valid, outcome, len(obs) >= 3)
    labels = {ch.key: ch.label for ch in channels}
    summary = {
        "explanation": reconcile.describe_fit(result.best, labels),
        "probability": round(result.best.probability, 3),
        "alternatives": [{"text": reconcile.describe_fit(f, labels), "probability": round(f.probability, 3)}
                         for f in result.alternatives(opts.alternative_probability)],
        "change": {"kind": change.kind, "onset_s": change.onset_s} if change else None,
    }
    return readings, outcome.faulty, findings, summary


# --------------------------------------------------------------------------- 管路摘要
def _usable(channels: List[reconcile.Channel], readings: Dict[str, float], faulty: Dict[str, str],
            side: Optional[str] = None) -> List[float]:
    """没有被判为故障的体积流量计（扣除固有偏差后）的读数。"""
    return [ch.corrected(readings[ch.key]) for ch in channels
            if ch.kind == iso.VOLUME and ch.key in readings and ch.key not in faulty and (side is None or ch.side == side)]


def _balance_summary(ctx: Context, loop: Dict, channels, readings, faulty, findings) -> Optional[Dict]:
    sup = _usable(channels, readings, faulty, iso.SUPPLY)
    ret = _usable(channels, readings, faulty, iso.RETURN)
    usable = sup + ret
    if not sup or not ret:
        return None
    tol = tolerances.balance(ctx.cfg, ctx.baseline, loop["name"])
    raw = (float(np.median(sup)) - float(np.median(ret))) / float(np.median(usable))
    bias = tol.bias   # 有逐表固有偏差时为 0（已逐表扣除）
    related = [f["severity"] for f in findings if f["category"] in ("balance", "aeration")]
    return {"raw": raw, "bias": bias, "corrected": raw - bias, "warn": tol.warn, "alarm": tol.alarm,
            "severity": max(related, key=lambda s: ck.SEVERITY_RANK[s]) if related else INFO}


def _mass_summary(mass: Dict, channel: reconcile.Channel, channels, readings, faulty) -> None:
    """质量流量计与同一侧（如回油）可用的体积流量计比较；该侧没有可用的表时用全部可用的表。"""
    side = _usable(channels, readings, faulty, channel.side) or _usable(channels, readings, faulty)
    if not side or channel.key not in readings:
        return
    ref = float(np.median(side))
    dev = (channel.corrected(readings[channel.key]) - ref) / ref
    mass.update({"reference_flow": ref, "deviation": dev, "warn": channel.tol.warn, "alarm": channel.tol.alarm,
                 "severity": faulty.get(channel.key, INFO)})


def _legacy(ctx: Context, mass: Dict) -> Optional[Dict]:
    """原经验公式（质量流量 → 涡轮转速 → 理论流量），只作参考。"""
    if not ctx.cfg.get("legacy_model", {}).get("enabled") or mass.get("mean") is None \
            or not mass.get("density") or not mass.get("reference_flow"):
        return None
    speed = legacy.simulated_speed(mass["mean"] / 3600.0, mass["density"])
    q_theory = legacy.theoretical_flow(speed)
    return {"speed": speed, "q_theory": q_theory, "valid": speed > 0,
            "deviation": (q_theory - mass["reference_flow"]) / mass["reference_flow"]}


def _range_notice(ctx: Context, loop: Dict, level: Optional[float], temperature: Optional[float]) -> List[Dict]:
    ranges = (ctx.baseline or {}).get("ranges")
    if not ranges or level is None:
        return []
    outside = []
    if not ranges["flow"][0] * 0.9 <= level <= ranges["flow"][1] * 1.1:
        outside.append(f"流量 {level:.0f} L/h（基准 {ranges['flow'][0]:.0f}–{ranges['flow'][1]:.0f}）")
    if temperature is not None and not ranges["temperature"][0] - 3 <= temperature <= ranges["temperature"][1] + 3:
        outside.append(f"油温 {temperature:.1f}℃（基准 {ranges['temperature'][0]:.1f}–{ranges['temperature'][1]:.1f}）")
    if not outside:
        return []
    return [finding("baseline", NOTICE, "工况超出健康基准范围",
                    "、".join(outside) + "，固有偏差按最接近的工况估算，结论可信度下降，"
                    "建议补充该工况的健康数据后重建基准", loop["name"], loop["name"])]


def _two_meters(ctx: Context, loop: Dict, valid: Dict[str, float]) -> List[Dict]:
    """只有两只有效流量计、又没有别的参照时，只能看出两者不一致，判断不了是哪一只。"""
    (c1, v1), (c2, v2) = valid.items()
    diff = abs(v1 - v2) / max(abs((v1 + v2) / 2), 1e-9)
    if diff <= ctx.th["redundancy"]["alarm"]:
        return []
    return [finding("redundancy", WARNING, "两只流量计不一致",
                    f"{loop['name']}只有两只有效流量计，相差 {diff * 100:.2f}%，无法判断是哪一只的问题",
                    c1, loop["name"], None, diff * 100)]


# --------------------------------------------------------------------------- 入口
def analyze_loop(ctx: Context, loop: Dict, active: bool, flow_level: float) -> LoopResult:
    """flow_level：该管路在稳定段内的流量水平（各表中位数的均值），用于掉零判断。"""
    meters = [m for m in loop["meters"] if m["column"] in ctx.seg.columns]
    mass_cfg = loop.get("mass_meter")
    mass_cfg = mass_cfg if mass_cfg and mass_cfg["column"] in ctx.seg.columns else None
    if not active:
        return _idle(ctx, loop, meters, mass_cfg)

    temp_col = loop.get("temperature_column")
    columns = {m["column"] for m in meters} | {c for c in (temp_col, (mass_cfg or {}).get("temperature_column")) if c}
    entries, valid, findings = _self_check(ctx, meters, flow_level)
    findings += _signal_quality(ctx, entries, valid)
    temperature = valid_temperature(ctx.seg, temp_col, ctx.cfg)  # 超量程时为 None，量程自检会报出来
    level = float(np.median(list(valid.values()))) if valid else None
    summary = {"name": loop["name"], "active": True, "meters": entries, "balance": None, "mass": None,
               "legacy": None, "consensus": None, "temperature": temperature}

    series = {c: pd.to_numeric(ctx.seg[c], errors="coerce") for c in valid}
    mass = None
    if mass_cfg:
        columns.add(mass_cfg["column"])
        mass, mass_series, extra = _mass_reading(ctx, mass_cfg, temp_col, temperature)
        findings += extra
        summary["mass"] = mass
        if mass_series is not None:
            series[mass_cfg["column"]] = mass_series
    channels = _channels(ctx, entries, valid, mass_cfg if mass_cfg and mass_cfg["column"] in series else None,
                         loop["name"], level, temperature) if level else []

    readings, faulty = {}, {}
    if len(channels) >= 2:
        readings, faulty, extra, summary["isolation"] = _reconcile(ctx, loop, channels, series, entries, valid)
        findings += extra

    if len(valid) == 2 and not any(f.get("fault") for f in findings):
        findings += _two_meters(ctx, loop, valid)
    usable = _usable(channels, readings, faulty)
    summary["consensus"] = float(np.median(usable)) if usable else level
    summary["balance"] = _balance_summary(ctx, loop, channels, readings, faulty, findings) if readings else None
    mass_channel = next((ch for ch in channels if ch.kind == iso.MASS), None)
    if mass is not None and mass_channel is not None:
        _mass_summary(mass, mass_channel, channels, readings, faulty)
        summary["legacy"] = _legacy(ctx, mass)
    summary["checked"] = (any("corrected" in m for m in entries) or len(valid) == 2
                          or "deviation" in (mass or {}))
    findings += _range_notice(ctx, loop, level, temperature)
    return LoopResult(summary, findings, columns)


def _update_meters(entries: List[Dict], channels: List[reconcile.Channel], valid: Dict[str, float],
                   outcome: reconcile.Outcome, redundant: bool) -> None:
    """各表条目：raw 偏差（留一法，建健康基准用）、固有偏差、协调后的偏差、阈值与严重程度。"""
    if not redundant:
        return
    tol = {ch.key: ch.tol for ch in channels}
    for e in entries:
        col = e["column"]
        if col not in valid or col not in tol or col not in outcome.corrected:
            continue
        e.update({"deviation": ck.loo_deviation(valid, col) if len(valid) >= 3 else None, "bias": tol[col].bias,
                  "corrected": outcome.corrected[col], "warn": tol[col].warn, "alarm": tol[col].alarm,
                  "severity": outcome.faulty.get(col, INFO)})
        if e["deviation"] is None:
            del e["deviation"]
