"""诊断历史：把每次诊断的关键指标串起来看趋势。

单次诊断只能发现“已经超过阈值”的偏差；把历次结果按时间排起来，可以：
1. 提前发现长期漂移：某只表每次只偏一点点，但几十次测试下来一直往一个方向走；
2. 区分质量流量计的零点漂移和标定漂移：零点漂移是固定的 kg/h，小流量时百分比大；
   标定漂移是固定的百分比。需要几次不同流量的测试才能分开，单次诊断做不到。

长期漂移超过 drift 时作为“注意”；如果历次结果还单调地朝一个方向走（秩相关 ≥ consistency），
说明是持续发展的漂移而不是偶然波动，升为“预警”：本次单次检查正常时，结论也改为预警（apply_history）。
"""
from typing import Dict, List, Optional

import numpy as np

from pump_test_bench.app.diagnosis.checks import NOTICE, SEVERITY_TEXT, WARNING, finding

DEFAULTS = {"window_days": 90, "min_tests": 6, "drift": 0.01, "consistency": 0.7,
            "mass_split_min_tests": 3, "mass_split_flow_ratio": 1.5}


def metrics(report: Dict) -> Optional[Dict]:
    """从报告中取出趋势要用的指标；没有有流量的管路时返回 None。"""
    loop = next((lp for lp in report.get("loops") or [] if lp.get("active")), None)
    if not loop:
        return None
    mass = loop.get("mass") or {}
    bal = loop.get("balance") or {}
    return {
        "result": report.get("result"),
        "flow": loop.get("consensus"),
        "temperature": (report.get("condition") or {}).get("温度"),
        "meters": {m["column"]: m["corrected"] for m in loop.get("meters", []) if m.get("corrected") is not None},
        "labels": {m["column"]: m.get("label", m["column"]) for m in loop.get("meters", [])},
        "balance": bal.get("corrected"),
        "mass": {k: mass.get(k) for k in ("column", "label", "deviation", "reference_flow", "mean", "density", "warn")}
        if mass.get("deviation") is not None else None,
    }


def _shift(values: List[float]) -> Optional[float]:
    """最近几次与最早几次的中位数之差（各取最多 5 次，不足 10 次时各取一半）。"""
    n = len(values)
    k = min(5, n // 2)
    if k < 3:
        return None
    return float(np.median(values[-k:]) - np.median(values[:k]))


def _monotonic(values: List[float]) -> float:
    """时间顺序与数值的秩相关（Spearman），+1 表示一直在增大，−1 表示一直在减小。"""
    v = np.asarray(values, dtype=float)
    if len(v) < 3 or np.ptp(v) == 0:
        return 0.0
    ranks = np.argsort(np.argsort(v))
    return float(np.corrcoef(np.arange(len(v)), ranks)[0, 1])


def _drift(category: str, values: List[float], opt: Dict, title: str, detail: str, target: str, label: str,
           threshold: bool = True) -> Optional[Dict]:
    d = _shift(values)
    if d is None or abs(d) <= opt["drift"]:
        return None
    steady = _monotonic(values) * np.sign(d) >= opt["consistency"]
    sev = WARNING if steady else NOTICE
    text = detail.format(dir_high="高" if d > 0 else "低", dir_big="大" if d > 0 else "小", d=abs(d) * 100, n=len(values))
    text += "，且历次结果一直朝同一方向变化，是持续发展的漂移" if steady else ""
    return finding(category, sev, title, text, target, label, None, d * 100,
                   f"±{opt['drift'] * 100:.1f}%" if threshold else None)


def drift_findings(series: List[Dict], cfg: Dict) -> List[Dict]:
    """series：按时间排列的指标（最后一个是本次）。"""
    opt = {**DEFAULTS, **cfg.get("history", {})}
    out: List[Optional[Dict]] = []
    if len(series) < opt["min_tests"]:
        return []
    current = series[-1]
    for col, label in current["labels"].items():
        values = [s["meters"][col] for s in series if col in s["meters"]]
        out.append(_drift("drift", values, opt, "流量计长期漂移",
                          f"{label}最近几次诊断的偏差比最早几次{{dir_high}} {{d:.2f}}%（共 {{n}} 次），"
                          "读数在往一个方向变化，建议安排校准", col, label))
    values = [s["balance"] for s in series if s.get("balance") is not None]
    d = _shift(values)
    hint = "可能有缓慢发展的泄漏" if d is not None and d > 0 else "回油侧读数在逐渐增大"
    out.append(_drift("drift", values, opt, "供回油差长期变化",
                      f"供油与回油之差最近几次比最早几次{{dir_big}} {{d:.2f}}%（共 {{n}} 次），{hint}",
                      "balance", "供回油平衡"))
    if current.get("mass"):
        mass = [s["mass"]["deviation"] for s in series if s.get("mass")]
        out.append(_drift("drift", mass, opt, "质量流量计长期漂移",
                          f"{current['mass']['label']}的质量-体积偏差最近几次比最早几次{{dir_high}} {{d:.2f}}%（共 {{n}} 次）",
                          current["mass"]["column"], current["mass"]["label"], threshold=False))
    return [f for f in out if f]


def mass_split(series: List[Dict], cfg: Dict) -> Optional[Dict]:
    """用最近连续偏差明显的几次诊断，把质量流量计误差拆成零点（kg/h）与标定（%）两部分。

    质量-体积偏差 dev = (qm/ρ − Q)/Q；写成绝对误差 E = dev·Q = s·Q + z，s 为标定偏差，z 为零点（L/h），
    在不同流量 Q 下做直线拟合即可分开。
    """
    opt = {**DEFAULTS, **cfg.get("history", {})}
    recent = []
    for s in reversed(series):
        m = s.get("mass")
        if not m or m.get("deviation") is None or not m.get("reference_flow"):
            break
        if abs(m["deviation"]) <= (m.get("warn") or 0.015) / 2:
            break  # 只用故障出现以后的连续几次
        recent.append(m)
    if len(recent) < opt["mass_split_min_tests"]:
        return None
    q = np.array([m["reference_flow"] for m in recent])
    if q.max() / q.min() < opt["mass_split_flow_ratio"]:
        return None
    err = np.array([m["deviation"] * m["reference_flow"] for m in recent])
    span, zero = np.polyfit(q, err, 1)
    rho = float(np.median([m["density"] for m in recent if m.get("density")] or [790.0]))
    zero_kg = zero * rho / 1000.0
    # 哪一部分解释了大部分误差
    zero_share = abs(zero) / (abs(zero) + abs(span) * float(q.mean()))
    kind = "零点漂移" if zero_share > 0.7 else "标定漂移" if zero_share < 0.3 else "零点与标定都有偏差"
    return {"column": recent[0].get("column"), "tests": len(recent), "flow_range": [float(q.min()), float(q.max())], "zero_kg_h": float(zero_kg),
            "span": float(span), "kind": kind,
            "text": f"根据最近 {len(recent)} 次流量 {q.min():.0f}–{q.max():.0f} L/h 的诊断：零点约 {zero_kg:+.1f} kg/h，"
                    f"标定偏差约 {span * 100:+.2f}%，主要是{kind}"}


def analyze_history(current_report: Dict, past_reports: List[Dict], cfg: Dict) -> Optional[Dict]:
    cur = metrics(current_report)
    if cur is None:
        return None
    series = [m for m in (metrics(r) for r in past_reports) if m] + [cur]
    out = {"tests": len(series), "findings": drift_findings(series, cfg)}
    split = mass_split(series, cfg)
    if split:
        out["mass_split"] = split
    return out


def apply_history(body: Dict, hist: Dict) -> None:
    """把历史分析并入本次报告：持续漂移（预警）在本次单次检查正常时把结论改为预警并作为原因列出；
    质量流量计零点/标定拆分写入对应原因；其余作为补充说明。"""
    body["history"] = hist
    warnings = [f for f in hist["findings"] if f["severity"] == WARNING]
    promoted = bool(warnings) and body.get("result") == "normal"
    if promoted:
        body["result"] = "warning"
        body["causes"] = [{
            "name": f["title"] if f["target"] == "balance" else f"{f['label']} {f['title']}",
            "severity": WARNING, "location": f["label"], "target": f["target"], "component": None,
            "explanation": "单次诊断未超过阈值，但最近多次诊断的偏差持续朝同一方向变化",
            "evidence": [f"{f['title']}：{f['detail']}"], "alternatives": [],
            "advice": "安排校准或检修，并在相同工况下复测确认趋势。"} for f in warnings]
        head = body["causes"][0]["name"]
        body["summary"] = f"{SEVERITY_TEXT[WARNING]}：{head}" + (f" 等 {len(warnings)} 项" if len(warnings) > 1 else "")
        diag = body.setdefault("diagnosis", {})
        diag["fault_name"] = "、".join(c["name"] for c in body["causes"])
        diag["location"] = "、".join(dict.fromkeys(c["location"] for c in body["causes"]))
        diag["analysis"] = "\n".join(f"{i}. [预警] {c['name']}：{c['explanation']}\n   依据：{c['evidence'][0]}"
                                     for i, c in enumerate(body["causes"], 1))
        body["repair_advice"] = "安排校准或检修，并在相同工况下复测确认趋势。"
    notes = [f["detail"] for f in hist["findings"] if not (promoted and f in warnings)]
    split = hist.get("mass_split")
    if split:
        for cause in body.get("causes", []):
            if cause.get("target") == split.get("column") or "零点或标定" in cause.get("name", ""):
                cause["explanation"] += "。" + split["text"]
                cause["name"] = cause["name"].replace("零点或标定漂移", split["kind"])
        body["summary"] = body.get("summary", "").replace("零点或标定漂移", split["kind"])
        diag = body.get("diagnosis") or {}
        if diag.get("fault_name"):
            diag["fault_name"] = diag["fault_name"].replace("零点或标定漂移", split["kind"])
        notes.append(split["text"])
    if notes:
        body["repair_advice"] = (body.get("repair_advice", "") + "\n历史趋势：" + "；".join(notes)).strip()
