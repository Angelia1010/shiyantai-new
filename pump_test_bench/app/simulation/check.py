"""诊断时的模型残差检查：实测 与 模型在同一工况下的预期值 比较。每个模型按自己的规则检查。

规则：
- 单测点（single）：某个测点偏离预期。single = decisive 时参与结论，notice 时只作补充证据
  （如整体模型里的单只流量计，由互校判断更准）；
- 整体偏移（group_shift）：一组测点彼此一致、整体偏离预期，含义（meaning）三种：
  pump      — 实际流量变了（被试泵出力下降等），再看与流量相关的压力是否同步变化来确认；
  reference — 模型的参考量偏了（如涡轮流量计模型的质量流量计、燃油密度）；
  input     — 模型的输入测点偏了（如温控模型的汇流温度传感器）。
"""
from typing import Dict, List, Optional, Set

import numpy as np
import pandas as pd

from pump_test_bench.app.diagnosis.checks import ABNORMAL, INFO, NOTICE, WARNING, finding, grade
from pump_test_bench.app.simulation.calibration import bias_at, residual
from pump_test_bench.app.simulation.condition import DensityFn, condition_of, measured_means
from pump_test_bench.app.simulation.config import residual_mode
from pump_test_bench.app.simulation.table import predict, sensitivity

GROUP_CATEGORY = {"pump": "model_system", "reference": "model_reference", "input": "model_input"}


def thresholds(th: Dict, kind: str, std: Optional[float], sigma: Optional[Dict] = None):
    sw = (sigma or {}).get("sigma_warn") or th.get("sigma_warn", 3)
    sa = (sigma or {}).get("sigma_alarm") or th.get("sigma_alarm", 5)
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


def model_check(seg: pd.DataFrame, mcfg: Dict, table: Dict, flagged: Optional[Set[str]] = None,
                density_fn: Optional[DensityFn] = None, sigma: Optional[Dict] = None,
                column_component: Optional[Dict[str, str]] = None) -> Dict:
    """flagged：互校已判定有问题的列（坏表不参与整体偏移判断）。sigma：诊断方案中的阈值倍数。"""
    flagged = flagged or set()
    column_component = column_component or {}
    th = mcfg.get("thresholds", {})
    cond, notes = condition_of(seg, mcfg, density_fn)
    model_label = (table.get("model") or {}).get("label", "")
    base = {"id": mcfg["id"], "name": mcfg["name"], "model": model_label, "table_created": table.get("created"),
            "condition": cond, "notes": notes}
    if len(cond) < len(table["inputs"]):
        return {**base, "available": False, "rows": [], "findings": []}
    pred, outside = predict(table, cond)
    calib = (table.get("calibration") or {}).get("columns", {})
    measured = measured_means(seg, mcfg)
    unit_of = {s["name"]: s.get("unit", "") for s in mcfg["inputs"]}
    cond_text = "、".join(f"{k} {_num(v)} {unit_of.get(k, '')}".rstrip() for k, v in cond.items())

    rows: List[Dict] = []
    for o in mcfg["outputs"]:
        p = pred.get(o["name"])
        mode = residual_mode(o)
        if p is None or (mode == "relative" and abs(p) < 1e-9):
            continue
        for col in o["columns"]:
            if col not in measured:
                continue
            c = calib.get(col, {})
            b = bias_at(c, mcfg, cond) if c else 0.0
            warn, alarm = thresholds(th, o["kind"], c.get("std"), sigma)
            r = residual(measured[col], p, mode) - b
            expected = p + b if mode == "absolute" else p * (1 + b)
            rows.append({"column": col, "output": o["name"], "kind": o["kind"], "unit": o.get("unit", ""),
                         "mode": mode, "measured": measured[col], "expected": expected, "residual": r,
                         "warn": warn, "alarm": alarm, "severity": grade(r, warn, alarm),
                         "single": o.get("single", "decisive"), "flow_dependent": bool(o.get("flow_dependent")),
                         "component": (o.get("component_by_column") or {}).get(col) or column_component.get(col)
                         or o.get("component"),
                         "excluded": col in flagged})

    findings: List[Dict] = []
    if outside:
        findings.append(finding("model_range", NOTICE, "工况超出仿真基准表范围",
                                f"{mcfg['name']}：" + "、".join(outside) + "，按表的边界估算，仅供参考",
                                mcfg["id"], mcfg["name"]))

    # 1) 整体偏移
    group = None
    rule = (mcfg.get("rules") or {}).get("group_shift")
    if rule:
        names = rule.get("outputs") or [rule["output"]]
        members = [r for r in rows if r["output"] in names and not r["excluded"]]
        if members:
            mode = members[0]["mode"]
            rq = float(np.median([r["residual"] for r in members]))
            warn_q = float(np.median([r["warn"] for r in members]))
            alarm_q = float(np.median([r["alarm"] for r in members]))
            agree = [r for r in members if np.sign(r["residual"]) == np.sign(rq) and abs(r["residual"]) > warn_q / 2]
            if abs(rq) > warn_q and len(agree) >= min(rule.get("min_columns", 3), len(members)):
                group = _group_finding(rule, mcfg, table, cond, cond_text, pred, rows, members, rq, warn_q, alarm_q,
                                       mode, findings)
                for r in members:
                    r["in_group"] = True

    # 2) 单个测点
    for r in rows:
        if r["severity"] == INFO or r["excluded"] or r.get("in_group"):
            continue
        text = (f"{r['column']} 实测 {_fmt(r['measured'], r['unit'])}，{mcfg['name']}预期 {_fmt(r['expected'], r['unit'])}，"
                f"偏差 {fmt_residual(r['residual'], r['mode'], r['unit'])}")
        limit = f"预警 {fmt_limit(r['warn'], r['mode'], r['unit'])}，异常 {fmt_limit(r['alarm'], r['mode'], r['unit'])}"
        value = r["residual"] if r["mode"] == "absolute" else r["residual"] * 100
        if r["single"] == "notice":
            f = finding("model", NOTICE, "测点偏离模型预期", text, r["column"], r["column"], r["component"], value, limit)
        else:
            f = finding("model_single", r["severity"], "测点偏离模型预期", text, r["column"], r["column"],
                        r["component"], value, limit)
        f["kind"] = r["kind"]
        findings.append(f)

    for f in findings:
        f["model"], f["model_name"] = mcfg["id"], mcfg["name"]
    return {**base, "available": True, "outside": outside, "expected": pred, "rows": rows, "group": group,
            "findings": findings}


def _group_finding(rule, mcfg, table, cond, cond_text, pred, rows, members, rq, warn_q, alarm_q, mode, findings):
    meaning = rule.get("meaning", "pump")
    sev = grade(rq, warn_q, alarm_q)
    shift = fmt_residual(rq, mode, members[0]["unit"])
    group = {"meaning": meaning, "residual": rq, "mode": mode, "warn": warn_q, "alarm": alarm_q, "severity": sev,
             "columns": [r["column"] for r in members]}
    direction = "低" if rq < 0 else "高"
    if meaning == "pump":
        out_name = rule["output"]
        follow, checked = 0, 0
        for r in rows:
            if not r["flow_dependent"]:
                continue
            e = sensitivity(table, cond, r["output"], out_name, mcfg["inputs"][0]["name"])
            if e is None:
                continue
            expect = e * rq
            checked += 1
            if np.sign(r["residual"]) == np.sign(expect) and \
                    abs(r["residual"]) >= mcfg.get("thresholds", {}).get("pressure_consistency", 0.5) * abs(expect):
                follow += 1
            if abs(r["residual"] - expect) <= r["warn"]:
                r["severity"] = INFO  # 能由流量变化解释的压力偏离，不再单独报
        group.update({"pressures_follow": checked > 0 and follow * 2 > checked, "pressures_checked": checked,
                      "expected": pred.get(out_name)})
        detail = (f"在 {cond_text} 工况下，{mcfg['name']}预期{out_name} {pred[out_name]:.1f} L/h；{len(members)} 只流量计"
                  f"彼此一致，整体{direction} {abs(rq) * 100:.2f}%（已扣除各表固有偏差）。")
        if checked:
            detail += (f"与流量相关的 {checked} 个压力测点中有 {follow} 个按模型关系同步变化，"
                       + ("说明实际流量确实变了" if group["pressures_follow"] else "压力基本没有随之变化，更像是测量整体偏了"))
        title, target = "系统流量偏离模型预期", out_name
    elif meaning == "reference":
        detail = (f"在 {cond_text} 下，{len(members)} 只流量计相对{mcfg['name']}一致偏{direction} {shift}，"
                  "各表彼此一致，说明是模型的参考量（质量流量计读数或燃油密度）偏了，而不是这些流量计")
        title, target = "流量计模型的参考量偏差", rule["output"]
    else:
        inp = rule.get("input", mcfg["inputs"][0]["name"])
        spec = next((i for i in mcfg["inputs"] if i["name"] == inp), {})
        detail = (f"{len(members)} 个测点相对{mcfg['name']}一致偏{direction} {shift}，彼此一致，"
                  f"更可能是模型输入“{inp}”（{spec.get('column', '')}）的测点偏了")
        title, target = "模型输入测点偏差", spec.get("column", inp)
    value = rq if mode == "absolute" else rq * 100
    findings.append(finding(GROUP_CATEGORY[meaning], sev, title, detail, target, target, rule.get("component"),
                            value, f"预警 {fmt_limit(warn_q, mode, members[0]['unit'])}，"
                                   f"异常 {fmt_limit(alarm_q, mode, members[0]['unit'])}"))
    return group


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
