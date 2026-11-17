"""诊断入口：读文件 → 识别稳定段 → 单信号自检 → 模型预期 → 主油路流量故障隔离 → 分段检查 → 汇总结论。

诊断只使用 bench.json 中的 9 个信号（P9、供油温度1-2、供油流量1-2、P1、电传转速、P5、回油温度1-1、
回油流量1-2、P6），判定依据：
1. 单信号自检（sensor_checks.py）：无数据、卡死、冻结、掉零、超量程、噪声、毛刺，P1 偏离设定档位；
2. 模型预期（expectation.py）：仿真模型按电传转速、油温、P1 给出两只流量计、P9、P5、P6、回油温度的
   健康预期值（含各测点的固有偏差）；
3. 流量故障隔离（flow_diagnosis.py → hypotheses.py → isolation.py）：两只流量计、P5、P6 与模型预期一起检验
   “某只流量计偏 / 两只同时偏 / 泄漏 / 实际流量变化（被试泵出力、电传转速信号）/ 回油阻力增大 / P5、P6 传感器偏”
   等假设，取最简洁一致的解释并给出可能性与其他解释；稳定段内有突变或渐变时按变化之后的数据判断（changepoint.py）；
4. 涡轮流量计二级诊断（turbine_check.py）：怀疑某只流量计时用涡轮流量计模型复核，以较低权重并入隔离；
5. 分段检查（section_checks.py）：供油段压差（P9 相对预期）、温升（回油温度相对预期）。

结论分四级：正常 / 预警 / 异常 / 无法判定。
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from pump_test_bench.app.core.data_reader import read_table
from pump_test_bench.app.diagnosis import checks as ck, flow_diagnosis, section_checks
from pump_test_bench.app.diagnosis.bench_signals import (INLET_PRESSURE, SPEED, SUPPLY_FLOW, SUPPLY_TEMPERATURE,
                                                          RETURN_FLOW, SignalSet)
from pump_test_bench.app.diagnosis.causes import infer_causes
from pump_test_bench.app.diagnosis.checks import ABNORMAL, NOTICE, SEVERITY_RANK, WARNING, finding, grade
from pump_test_bench.app.diagnosis.config import config_path, load_config
from pump_test_bench.app.diagnosis.expectation import ModelView, model_view
from pump_test_bench.app.diagnosis.fuel import density
from pump_test_bench.app.diagnosis.sensor_checks import check_signals
from pump_test_bench.app.diagnosis.signals import Segment, find_steady, time_axis
from pump_test_bench.app.simulation.check import summary_rows
from pump_test_bench.app.simulation.config import list_models
from pump_test_bench.app.simulation.table import is_stale, load_table

logger = logging.getLogger(__name__)

ALGORITHM_VERSION = "4.0"
RESULT_NORMAL, RESULT_WARNING, RESULT_ABNORMAL, RESULT_INCONCLUSIVE = "normal", "warning", "abnormal", "inconclusive"


# --------------------------------------------------------------------------- 分析（诊断与建基准共用）
def _density_fn(cfg: Dict, baseline: Optional[Dict], fuel_density_20: Optional[float]):
    return lambda t: density(cfg, baseline, t, fuel_density_20)[0]


def _flow_consensus(df: pd.DataFrame, signals: SignalSet) -> pd.Series:
    cols = [c for c in (signals.column(SUPPLY_FLOW), signals.column(RETURN_FLOW)) if c in df.columns]
    return df[cols].apply(pd.to_numeric, errors="coerce").mean(axis=1)


def _locate(df: pd.DataFrame, t: np.ndarray, cfg: Dict, signals: SignalSet):
    """返回 (稳定段, 是否有流量)。对每只流量计各找一次稳定段，取最长的：
    一只表出故障（掉零、中途突变）时，按另一只表仍能找到完整的稳定段。"""
    consensus = _flow_consensus(df, signals)
    active = bool(len(consensus.dropna())) and float(consensus.mean()) > cfg["thresholds"]["active_flow"]
    n = len(df)
    whole = Segment(0, n, float(t[0]) if n else 0.0, float(t[-1]) if n else 0.0, False)
    if not active:
        return whole, False
    candidates = []
    for col in (signals.column(SUPPLY_FLOW), signals.column(RETURN_FLOW)):
        if col and col in df.columns:
            values = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
            if np.nanmean(values) > cfg["thresholds"]["active_flow"]:
                candidates.append(find_steady(values, t, cfg["steady"]))
    found = [c for c in candidates if c.found]
    return (max(found, key=lambda c: c.duration) if found else whole), True


def _fault_limits(cfg: Dict, column: str, kind: str, mode: str) -> tuple:
    th = cfg["thresholds"]
    if kind == "flow":
        return th["faults"]["meter"]["warn"], th["faults"]["meter"]["alarm"]
    if kind == "temperature":
        return th["temperature_rise"]["warn"], th["temperature_rise"]["alarm"]
    if mode == "absolute":
        return th["supply_drop"]["warn"], th["supply_drop"]["alarm"]
    return th["faults"]["pressure_sensor"]["warn"], th["faults"]["pressure_sensor"]["alarm"]


def _model_report(view: ModelView, status: Dict, cfg: Dict, loop: Dict) -> List[Dict]:
    """报告中的模型对比：各信号实测 vs 模型预期（展示用；判定由故障隔离与分段检查给出）。"""
    base = {"id": view.model_id, "name": view.name or "标准台系统模型", "mode": view.mode, "model": view.label,
            "table_created": view.table_created, "condition": view.condition, "notes": view.notes,
            "outside": view.outside, "available": view.available, "rows": []}
    for col, e in view.expected.items():
        st = status.get(col)
        if not st or st.mean is None:
            continue
        r = e.residual(st.mean)
        warn, alarm = _fault_limits(cfg, col, e.kind, e.mode)
        if e.sigma:
            warn, alarm = max(warn, 4 * e.sigma), max(alarm, 8 * e.sigma)
        base["rows"].append({"column": col, "output": e.output, "kind": e.kind, "unit": e.unit, "mode": e.mode,
                             "measured": st.mean, "expected": e.value, "residual": r, "warn": warn, "alarm": alarm,
                             "severity": grade(r, warn, alarm), "component": e.component, "excluded": False})
    out = [base]
    turbine = [t for t in (loop.get("isolation") or {}).get("turbine") or [] if t.get("available")]
    if turbine:
        out.append({"id": "turbine", "name": "涡轮流量计模型（二级诊断）", "mode": "reference", "model": "",
                    "available": True, "condition": turbine[0].get("condition", {}), "notes": [], "outside": [],
                    "rows": [{"column": f"{t['label']} 转速", "output": t["label"], "kind": "flow", "unit": "Hz",
                              "mode": "relative", "measured": t["measured_hz"], "expected": t["expected_hz"],
                              "residual": t["residual"], "warn": 2 * t["sigma"], "alarm": 4 * t["sigma"],
                              "severity": grade(t["residual"], 2 * t["sigma"], 4 * t["sigma"]), "excluded": False}
                             for t in turbine]})
    return out


def _model_notices(view: ModelView, active: bool) -> List[Dict]:
    if not active:
        return []
    if not view.available:
        return [finding("model", NOTICE, "没有模型参照",
                        "；".join(view.notes) + "。只能比较两只流量计，无法判断泄漏、被试泵出力与压力测点",
                        view.model_id, view.name or "仿真模型")]
    if view.outside:
        return [finding("model_range", NOTICE, "工况超出仿真模型范围",
                        f"{view.name}：" + "、".join(view.outside) + "，按模型边界估算，结论可信度下降",
                        view.model_id, view.name)]
    return []


def _segment_notice(segment: Segment, active: bool) -> List[Dict]:
    if segment.found or not active:
        return []
    return [finding("segment", NOTICE, "未识别到稳定段",
                    "流量在整个文件中都没有稳定下来（升降速、调节过程或采集时间过短），已用全部数据分析；"
                    "各项偏差包含了工况变化的影响，结论仅供参考", "segment", "分析数据段")]


def _missing_notice(missing: List[str]) -> List[Dict]:
    if not missing:
        return []
    return [finding("sensor", NOTICE, "数据中缺少诊断信号", f"文件中没有 {'、'.join(missing)}，相关判断已跳过",
                    "signals", "诊断信号")]


def _condition(status: Dict, signals: SignalSet, flow: Optional[float]) -> Dict:
    cond = {}

    def mean(key):
        col = signals.column(key)
        st = status.get(col) if col else None
        return st.mean if st and st.usable else None

    t, n, p1 = mean(SUPPLY_TEMPERATURE), mean(SPEED), mean(INLET_PRESSURE)
    parts = []
    if t is not None:
        cond["温度"] = round(t, 1)
        parts.append(f"油温 {cond['温度']}℃")
    if n is not None:
        cond["电传"] = int(round(n / 500) * 500)
        parts.append(f"电传 {cond['电传']} rpm")
    if p1 is not None:
        cond["P1"] = round(p1, 3)
        parts.append(f"P1 {p1:.2f} MPa")
    if flow:
        cond["流量"] = round(flow, 1)
        parts.append(f"流量 {cond['流量']} L/h")
    cond["label"] = " · ".join(parts) or "未知工况"
    return cond


def analyze(df: pd.DataFrame, cfg: Dict, baseline: Optional[Dict] = None,
            fuel_density_20: Optional[float] = None, sims: Optional[List] = None,
            profile: Optional[Dict] = None) -> Dict:
    """fuel_density_20：当前燃油 20 ℃ 密度（kg/m³，涡轮流量计二级诊断用）。
    sims：[(模型配置, 仿真基准表), ...]；profile：诊断方案 {模型 id: {mode}}。"""
    all_signals = SignalSet.from_config(cfg)
    signals = all_signals.present(df.columns)
    if not any(signals.get(k) for k in (SUPPLY_FLOW, RETURN_FLOW)):
        flows = "、".join(c for c in (all_signals.column(SUPPLY_FLOW), all_signals.column(RETURN_FLOW)) if c)
        raise ValueError(f"文件中没有诊断用的流量计列（{flows}），请确认数据文件，"
                         "或在 pump_test_bench/config/bench.json 的 signals 中核对列名")
    missing = [s.column for s in all_signals if s.column not in df.columns]
    t = time_axis(df)
    segment, active = _locate(df, t, cfg, signals)
    seg, seg_t = df.iloc[segment.start:segment.end], t[segment.start:segment.end]
    level = float(_flow_consensus(seg, signals).mean()) if active else 0.0
    # 没有流量（停机）时读数不变是正常的，只检查量程
    status, findings = check_signals(df, seg, seg_t, segment.duration, signals, cfg, baseline, level,
                                     only=None if active else ("range",))
    findings += _missing_notice(missing)
    temp_col = signals.column(SUPPLY_TEMPERATURE)
    temperature = status[temp_col].mean if temp_col and status[temp_col].usable else None
    density_fn = _density_fn(cfg, baseline, fuel_density_20)
    unusable = {c for c, st in status.items() if not st.usable}
    view = model_view(seg, cfg, sims, profile, density_fn, unusable, signals.column(SUPPLY_FLOW)) if active \
        else ModelView(False)

    loop = {"name": "主油路", "active": False, "meters": [], "balance": None, "mass": None, "consensus": None}
    flow = None
    if active:
        ctx = flow_diagnosis.FlowContext(cfg, baseline, seg, seg_t, signals, status, view, list(sims or []),
                                         density_fn, temperature)
        flow = flow_diagnosis.diagnose(ctx)
        loop = flow.loop
        findings += flow.findings
        findings += section_checks.supply_section(signals, status, view, cfg, True)
        findings += section_checks.temperature_rise(signals, status, view, cfg, True)
    findings += _model_notices(view, active)
    findings += _segment_notice(segment, active)
    return {"segment": segment, "loops": [loop], "findings": findings,
            "condition": _condition(status, signals, loop.get("consensus")),
            "models": _model_report(view, status, cfg, loop) if active else [],
            "signals": [st.as_dict() for st in status.values()], "view": view, "status": status,
            "observations": flow.observations if flow else [], "change": flow.change if flow else None,
            "ignored": []}


# --------------------------------------------------------------------------- 诊断
def _indicators(analysis: Dict) -> List[Dict]:
    seg = analysis["segment"]
    rows = [
        {"name": "试验工况", "reference": "—", "value": analysis["condition"]["label"]},
        {"name": "分析数据段", "reference": "稳定段",
         "value": f"{seg.start_s:.1f}–{seg.end_s:.1f} 秒（{seg.duration:.0f} 秒，{seg.end - seg.start} 行）"
         if seg.found else f"未识别到稳定段，使用全部数据（{seg.end - seg.start} 行）"},
    ]
    for loop in analysis["loops"]:
        if not loop["active"]:
            continue
        iso_info = loop.get("isolation")
        if iso_info:
            rows.append({"name": "故障隔离结论", "reference": "最可能的解释",
                         "value": f"{iso_info['explanation']}（可能性约 {iso_info['probability'] * 100:.0f}%）",
                         "abnormal": iso_info["explanation"] != "各信号都正常"})
        for m in loop["meters"]:
            if "corrected" in m:
                rows.append({"name": f"{m['label']} 偏差", "reference": f"±{m['warn'] * 100:.1f}% / ±{m['alarm'] * 100:.1f}%",
                             "value": f"{m['corrected'] * 100:+.2f}%（{m['mean']:.1f} L/h）",
                             "abnormal": m["severity"] in (WARNING, ABNORMAL)})
        if loop.get("balance"):
            b = loop["balance"]
            rows.append({"name": "供回油平衡", "reference": f"±{b['warn'] * 100:.1f}% / ±{b['alarm'] * 100:.1f}%",
                         "value": f"{b['corrected'] * 100:+.2f}%", "abnormal": b["severity"] in (WARNING, ABNORMAL)})
    for m in analysis.get("models") or []:
        if m.get("available"):
            rows += summary_rows(m)
    return rows


def build_report_body(analysis: Dict, baseline: Optional[Dict] = None) -> Dict:
    findings = list(analysis["findings"])
    findings.sort(key=lambda f: -SEVERITY_RANK[f["severity"]])
    decisive = [f for f in findings if SEVERITY_RANK[f["severity"]] >= SEVERITY_RANK[WARNING]]
    active = [lp for lp in analysis["loops"] if lp["active"]]

    if any(f["severity"] == ABNORMAL for f in decisive):
        result = RESULT_ABNORMAL
    elif decisive:
        result = RESULT_WARNING
    elif not active or not any(lp.get("checked") for lp in active) or not analysis["segment"].found:
        result = RESULT_INCONCLUSIVE
    else:
        result = RESULT_NORMAL

    causes = infer_causes(findings, analysis.get("signals"))
    if decisive:
        fault_name = "、".join(c["name"] for c in causes)
        location = "、".join(dict.fromkeys(c["location"] for c in causes if c["location"]))
        parts = []
        for i, c in enumerate(causes, 1):
            text = f"{i}. [{ck.SEVERITY_TEXT[c['severity']]}] {c['name']}：{c['explanation']}"
            text += "".join(f"\n   依据：{e}" for e in c["evidence"])
            if c["alternatives"]:
                text += "\n   其他可能：" + "；".join(c["alternatives"])
            parts.append(text)
        analysis_text = "\n".join(parts)
        advice = list(dict.fromkeys(c["advice"] for c in causes))
        head = causes[0]["name"]
        summary = f"{'异常' if result == RESULT_ABNORMAL else '预警'}：{head}" + (
            f" 等 {len(causes)} 项" if len(causes) > 1 else "")
    elif result == RESULT_INCONCLUSIVE and not active:
        fault_name, location = "无法判定", "—"
        analysis_text = "主油路没有流量，无法诊断。"
        advice = ["在有流量的稳定工况下重新采集数据后再诊断。"]
        summary = "无法判定：没有流量"
    elif result == RESULT_INCONCLUSIVE and not analysis["segment"].found:
        fault_name, location = "无法判定", "、".join(lp["name"] for lp in active)
        analysis_text = "流量在整个文件中都没有稳定下来，各项偏差包含了工况变化的影响，没有发现明确的故障，但不能据此判为正常。"
        advice = ["在稳定工况下（转速、流量保持不变）重新采集数据后再诊断。"]
        summary = "无法判定：没有稳定工况"
    elif result == RESULT_INCONCLUSIVE:
        fault_name, location = "无法判定", "、".join(lp["name"] for lp in active)
        analysis_text = "可用的流量计不足，且没有可用的模型参照，无法判断。"
        advice = ["确认数据文件包含诊断信号（bench.json 的 signals），并在“仿真模型”页面建立标准台系统模型。"]
        summary = "无法判定：可用的信号不足"
    else:
        fault_name, location = "未发现异常", "、".join(lp["name"] for lp in active)
        analysis_text = "各信号自检正常，两只流量计、P5、P6、P9、回油温度都与模型预期一致。"
        advice = ["无需处理。"]
        summary = "正常：各信号与模型预期一致"

    notices = [f for f in findings if f["severity"] == NOTICE]
    if notices:
        advice.append("另外（不影响本次结论）：" + "；".join(f["detail"] for f in notices))

    return {
        "result": result,
        "summary": summary,
        "condition": analysis["condition"],
        "segment": analysis["segment"].as_dict(),
        "causes": causes,
        "findings": findings,
        "loops": [_loop_summary(lp) for lp in analysis["loops"]],
        "indicators": _indicators(analysis),
        "diagnosis": {"fault_name": fault_name, "location": location, "analysis": analysis_text},
        "repair_advice": "\n".join(a for a in advice if a),
        "algorithm": {
            "version": ALGORITHM_VERSION,
            "config": str(config_path().name),
            "baseline": {k: baseline[k] for k in ("created", "source", "files") if k in baseline} if baseline else None,
        },
        "models": [_model_summary(m) for m in analysis.get("models") or []],
        "signals": analysis.get("signals", []),
    }


def _loop_summary(loop: Dict) -> Dict:
    """供前端展示的管路摘要（只保留可序列化的字段）。"""
    keep = ("column", "label", "group", "component", "mean", "deviation", "bias", "corrected", "warn", "alarm",
            "severity", "cv", "stuck")
    out = {"name": loop["name"], "active": loop["active"], "consensus": loop.get("consensus"),
           "meters": [{k: m[k] for k in keep if k in m} for m in loop["meters"]]}
    for key in ("balance", "isolation"):
        if loop.get(key):
            out[key] = loop[key]
    return out


def _model_summary(model: Dict) -> Dict:
    """报告中的一个模型对比（可序列化）。"""
    keep = ("column", "output", "kind", "unit", "mode", "measured", "expected", "residual", "warn", "alarm",
            "severity", "excluded", "component", "system")
    return {"id": model["id"], "name": model["name"], "mode": model.get("mode"), "available": model["available"],
            "model": model["model"], "table_created": model.get("table_created"), "condition": model["condition"],
            "notes": model["notes"], "outside": model.get("outside", []), "group": model.get("group"),
            "rows": [{k: r[k] for k in keep if k in r} for r in model.get("rows", [])]}


def load_sims() -> List:
    """所有已配置、且有基准表的仿真模型：[(模型配置, 基准表), ...]。"""
    out = []
    try:
        for mcfg in list_models():
            table = load_table(mcfg["id"])
            if table and not is_stale(table, mcfg):  # 配置改过、基准表没重建的模型不参与
                out.append((mcfg, table))
    except Exception:
        logger.warning("加载仿真模型失败，本次不做模型对比", exc_info=True)
    return out


def diagnose_frame(df: pd.DataFrame, density: Optional[float] = None, baseline: Optional[Dict] = None,
                   cfg: Optional[Dict] = None, sims="auto", profile: Optional[Dict] = None) -> Dict:
    """sims："auto" 用所有有基准表的模型，None 不做模型对比；profile：诊断方案，不传用保存的方案。"""
    from pump_test_bench.app.diagnosis.settings import profile as current_profile
    cfg = cfg or load_config()
    if sims == "auto":
        sims = load_sims()
    if sims and profile is None:
        profile = current_profile()
    analysis = analyze(df, cfg, baseline, density, sims, profile)
    # 扩展插件（diagnosis/plugins.py）：分析器的发现参与结论；推理器（如大模型智能体）在结论后给出独立意见
    from pump_test_bench.app.diagnosis import plugins
    seg = analysis["segment"]
    ctx = plugins.DiagnosisContext(df, df.iloc[seg.start:seg.end], cfg, analysis, baseline, density,
                                   list(sims or []), profile or {})
    analysis["findings"].extend(plugins.run_analyzers(ctx))
    body = build_report_body(analysis, baseline)
    body["profile"] = profile or {}
    reviews = plugins.run_reasoners(body, ctx)
    if reviews:
        body["reviews"] = reviews
    return body


def diagnose_file(path: Path, density: Optional[float] = None, models: Optional[Dict] = None) -> Dict:
    """models：本次诊断临时调整的诊断方案（只覆盖给出的模型）。"""
    from pump_test_bench.app.diagnosis.baseline import load_baseline  # 避免循环导入
    from pump_test_bench.app.diagnosis.settings import profile as current_profile
    _, df = read_table(path)
    return diagnose_frame(df, density, load_baseline(), profile=current_profile(models))
