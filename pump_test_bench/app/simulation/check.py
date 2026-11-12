"""诊断时的模型残差检查：实测 与 模型在同一工况下的预期值 比较。

模型补的是流量计互校看不到的问题：
- 系统性偏离：各流量计彼此一致，但整体比模型预期低（或高）——被试泵出力下降、转速信号偏差等；
  再看与流量有关的压力是否按模型关系同步变化，区分“实际流量变了”与“测量整体偏了”；
- 没有冗余表的测点（各压力）：只能与模型预期比较。
单只流量计、泄漏等由互校判断，这里只作为补充证据（“注意”级别）。
"""
from typing import Dict, List, Optional, Set

import numpy as np
import pandas as pd

from pump_test_bench.app.diagnosis.checks import ABNORMAL, INFO, NOTICE, WARNING, finding, grade
from pump_test_bench.app.simulation.condition import condition_of, measured_means
from pump_test_bench.app.simulation.table import predict, sensitivity

PUMP_COMPONENT = "被试件1高低压双联泵"


def _thresholds(th: Dict, kind: str, std: Optional[float]):
    fw = th["floor_warn"].get(kind, 0.05)
    fa = th["floor_alarm"].get(kind, 0.08)
    if std:
        return max(fw, th["sigma_warn"] * std), max(fa, th["sigma_alarm"] * std)
    return fw, fa


def _num(v: float) -> str:
    return f"{v:.0f}" if abs(v) >= 100 else f"{v:.1f}" if abs(v) >= 1 else f"{v:.3f}"


def _fmt(value: float, unit: str) -> str:
    return f"{value:.3f} {unit}" if unit == "MPa" else f"{value:.1f} {unit}"


def model_check(seg: pd.DataFrame, sim_cfg: Dict, table: Dict, flagged: Optional[Set[str]] = None) -> Dict:
    """flagged：互校已判定有问题的列（坏表不参与系统性判断）。"""
    flagged = flagged or set()
    th = sim_cfg["thresholds"]
    cond, notes = condition_of(seg, sim_cfg)
    model_label = (table.get("model") or {}).get("label", "")
    base = {"model": model_label, "table_created": table.get("created"), "condition": cond, "notes": notes}
    if len(cond) < len(table["inputs"]):
        return {**base, "available": False, "rows": [], "findings": []}
    pred, outside = predict(table, cond)
    calib = (table.get("calibration") or {}).get("columns", {})
    measured = measured_means(seg, sim_cfg)
    unit_of = {s["name"]: s.get("unit", "") for s in sim_cfg["inputs"]}
    cond_text = "、".join(f"{k} {_num(v)} {unit_of.get(k, '')}".rstrip() for k, v in cond.items())

    rows: List[Dict] = []
    for o in sim_cfg["outputs"]:
        p = pred.get(o["name"])
        if p is None or abs(p) < 1e-9:
            continue
        for col in o["columns"]:
            if col not in measured:
                continue
            c = calib.get(col, {})
            bias = c.get("bias", 0.0)
            warn, alarm = _thresholds(th, o["kind"], c.get("std"))
            r = measured[col] / p - 1 - bias
            rows.append({"column": col, "output": o["name"], "kind": o["kind"], "unit": o.get("unit", ""),
                         "measured": measured[col], "expected": p * (1 + bias), "residual": r,
                         "warn": warn, "alarm": alarm, "severity": grade(r, warn, alarm),
                         "system": bool(o.get("system")), "flow_dependent": bool(o.get("flow_dependent")),
                         "excluded": col in flagged})

    findings: List[Dict] = []
    if outside:
        findings.append(finding("model_range", NOTICE, "工况超出仿真基准表范围",
                                "、".join(outside) + "，模型预期按表的边界估算，模型对比仅供参考", "仿真模型", "仿真模型"))

    # 1) 系统性偏离：用互校正常的流量计
    system = None
    sys_rows = [r for r in rows if r["system"] and not r["excluded"]]
    if sys_rows:
        rq = float(np.median([r["residual"] for r in sys_rows]))
        warn_q, alarm_q = float(np.median([r["warn"] for r in sys_rows])), float(np.median([r["alarm"] for r in sys_rows]))
        agree = [r for r in sys_rows if np.sign(r["residual"]) == np.sign(rq) and abs(r["residual"]) > warn_q / 2]
        if abs(rq) > warn_q and len(agree) >= min(th.get("system_min_columns", 4), len(sys_rows)):
            sys_out = next(o["name"] for o in sim_cfg["outputs"] if o.get("system"))
            speed_input = sim_cfg["inputs"][0]["name"]
            follow, checked = 0, 0
            for r in rows:
                if not r["flow_dependent"]:
                    continue
                e = sensitivity(table, cond, r["output"], sys_out, speed_input)
                if e is None:
                    continue
                expect = e * rq
                r["explained_by_system"] = expect
                checked += 1
                if np.sign(r["residual"]) == np.sign(expect) and abs(r["residual"]) >= th.get("pressure_consistency", 0.5) * abs(expect):
                    follow += 1
                # 能由流量变化解释的压力偏离，不再单独报
                if abs(r["residual"] - expect) <= r["warn"]:
                    r["severity"] = INFO
            pressures_follow = checked > 0 and follow * 2 > checked
            sev = grade(rq, warn_q, alarm_q)
            expected_flow = pred[sys_out]
            detail = (f"在 {cond_text} 工况下，模型预期流量 {expected_flow:.1f} L/h；{len(sys_rows)} 只流量计彼此一致，"
                      f"整体{'低' if rq < 0 else '高'} {abs(rq) * 100:.2f}%（已扣除各表固有偏差）。")
            if checked:
                detail += (f"与流量相关的 {checked} 个压力测点中有 {follow} 个按模型关系同步变化，"
                           + ("说明实际流量确实变了" if pressures_follow else "压力基本没有随之变化，更像是测量整体偏了"))
            system = {"residual": rq, "warn": warn_q, "alarm": alarm_q, "severity": sev,
                      "pressures_follow": pressures_follow, "pressures_checked": checked, "expected_flow": expected_flow}
            findings.append(finding("model_system", sev, "系统流量偏离模型预期", detail, sys_out, sys_out,
                                    PUMP_COMPONENT, rq * 100,
                                    f"预警 ±{warn_q * 100:.1f}%，异常 ±{alarm_q * 100:.1f}%"))

    # 2) 单个测点
    for r in rows:
        if r["severity"] == INFO or r["excluded"] or (system and r["system"]):
            continue
        text = (f"{r['column']} 实测 {_fmt(r['measured'], r['unit'])}，模型预期 {_fmt(r['expected'], r['unit'])}，"
                f"{'高' if r['residual'] > 0 else '低'} {abs(r['residual']) * 100:.1f}%")
        limit = f"预警 ±{r['warn'] * 100:.1f}%，异常 ±{r['alarm'] * 100:.1f}%"
        if r["kind"] == "pressure":
            findings.append(finding("model_pressure", r["severity"], "压力测点偏离模型预期", text + "（该测点没有冗余表可互校）",
                                    r["column"], r["column"], None, r["residual"] * 100, limit))
        else:
            # 流量计由互校判断；扭矩模型离散大。都只作补充证据
            findings.append(finding("model", NOTICE, "测点偏离模型预期", text, r["column"], r["column"], None,
                                    r["residual"] * 100, limit))
    return {**base, "available": True, "outside": outside, "expected": pred, "rows": rows, "system": system,
            "findings": findings}


def summary_rows(result: Dict) -> List[Dict]:
    """报告“检测明细”用：每个模型输出一行（多只表取中位数）。"""
    out = []
    by_output: Dict[str, List[Dict]] = {}
    for r in result.get("rows", []):
        by_output.setdefault(r["output"], []).append(r)
    for name, rs in by_output.items():
        res = float(np.median([r["residual"] for r in rs]))
        expected = float(np.median([r["expected"] for r in rs]))
        unit = rs[0]["unit"]
        out.append({"name": f"模型对比：{name}", "reference": f"预期 {_fmt(expected, unit)}，±{rs[0]['warn'] * 100:.1f}%",
                    "value": f"{res * 100:+.2f}%" + (f"（{len(rs)} 个测点中位数）" if len(rs) > 1 else ""),
                    "abnormal": any(r["severity"] in (WARNING, ABNORMAL) for r in rs)})
    return out
