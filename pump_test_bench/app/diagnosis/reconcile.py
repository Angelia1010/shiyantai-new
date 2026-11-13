"""流量协调：把一路油上各流量计的读数交给故障隔离，再把隔离结果翻译成诊断的发现与管路摘要。

- 读数 → 观测量：扣除各表在当前工况下的固有偏差，换算成相对参考水平的相对读数；
  质量流量计按密度换算成体积流量；仿真模型的预期流量（锚点）作为不依赖流量计的参照；
- 隔离结果 → 发现：最可能的解释中每个超过阈值的原因成为一条发现（类别沿用 redundancy / balance /
  mass_volume / aeration，共因为 common_mode），附带该解释的概率与其他可能的解释；
- 管路摘要：各表相对协调后真实流量的偏差、供回油平衡、质量-体积偏差（前端、诊断历史、健康基准都用）。
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from pump_test_bench.app.diagnosis import isolation as iso
from pump_test_bench.app.diagnosis.changepoint import RAMP, Change
from pump_test_bench.app.diagnosis.checks import INFO, SEVERITY_RANK, WARNING, finding, grade
from pump_test_bench.app.diagnosis.tolerances import Tolerance

SIDE = {"供油": iso.SUPPLY, "回油": iso.RETURN}
SIDE_TEXT = {iso.SUPPLY: "供油", iso.RETURN: "回油"}

# 原因 → 发现的类别
CATEGORY = {iso.LEAK: "balance", iso.AERATION: "aeration", iso.SUPPLY_GROUP: "common_mode",
            iso.RETURN_GROUP: "common_mode", iso.VOLUME_GROUP: "common_mode"}


@dataclass(frozen=True)
class Channel:
    """参与协调的一只流量计（质量流量计已换算成体积流量）。"""
    key: str
    label: str
    component: Optional[str]
    side: str                  # iso.SUPPLY / iso.RETURN
    kind: str                  # iso.VOLUME / iso.MASS
    tol: Tolerance

    def corrected(self, reading: float) -> float:
        return reading / (1 + self.tol.bias)


@dataclass(frozen=True)
class Anchor:
    """仿真模型给出的真实流量参照：各供油侧流量计的预期读数（L/h）与模型离散。"""
    key: str
    label: str
    expected: Dict[str, float]
    sigma: float


@dataclass(frozen=True)
class Options:
    isolation: iso.Options
    alternative_probability: float = 0.05

    @staticmethod
    def from_config(cfg: Dict) -> "Options":
        o = cfg.get("isolation", {})
        return Options(iso.Options(o.get("cause_cost", 9.0), o.get("group_cost", 3.0), o.get("max_causes", 2)),
                       o.get("alternative_probability", 0.05))


# --------------------------------------------------------------------------- 读数 → 观测量
def reference_level(channels: Sequence[Channel], readings: Dict[str, float]) -> Optional[float]:
    """参考水平：各体积流量计（扣除固有偏差）的中位数。"""
    vols = [ch.corrected(readings[ch.key]) for ch in channels if ch.kind == iso.VOLUME and ch.key in readings]
    level = float(np.median(vols)) if vols else None
    return level if level and level > 0 else None


def anchor_value(anchor: Anchor, channels: Sequence[Channel], level: float) -> Optional[float]:
    """锚点的相对读数：模型对各供油侧流量计的预期读数扣除固有偏差后的中位数。"""
    values = [ch.corrected(anchor.expected[ch.key]) for ch in channels
              if ch.side == iso.SUPPLY and ch.kind == iso.VOLUME and ch.key in anchor.expected]
    return float(np.median(values)) / level - 1 if values else None


def observations(channels: Sequence[Channel], readings: Dict[str, float],
                 anchor: Optional[Anchor] = None) -> Tuple[List[iso.Observation], Optional[float]]:
    """返回 (观测量, 参考水平 L/h)。"""
    level = reference_level(channels, readings)
    if level is None:
        return [], None
    obs = [iso.Observation(ch.key, ch.side, ch.kind, ch.corrected(readings[ch.key]) / level - 1, ch.tol.sigma)
           for ch in channels if ch.key in readings]
    if anchor:
        value = anchor_value(anchor, channels, level)
        if value is not None:
            obs.append(iso.Observation(anchor.key, iso.SUPPLY, iso.ANCHOR, value, anchor.sigma))
    return obs, level


def relative_series(channels: Sequence[Channel], windows: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """按时间窗的相对读数：每个时间窗都相对该窗内的共识值，实际流量的波动相互抵消。"""
    vols = [ch for ch in channels if ch.kind == iso.VOLUME and ch.key in windows]
    if not vols:
        return {}
    level = np.median(np.vstack([ch.corrected(windows[ch.key]) for ch in vols]), axis=0)
    level = np.where(level > 0, level, np.nan)
    return {ch.key: ch.corrected(windows[ch.key]) / level - 1 for ch in channels if ch.key in windows}


# --------------------------------------------------------------------------- 隔离结果 → 文字
def _pct(v: float) -> str:
    return f"{abs(v) * 100:.2f}%"


def describe_cause(cause: iso.Cause, fit: iso.Fit, labels: Dict[str, str]) -> str:
    """一个原因的简短描述，如“回油流量1-2 偏低 3.00%”。"""
    v = fit.magnitude(cause)
    hl = "偏高" if v > 0 else "偏低"
    if cause.kind == iso.METER:
        key = cause.keys[0]
        if key not in labels:  # 锚点：模型预期高于各表一致的读数，即实际流量偏低
            return f"实际流量比模型预期{'低' if v > 0 else '高'} {_pct(v)}"
        return f"{labels[key]} {hl} {_pct(v)}"
    if cause.kind == iso.LEAK:
        return f"供回油之间泄漏 {_pct(v)}"
    if cause.kind == iso.AERATION:
        return f"回油夹气（回油流量计多计 {_pct(v)}）"
    side = {iso.SUPPLY_GROUP: "供油侧流量计", iso.RETURN_GROUP: "回油侧流量计", iso.VOLUME_GROUP: "全部体积流量计"}
    return f"{side[cause.kind]}整体{hl} {_pct(v)}"


def describe_fit(fit: iso.Fit, labels: Dict[str, str]) -> str:
    return "、".join(describe_cause(c, fit, labels) for c in fit.causes) or "各流量计都正常"


# --------------------------------------------------------------------------- 隔离结果 → 发现与摘要
@dataclass
class Outcome:
    findings: List[Dict]
    faulty: Dict[str, str]          # 有故障的流量计 → 严重程度
    corrected: Dict[str, float]     # 各流量计相对协调后真实流量的偏差


def _cause_tolerance(cause: iso.Cause, by_key: Dict[str, Channel], balance: Tolerance,
                     mass: Optional[Tolerance]) -> Optional[Tolerance]:
    if cause.kind == iso.METER:
        ch = by_key.get(cause.keys[0])
        return ch.tol if ch else None             # 锚点偏离由仿真模型的检查报出
    if cause.kind == iso.VOLUME_GROUP:
        return mass or balance                    # 全部体积表一致偏移只能靠质量流量计/模型看出
    return balance


def _target(cause: iso.Cause, by_key: Dict[str, Channel], loop: Dict) -> Tuple[str, str, Optional[str]]:
    """发现的 (target, label, component)。"""
    if cause.kind == iso.METER:
        ch = by_key[cause.keys[0]]
        return ch.key, ch.label, ch.component
    component = {iso.SUPPLY_GROUP: "供油管路", iso.VOLUME_GROUP: None}.get(cause.kind, "回油管路")
    if cause.kind == iso.RETURN_GROUP:
        component = next((by_key[k].component for k in cause.keys if by_key[k].component), component)
    return loop["name"], loop["name"], component


def _detail(cause: iso.Cause, fit: iso.Fit, by_key: Dict[str, Channel], level: float) -> str:
    v = fit.magnitude(cause)
    if cause.kind == iso.METER:
        ch = by_key[cause.keys[0]]
        what = "质量流量换算成体积后" if ch.kind == iso.MASS else "读数"
        text = (f"{ch.label}{what}比协调后的实际流量（{level * (1 + fit.true_level(ch.side)):.1f} L/h）"
                f"{'高' if v > 0 else '低'} {_pct(v)}")
        return text + (f"（已扣除该表固有偏差 {ch.tol.bias * 100:+.2f}%）" if ch.tol.bias else "")
    if cause.kind == iso.LEAK:
        return (f"供油侧各流量计彼此一致、回油侧各流量计（含质量流量计）彼此一致，回油整体比供油少 {_pct(v)}，"
                "可能存在泄漏或分流")
    if cause.kind == iso.AERATION:
        mass = fit.params[cause.id][1]
        text = f"回油流量计比供油多 {_pct(v)}，泄漏不可能造成这种结果；涡轮流量计会把气泡体积也计入"
        return text + (f"，同时质量流量计偏低 {_pct(mass)}（两相流下科氏表少计）" if mass < 0 else "")
    names = "、".join(by_key[k].label for k in cause.keys if k in by_key)
    return f"{names} 彼此一致，但整体比其余流量计{'高' if v > 0 else '低'} {_pct(v)}"


def _change_finding(fault: Dict, cause: iso.Cause, change: Change) -> Optional[Dict]:
    moved = {k: v for k, v in change.shifts.items() if k in cause.keys}
    if not moved:
        return None
    key = max(moved, key=lambda k: abs(moved[k]))
    v = moved[key]
    if change.kind == RAMP:
        title, text = "偏差在测试中持续变化", f"从第 {change.onset_s:.0f} 秒起逐渐变化，到测试结束变化了 {v * 100:+.2f}%，故障正在发展"
    else:
        title, text = "偏差在测试中突然变化", f"在第 {change.onset_s:.0f} 秒突然变化 {v * 100:+.2f}%，结论按变化之后的数据给出"
    f = finding("trend", WARNING, title,
                f"{fault['label']}{text}", fault["target"], fault["label"], fault["component"], v * 100)
    f["change"] = {"kind": change.kind, "onset_s": change.onset_s}
    return f


def explain(result: iso.Isolation, channels: Sequence[Channel], loop: Dict, level: float, balance: Tolerance,
            mass: Optional[Tolerance], opts: Options, change: Optional[Change] = None) -> Outcome:
    """把最可能的解释翻译成发现；未超过预警阈值的原因不报。"""
    by_key = {ch.key: ch for ch in channels}
    labels = {ch.key: ch.label for ch in channels}
    fit = result.best
    alternatives = [{"text": describe_fit(f, labels), "probability": round(f.probability, 3)}
                    for f in result.alternatives(opts.alternative_probability)]
    findings: List[Dict] = []
    faulty: Dict[str, str] = {}
    for cause in fit.causes:
        tol = _cause_tolerance(cause, by_key, balance, mass)
        if tol is None:
            continue
        v = fit.magnitude(cause)
        sev = grade(v, tol.warn, tol.alarm)
        if sev == INFO:
            continue
        target, label, component = _target(cause, by_key, loop)
        ch = by_key.get(cause.keys[0])
        category = CATEGORY.get(cause.kind) or ("mass_volume" if ch and ch.kind == iso.MASS else "redundancy")
        title = {"redundancy": "流量计读数偏离", "mass_volume": "质量流量与体积流量不一致",
                 "balance": "供回油流量不平衡", "aeration": "供回油流量不平衡",
                 "common_mode": "多只流量计同时偏离"}[category]
        f = finding(category, sev, title, _detail(cause, fit, by_key, level), target, label, component, v * 100,
                    f"预警 ±{tol.warn * 100:.1f}%，异常 ±{tol.alarm * 100:.1f}%")
        f["fault"] = {"kind": cause.kind, "side": SIDE_TEXT.get(by_key[cause.keys[0]].side) if ch else None,
                      "meters": [k for k in cause.keys if k in by_key], "summary": describe_fit(fit, labels),
                      "probability": round(fit.probability, 3), "alternatives": alternatives}
        findings.append(f)
        if change:
            extra = _change_finding(f, cause, change)
            if extra:
                f["fault"]["change"] = extra["change"]
                findings.append(extra)
        if cause.kind != iso.LEAK:
            members = cause.keys if cause.kind != iso.AERATION else [k for k in cause.keys if by_key[k].kind == iso.VOLUME]
            for k in members:
                if k in by_key and SEVERITY_RANK[sev] > SEVERITY_RANK[faulty.get(k, INFO)]:
                    faulty[k] = sev
    corrected = {o.key: o.value - fit.true_level(o.side) for o in result.observations if o.key in by_key}
    return Outcome(findings, faulty, corrected)


def unexplained_change(change: Change, channels: Sequence[Channel], explained: Sequence[str]) -> Optional[Dict]:
    """测试中出现了明显变化，但当前状态没有超过阈值的故障（如间歇性故障已恢复）：作为预警报出。"""
    by_key = {ch.key: ch for ch in channels}
    rest = {k: v for k, v in change.shifts.items() if k not in explained and k in by_key}
    big = {k: v for k, v in rest.items() if abs(v) > by_key[k].tol.warn}
    if not big:
        return None
    key = max(big, key=lambda k: abs(big[k]))
    ch, v = by_key[key], big[key]
    how = "逐渐" if change.kind == RAMP else "突然"
    f = finding("trend", WARNING, "偏差在测试中发生变化",
                f"{ch.label}相对其他流量计的偏差在第 {change.onset_s:.0f} 秒起{how}变化了 {v * 100:+.2f}%，"
                "测试末段的偏差未超过阈值，可能是间歇性故障", ch.key, ch.label, ch.component, v * 100,
                f"±{ch.tol.warn * 100:.1f}%")
    f["change"] = {"kind": change.kind, "onset_s": change.onset_s}
    return f
