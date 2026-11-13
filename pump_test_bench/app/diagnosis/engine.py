"""诊断入口：读文件 → 识别稳定段 → 各管路流量诊断 → 模型对比与其他自检 → 汇总结论。

判定依据：
1. 传感器自检：卡死/冻结、掉零、无数据、噪声、毛刺、超量程，同位置温度传感器互校；
2. 流量协调与故障隔离（flow_loop.py → reconcile.py → isolation.py）：同一路油上串联的体积流量计、
   按密度换算的质量流量计、以及仿真模型给出的真实流量参照，一起检验“单表偏离 / 两表偏离 / 泄漏 /
   回油夹气 / 一侧整体偏 / 体积表共模偏 / 实际流量变化”等假设，取最简洁一致的解释并给出概率与其他可能；
   有健康基准时先扣除各表在当前工况下的固有偏差；
3. 变点检测（changepoint.py）：稳定段内偏差突变或渐变时，按变化之后（渐变取末段）的数据判断当前状态；
4. 零点：没有流量的管路上，流量计读数应接近 0；
5. 模型残差（有仿真基准表时）：各表一致但整体偏离（被试泵出力变化等），以及没有冗余表的压力测点偏离
   （见 pump_test_bench/app/simulation/）；
6. 原经验公式（质量流量→涡轮转速→理论流量）只作参考，不参与判定。

结论分四级：正常 / 预警 / 异常 / 无法判定。
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from pump_test_bench.app.core.data_reader import read_table
from pump_test_bench.app.diagnosis import checks as ck, flow_loop, reconcile
from pump_test_bench.app.diagnosis.causes import infer_causes
from pump_test_bench.app.diagnosis.checks import ABNORMAL, INFO, NOTICE, SEVERITY_RANK, WARNING, finding
from pump_test_bench.app.diagnosis.config import config_path, load_config
from pump_test_bench.app.diagnosis.fuel import density
from pump_test_bench.app.diagnosis.signals import Segment, find_steady, time_axis
from pump_test_bench.app.simulation.check import expected_flows, model_check, summary_rows
from pump_test_bench.app.simulation.config import list_models
from pump_test_bench.app.simulation.table import is_stale, load_table

logger = logging.getLogger(__name__)

ALGORITHM_VERSION = "3.0"
RESULT_NORMAL, RESULT_WARNING, RESULT_ABNORMAL, RESULT_INCONCLUSIVE = "normal", "warning", "abnormal", "inconclusive"


# --------------------------------------------------------------------------- 分析（诊断与建基准共用）
def _model_setting(mcfg: Dict, profile: Optional[Dict]) -> Dict:
    return (profile or {}).get(mcfg["id"], {"mode": mcfg.get("default_mode", "decisive")})


def _density_fn(cfg: Dict, baseline: Optional[Dict], fuel_density_20: Optional[float]):
    return lambda t: density(cfg, baseline, t, fuel_density_20)[0]


def _locate(df: pd.DataFrame, t: np.ndarray, cfg: Dict):
    """找出有流量的管路，以第一路有流量的管路确定稳定段。返回 (稳定段, [(管路配置, 是否有流量, 流量序列)])。"""
    loops, segment = [], None
    for loop in cfg["loops"]:
        cols = [m["column"] for m in loop["meters"] if m["column"] in df.columns]
        consensus = df[cols].apply(pd.to_numeric, errors="coerce").median(axis=1) if cols else pd.Series(dtype=float)
        active = bool(len(consensus.dropna())) and float(consensus.mean()) > cfg["thresholds"]["loop_active_flow"]
        loops.append((loop, active, consensus))
        if active and segment is None:
            segment = find_steady(consensus.to_numpy(dtype=float), t, cfg["steady"])
    if segment is None:
        segment = Segment(0, len(df), float(t[0]) if len(t) else 0.0, float(t[-1]) if len(t) else 0.0, False)
    return segment, loops


def _flow_anchor(seg: pd.DataFrame, cfg: Dict, sims: Optional[List], profile: Optional[Dict],
                 density_fn) -> Optional[reconcile.Anchor]:
    """仿真模型（整体偏移含义为“实际流量”的模型，且参与判定）给出的真实流量参照。"""
    floor = cfg.get("isolation", {}).get("anchor_sigma_floor", 0.006)
    for mcfg, table in sims or []:
        rule = (mcfg.get("rules") or {}).get("group_shift") or {}
        if rule.get("meaning") != "pump" or _model_setting(mcfg, profile).get("mode", "decisive") != "decisive":
            continue
        try:
            exp = expected_flows(seg, mcfg, table, density_fn)
        except Exception:
            logger.warning("模型 %s 计算预期流量失败，本次不用作参照", mcfg["id"], exc_info=True)
            continue
        if exp:
            std = list(exp["std"].values())
            return reconcile.Anchor(mcfg["id"], mcfg["name"], exp["expected"],
                                    max(float(np.median(std)) if std else 0.0, floor))
    return None


def _model_checks(seg: pd.DataFrame, cfg: Dict, loops: List[Dict], sims: Optional[List], profile: Optional[Dict],
                  density_fn) -> Tuple[List[Dict], List[Dict]]:
    """与仿真模型在同一工况下的预期值比较（已判为有问题的表不参与系统性判断）。返回 (模型结果, 发现)。"""
    if not sims or not any(lp["active"] for lp in loops):  # 没有流量时不做模型对比
        return [], []
    flagged = {m["column"] for lp in loops for m in lp["meters"] if m.get("severity", INFO) != INFO}
    components = {m["column"]: m.get("component") for lp in cfg["loops"] for m in lp["meters"] if m.get("component")}
    results, findings = [], []
    for mcfg, table in sims:
        setting = _model_setting(mcfg, profile)
        if setting.get("mode") == "off":
            continue
        res = model_check(seg, mcfg, table, flagged, density_fn, setting, components)
        res["mode"] = setting.get("mode", "decisive")
        if res["mode"] == "reference":  # 仅作参考：不影响结论
            for f in res["findings"]:
                if f["severity"] in (WARNING, ABNORMAL):
                    f["raw_severity"], f["severity"], f["reference_only"] = f["severity"], NOTICE, True
        findings.extend(res["findings"])
        results.append(res)
    return results, findings


def _temperature_pairs(seg: pd.DataFrame, cfg: Dict, used_columns: Set[str]) -> List[Dict]:
    """同位置温度传感器互校（油温决定密度修正，偏了会把质量-体积校核带偏）。"""
    out = []
    for pair in cfg.get("temperature_pairs", []):
        a, b = pair["columns"]
        if a not in seg.columns or b not in seg.columns:
            continue
        rule = ck.range_rule(a, cfg.get("sensor_ranges", [])) or {"min": -1e9, "max": 1e9}
        ta, tb = ck.mean_of(seg[a]), ck.mean_of(seg[b])
        if ta is None or tb is None or not all(rule["min"] <= x <= rule["max"] for x in (ta, tb)):
            continue  # 超量程由量程自检报出
        diff = abs(ta - tb)
        sev = ck.grade(diff, pair.get("warn", 3.0), pair.get("alarm", 6.0))
        if sev == INFO:
            continue
        used = a in used_columns and a or (b in used_columns and b) or None
        out.append(finding(
            "temperature", sev if used else NOTICE, "同位置温度传感器不一致",
            f"{a} {ta:.1f} ℃，{b} {tb:.1f} ℃，相差 {diff:.1f} ℃（健康数据中不超过约 1.5 ℃），至少一只有偏差"
            + (f"；密度修正使用的是 {used}，油温每偏 1 ℃ 密度约偏 0.07%" if used else ""),
            used or a, used or a, None, diff, f"预警 {pair.get('warn', 3.0)} ℃，异常 {pair.get('alarm', 6.0)} ℃"))
    return out


def _fuel_notice(cfg: Dict, baseline: Optional[Dict], fuel_density_20: Optional[float]) -> List[Dict]:
    """燃油换批：设置的密度与建立健康基准时的油品相差较大。"""
    model = (baseline or {}).get("density")
    if not fuel_density_20 or not model:
        return []
    base20 = model["rho15"] + model["slope"] * 5
    diff = (fuel_density_20 - base20) / base20
    if abs(diff) <= 0.01:
        return []
    return [finding(
        "fuel", NOTICE, "燃油与健康基准的油品不同",
        f"设置的燃油密度 {fuel_density_20:.1f} kg/m³，建立健康基准时的油品约 {base20:.1f} kg/m³（20 ℃），"
        f"相差 {diff * 100:+.1f}%。质量-体积校核已按设置的密度计算；涡轮流量计的固有偏差与油品粘度有关，"
        "长期使用新油品时建议用新油的正常数据重建健康基准", "fuel", "燃油", None, diff * 100)]


def _sensor_ranges(df: pd.DataFrame, cfg: Dict, used_columns: Set[str]) -> List[Dict]:
    """传感器量程自检（全部数值列；诊断用到的列影响结论，其余只作“注意”）。已知故障的测点不重复报警。"""
    ignored = {s["column"]: s.get("reason", "") for s in cfg.get("ignored_sensors", [])}
    out = []
    for col in df.columns:
        rule = ck.range_rule(col, cfg.get("sensor_ranges", []))
        if not rule or df[col].dtype.kind != "f":
            continue
        ratio = ck.out_of_range_ratio(df[col], rule)
        if col in ignored:
            if ratio == 0 and not ck.is_stuck(df[col]):
                out.append(finding("sensor", NOTICE, "已屏蔽的测点读数恢复正常",
                                   f"{col} 在已知故障清单中（{ignored[col] or '未注明原因'}），本次读数正常，"
                                   "确认修复后可从 bench.json 的 ignored_sensors 中移除", col, col))
            continue
        if ratio > 0.05:
            mean = ck.mean_of(df[col])
            out.append(finding("sensor", ABNORMAL if col in used_columns else NOTICE, "传感器读数超出合理范围",
                               f"{col} 均值 {mean:.3f}，{ratio * 100:.0f}% 的读数超出 [{rule['min']}, {rule['max']}]，"
                               "可能是断线、未接入或量程设置错误", col, col, None, mean,
                               f"[{rule['min']}, {rule['max']}]"))
    return out


def _segment_notice(segment: Segment, loops: List[Dict]) -> List[Dict]:
    if segment.found or not any(lp["active"] for lp in loops):
        return []
    return [finding("segment", NOTICE, "未识别到稳定段",
                    "流量在整个文件中都没有稳定下来（升降速、调节过程或采集时间过短），已用全部数据分析；"
                    "各项偏差包含了工况变化的影响，结论仅供参考", "segment", "分析数据段")]


def analyze(df: pd.DataFrame, cfg: Dict, baseline: Optional[Dict] = None,
            fuel_density_20: Optional[float] = None, sims: Optional[List] = None,
            profile: Optional[Dict] = None) -> Dict:
    """fuel_density_20：当前燃油 20 ℃ 密度（kg/m³），不填时用健康基准/配置的密度-温度模型。
    sims：[(模型配置, 仿真基准表), ...]；profile：诊断方案 {模型 id: {mode, sigma_warn, sigma_alarm}}。"""
    configured = [m["column"] for lp in cfg["loops"] for m in lp["meters"]]
    if not any(c in df.columns for c in configured):
        raise ValueError(f"文件中没有诊断配置里的任何流量计列（{'、'.join(configured)}），"
                         "请确认数据文件，或在 pump_test_bench/config/bench.json 中核对列名")
    t = time_axis(df)
    segment, located = _locate(df, t, cfg)
    seg = df.iloc[segment.start:segment.end]
    density_fn = _density_fn(cfg, baseline, fuel_density_20)
    ctx = flow_loop.Context(cfg, baseline, segment, seg, t[segment.start:segment.end], fuel_density_20,
                            _flow_anchor(seg, cfg, sims, profile, density_fn))

    loops, findings, used_columns = [], [], set()
    for loop, active, consensus in located:
        level = float(consensus.iloc[segment.start:segment.end].mean()) if active else 0.0
        res = flow_loop.analyze_loop(ctx, loop, active, level)
        loops.append(res.summary)
        findings += res.findings
        used_columns |= res.columns

    models, model_findings = _model_checks(seg, cfg, loops, sims, profile, density_fn)
    findings += model_findings
    findings += _temperature_pairs(seg, cfg, used_columns)
    findings += _fuel_notice(cfg, baseline, fuel_density_20)
    findings += _sensor_ranges(df, cfg, used_columns)
    findings += _segment_notice(segment, loops)
    ignored = {s["column"]: s.get("reason", "") for s in cfg.get("ignored_sensors", [])}
    return {"segment": segment, "loops": loops, "findings": findings,
            "condition": _condition(seg, cfg, loops), "models": models,
            "ignored": [f"{c}（{r}）" if r else c for c, r in ignored.items() if c in df.columns]}


def _condition(seg: pd.DataFrame, cfg: Dict, loops: List[Dict]) -> Dict:
    cond = {}
    main = next((r for r in loops if r["active"]), None)
    if main and main.get("temperature") is not None:
        cond["温度"] = round(main["temperature"], 1)
    for name, col in cfg.get("condition", {}).get("speed_columns", {}).items():
        if col in seg.columns:
            v = ck.mean_of(seg[col])
            step = cfg["condition"]["speed_step"].get(name, 1)
            if v is not None:
                cond[name] = int(round(v / step) * step)
    if main and main.get("consensus"):
        cond["流量"] = round(main["consensus"], 1)
    parts = []
    if "温度" in cond:
        parts.append(f"油温 {cond['温度']}℃")
    for name in cfg.get("condition", {}).get("speed_columns", {}):
        if name in cond:
            parts.append(f"{name} {cond[name]} rpm")
    if "流量" in cond:
        parts.append(f"流量 {cond['流量']} L/h")
    cond["label"] = " · ".join(parts) or "未知工况"
    return cond


# --------------------------------------------------------------------------- 诊断
def _indicators(analysis: Dict) -> List[Dict]:
    seg = analysis["segment"]
    rows = [
        {"name": "试验工况", "reference": "—", "value": analysis["condition"]["label"]},
        {"name": "分析数据段", "reference": "稳定段",
         "value": f"{seg.start_s:.1f}–{seg.end_s:.1f} 秒（{seg.duration:.0f} 秒，{seg.end - seg.start} 行）"
         if seg.found else f"未识别到稳定段，使用全部数据（{seg.end - seg.start} 行）"},
    ]
    if analysis.get("ignored"):
        rows.append({"name": "已屏蔽测点", "reference": "bench.json ignored_sensors",
                     "value": "、".join(analysis["ignored"])})
    for loop in analysis["loops"]:
        if not loop["active"]:
            continue
        if loop.get("consensus"):
            rows.append({"name": f"{loop['name']} 流量共识值", "reference": "各流量计中位数",
                         "value": f"{loop['consensus']:.1f} L/h"})
        for m in loop["meters"]:
            if "corrected" in m:
                rows.append({"name": f"{m['label']} 偏差", "reference": f"±{m['warn'] * 100:.1f}% / ±{m['alarm'] * 100:.1f}%",
                             "value": f"{m['corrected'] * 100:+.2f}%（{m['mean']:.1f} L/h）",
                             "abnormal": m["severity"] in (WARNING, ABNORMAL)})
        if loop.get("balance"):
            b = loop["balance"]
            rows.append({"name": f"{loop['name']} 供回油平衡", "reference": f"±{b['warn'] * 100:.1f}% / ±{b['alarm'] * 100:.1f}%",
                         "value": f"{b['corrected'] * 100:+.2f}%", "abnormal": b["severity"] in (WARNING, ABNORMAL)})
        mass = loop.get("mass")
        if mass and mass.get("density"):
            rows.append({"name": "燃油密度", "reference": mass["density_source"],
                         "value": f"{mass['density']:.1f} kg/m³" + (f"（{mass['temperature']:.1f}℃）"
                                                                   if mass.get("temperature") is not None else "")})
        if mass and "deviation" in mass:
            rows.append({"name": f"{mass['label']} 质量-体积校核",
                         "reference": f"±{mass['warn'] * 100:.1f}% / ±{mass['alarm'] * 100:.1f}%",
                         "value": f"{mass['deviation'] * 100:+.2f}%（{mass['q_mass']:.1f} L/h）",
                         "abnormal": mass["severity"] in (WARNING, ABNORMAL)})
        if loop.get("legacy"):
            lg = loop["legacy"]
            rows.append({"name": "经验公式理论流量（参考）", "reference": "不参与判定",
                         "value": f"{lg['q_theory']:.1f} L/h，偏差 {lg['deviation'] * 100:+.1f}%"
                         + ("" if lg["valid"] else "（超出公式适用范围）")})
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

    causes = infer_causes(findings, analysis["loops"])
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
        analysis_text = "所有管路都没有流量，无法诊断流量计。"
        advice = ["在有流量的稳定工况下重新采集数据后再诊断。"]
        summary = "无法判定：没有流量"
    elif result == RESULT_INCONCLUSIVE and not analysis["segment"].found:
        fault_name, location = "无法判定", "、".join(lp["name"] for lp in active)
        analysis_text = "流量在整个文件中都没有稳定下来，各项偏差包含了工况变化的影响，没有发现明确的故障，但不能据此判为正常。"
        advice = ["在稳定工况下（转速、流量保持不变）重新采集数据后再诊断。"]
        summary = "无法判定：没有稳定工况"
    elif result == RESULT_INCONCLUSIVE:
        fault_name, location = "无法判定", "、".join(lp["name"] for lp in active)
        analysis_text = "有效的流量计不足两只，且没有可用的质量流量计，无法互相校核。"
        advice = ["确认数据文件包含诊断配置中的各流量计列，或在 bench.json 中核对管路与测点的对应关系。"]
        summary = "无法判定：可校核的流量计不足"
    else:
        fault_name, location = "未发现异常", "、".join(lp["name"] for lp in active)
        analysis_text = "各流量计读数相互一致，质量-体积校核通过，传感器自检正常。"
        advice = ["无需处理。"]
        summary = "正常：各流量计读数一致"

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
    }


def _loop_summary(loop: Dict) -> Dict:
    """供前端展示的管路摘要（只保留可序列化的字段）。"""
    keep = ("column", "label", "group", "component", "mean", "deviation", "bias", "corrected", "warn", "alarm",
            "severity", "cv", "stuck")
    out = {"name": loop["name"], "active": loop["active"], "consensus": loop.get("consensus"),
           "meters": [{k: m[k] for k in keep if k in m} for m in loop["meters"]]}
    for key in ("balance", "mass", "legacy", "isolation"):
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
