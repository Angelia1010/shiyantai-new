"""诊断入口：读文件 → 识别稳定段 → 各项检查 → 汇总结论。

判定依据（按可信度从高到低）：
1. 冗余比对：同一路油上串联的多个流量计，每个表与“其余各表的中位数”比较（留一法），
   偏差大的就是嫌疑表。不依赖任何模型，有健康基准时扣除每个表的固有偏差；
2. 供回油平衡：供油组与回油组的中位数之差，持续偏离说明泄漏或分流；
3. 质量-体积校核：质量流量 ÷ 密度（按温度修正）与体积流量共识值比较，校核质量流量计；
4. 零点：没有流量的管路上，流量计读数应接近 0；
5. 传感器自检：卡死、超量程、噪声、毛刺；
6. 原经验公式（质量流量→涡轮转速→理论流量）只作参考，不参与判定；
7. AMESim 仿真对比（有仿真数据时）作为辅助证据。

结论分四级：正常 / 预警 / 异常 / 无法判定。
"""
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from pump_test_bench.app.core import flow_meter as legacy
from pump_test_bench.app.core.data_reader import read_table
from pump_test_bench.app.diagnosis import checks as ck
from pump_test_bench.app.diagnosis.checks import ABNORMAL, INFO, NOTICE, SEVERITY_RANK, WARNING, finding
from pump_test_bench.app.diagnosis.config import config_path, load_config
from pump_test_bench.app.diagnosis.signals import Segment, find_steady, time_axis

ALGORITHM_VERSION = "2.0"
RESULT_NORMAL, RESULT_WARNING, RESULT_ABNORMAL, RESULT_INCONCLUSIVE = "normal", "warning", "abnormal", "inconclusive"


# --------------------------------------------------------------------------- 分析（诊断与建基准共用）
def _density(cfg: Dict, baseline: Optional[Dict], temperature: Optional[float], override: Optional[float]):
    if override:
        return float(override), "输入值"
    model = (baseline or {}).get("density") or cfg.get("fuel") or {}
    if temperature is None or "rho15" not in model:
        return None, "无法计算（缺少温度）"
    rho = model["rho15"] + model["slope"] * (temperature - 15)
    return rho, "健康基准拟合" if (baseline or {}).get("density") else "配置（密度-温度模型）"


def _meter_thresholds(cfg: Dict, base: Optional[Dict], flow: Optional[float] = None,
                      temperature: Optional[float] = None, ranges: Optional[Dict] = None):
    """返回 (该表在当前工况下的固有偏差, 预警阈值, 异常阈值)。"""
    from pump_test_bench.app.diagnosis.baseline import predict_bias  # 避免循环导入
    th = cfg["thresholds"]["redundancy"]
    if not base:
        return 0.0, th["warn"], th["alarm"]
    std = base.get("std", 0.0)
    warn = max(th["baseline_warn_floor"], th["baseline_warn_sigma"] * std)
    alarm = max(th["baseline_alarm_floor"], th["baseline_alarm_sigma"] * std)
    return predict_bias(base, flow, temperature, ranges), warn, alarm


def analyze(df: pd.DataFrame, cfg: Dict, baseline: Optional[Dict] = None, density_override: Optional[float] = None) -> Dict:
    t = time_axis(df)
    th = cfg["thresholds"]
    bmeters = (baseline or {}).get("meters", {})
    findings: List[Dict] = []

    configured = [m["column"] for lp in cfg["loops"] for m in lp["meters"]]
    if not any(c in df.columns for c in configured):
        raise ValueError(f"文件中没有诊断配置里的任何流量计列（{'、'.join(configured)}），"
                         "请确认数据文件，或在 pump_test_bench/config/bench.json 中核对列名")

    # 1) 找出有流量的管路，以第一路有流量的管路确定稳定段
    loops = []
    segment: Optional[Segment] = None
    for loop in cfg["loops"]:
        cols = [m["column"] for m in loop["meters"] if m["column"] in df.columns]
        consensus = df[cols].apply(pd.to_numeric, errors="coerce").median(axis=1) if cols else pd.Series(dtype=float)
        level = float(consensus.mean()) if len(consensus.dropna()) else 0.0
        active = level > th["loop_active_flow"]
        loops.append({"cfg": loop, "cols": cols, "consensus": consensus, "active": active})
        if active and segment is None:
            segment = find_steady(consensus.to_numpy(dtype=float), t, cfg["steady"])
    if segment is None:
        segment = Segment(0, len(df), float(t[0]) if len(t) else 0.0, float(t[-1]) if len(t) else 0.0, False)
    seg = df.iloc[segment.start:segment.end]
    seg_t = t[segment.start:segment.end]
    diag_columns = set()

    results = []
    for item in loops:
        loop, cols = item["cfg"], item["cols"]
        meters_cfg = [m for m in loop["meters"] if m["column"] in df.columns]
        result = {"name": loop["name"], "active": item["active"], "meters": [], "balance": None,
                  "mass": None, "legacy": None, "consensus": None}
        mass_cfg = loop.get("mass_meter")
        mass_col = mass_cfg["column"] if mass_cfg and mass_cfg["column"] in df.columns else None

        if not item["active"]:
            # 2) 无流量管路：读数应接近零
            for m in meters_cfg:
                mean = ck.mean_of(seg[m["column"]])
                sev = WARNING if mean is not None and abs(mean) > th["zero"]["volume"] else INFO
                result["meters"].append({**m, "mean": mean, "severity": sev})
                if sev == WARNING:
                    findings.append(finding("zero", WARNING, "无流量时读数不为零",
                                            f"{loop['name']}没有流量，但{m['label']}读数均值为 {mean:.2f} L/h",
                                            m["column"], m["label"], m.get("component"), mean,
                                            f"≤{th['zero']['volume']} L/h"))
            if mass_col:
                mean = ck.mean_of(seg[mass_col])
                sev = WARNING if mean is not None and abs(mean) > th["zero"]["mass"] else INFO
                result["mass"] = {"column": mass_col, "label": mass_cfg["label"], "mean": mean, "severity": sev}
                findings.append(finding(
                    "zero", sev, "质量流量计零点偏移" if sev == WARNING else "质量流量计零点",
                    f"{loop['name']}没有流量，{mass_cfg['label']}读数均值为 {mean:.2f} kg/h（零点）",
                    mass_col, mass_cfg["label"], None, mean, f"≤{th['zero']['mass']} kg/h"))
            results.append(result)
            continue

        diag_columns.update(cols)
        if mass_col:
            diag_columns.add(mass_col)
        if loop.get("temperature_column"):
            diag_columns.add(loop["temperature_column"])

        # 3) 冗余比对
        means: Dict[str, float] = {}
        for m in meters_cfg:
            col = m["column"]
            entry = {**m, "mean": ck.mean_of(seg[col]), "severity": INFO}
            if entry["mean"] is None:
                entry["severity"] = ABNORMAL
                findings.append(finding("sensor", ABNORMAL, "流量计无有效数据", f"{m['label']}在稳定段内没有有效读数",
                                        col, m["label"], m.get("component")))
            elif ck.is_stuck(seg[col]):
                entry["severity"] = ABNORMAL
                entry["stuck"] = True
                findings.append(finding("sensor", ABNORMAL, "流量计读数卡死",
                                        f"{m['label']}在 {segment.duration:.0f} 秒内读数始终为 {entry['mean']:.3f}",
                                        col, m["label"], m.get("component"), entry["mean"]))
            else:
                means[col] = entry["mean"]
            result["meters"].append(entry)

        # 油温（密度修正、固有偏差模型都要用）；温度传感器读数不合理时不用
        temp_col = loop.get("temperature_column")
        temperature = ck.mean_of(seg[temp_col]) if temp_col and temp_col in df.columns else None
        temp_rule = ck.range_rule(temp_col or "", cfg.get("sensor_ranges", []))
        if temperature is not None and temp_rule and not (temp_rule["min"] <= temperature <= temp_rule["max"]):
            temperature = None  # 后面的传感器自检会报出来
        level = float(np.median(list(means.values()))) if means else None
        ranges = (baseline or {}).get("ranges")

        # 噪声与毛刺（只对有效的表，不影响均值比较）
        for entry in result["meters"]:
            col = entry["column"]
            if col not in means:
                continue
            cv = ck.window_cv(seg[col], seg_t, cfg["steady"]["window_s"])
            entry["cv"] = cv
            base_cv = bmeters.get(col, {}).get("cv")
            limit = max(th["noise"]["floor"], th["noise"]["ratio"] * base_cv) if base_cv else th["noise"]["floor"]
            if cv is not None and cv > limit:
                findings.append(finding("noise", WARNING, "流量计读数波动过大",
                                        f"{entry['label']}短时波动 {cv * 100:.2f}%，超过 {limit * 100:.2f}%",
                                        col, entry["label"], entry.get("component"), cv * 100, f"≤{limit * 100:.2f}%"))
                entry["noisy"] = True
            ratio = ck.spike_ratio(seg[col], th["spike"]["z"])
            if ratio > th["spike"]["ratio"]:
                findings.append(finding("spike", WARNING, "流量计读数有毛刺",
                                        f"{entry['label']}有 {ratio * 100:.2f}% 的读数明显偏离（突跳）",
                                        col, entry["label"], entry.get("component"), ratio * 100,
                                        f"≤{th['spike']['ratio'] * 100:.1f}%"))
                entry["noisy"] = True

        # 冗余比对 + 泄漏判断：比较两种解释——“单表偏离”与“回油侧整体少了一个比例（泄漏/分流）”
        group_of = {e["column"]: e.get("group", "") for e in result["meters"]}
        bbal = (baseline or {}).get("balance", {}).get(loop["name"], {})
        bal_bias = bbal.get("bias", 0.0)
        bal_warn, bal_alarm = th["balance"]["warn"], th["balance"]["alarm"]
        if bbal.get("std"):
            bal_warn = max(bal_warn, 4 * bbal["std"])
            bal_alarm = max(bal_alarm, 8 * bbal["std"])

        def redundancy(values: Dict[str, float]) -> Dict[str, Dict]:
            out = {}
            if len(values) < 3:
                return out
            for col in values:
                dev = ck.loo_deviation(values, col)
                bias, warn, alarm = _meter_thresholds(cfg, bmeters.get(col), level, temperature, ranges)
                out[col] = {"deviation": dev, "bias": bias, "corrected": dev - bias, "warn": warn, "alarm": alarm,
                            "severity": ck.grade(dev - bias, warn, alarm)}
            return out

        def n_flagged(r: Dict[str, Dict]) -> int:
            return sum(v["severity"] != INFO for v in r.values())

        chosen = redundancy(means)
        leak_ratio = None
        sup = [v for c, v in means.items() if group_of[c] == "供油"]
        ret = [v for c, v in means.items() if group_of[c] == "回油"]
        if sup and ret and len(means) >= 3:
            shift = (float(np.median(sup)) - float(np.median(ret))) / level - bal_bias
            def consistent(group: str) -> bool:
                # 同侧各表（扣除固有偏差后）彼此一致：泄漏时同侧的表一起变化，单表故障时则对不上
                vals = [v / (1 + _meter_thresholds(cfg, bmeters.get(c), level, temperature, ranges)[0])
                        for c, v in means.items() if group_of[c] == group]
                return len(vals) < 2 or (max(vals) - min(vals)) / level <= th["redundancy"]["warn"]

            if abs(shift) > bal_warn and consistent("供油") and consistent("回油"):
                restored = {c: v / (1 - shift) if group_of[c] == "回油" else v for c, v in means.items()}
                alt = redundancy(restored)
                if n_flagged(alt) < n_flagged(chosen):
                    chosen, leak_ratio = alt, shift

        for entry in result["meters"]:
            r = chosen.get(entry["column"])
            if not r:
                continue
            entry.update(r)
            if r["severity"] != INFO:
                c = r["corrected"]
                findings.append(finding(
                    "redundancy", r["severity"], "流量计读数偏离",
                    f"{entry['label']}读数 {entry['mean']:.1f} L/h，比其余流量计的中位数"
                    f"{'高' if c > 0 else '低'} {abs(c) * 100:.2f}%"
                    + (f"（已扣除该表固有偏差 {r['bias'] * 100:+.2f}%）" if r["bias"] else ""),
                    entry["column"], entry["label"], entry.get("component"), c * 100,
                    f"预警 ±{r['warn'] * 100:.1f}%，异常 ±{r['alarm'] * 100:.1f}%"))

        if len(means) == 2:
            (c1, v1), (c2, v2) = means.items()
            diff = abs(v1 - v2) / max(abs((v1 + v2) / 2), 1e-9)
            if diff > th["redundancy"]["alarm"]:
                findings.append(finding("redundancy", WARNING, "两只流量计不一致",
                                        f"{loop['name']}只有两只有效流量计，相差 {diff * 100:.2f}%，无法判断是哪一只的问题",
                                        c1, loop["name"], None, diff * 100))

        # 供回油平衡与共识值（偏离的表不参与；判为泄漏时两侧的表都如实反映了流量，全部参与）。
        # 有健康基准时先扣除各表在当前工况下的固有偏差
        if leak_ratio is not None:
            usable = dict(means)
        else:
            bad = {c for c, r in chosen.items() if r["severity"] != INFO}
            usable = {c: v for c, v in means.items() if c not in bad}
        if bmeters:
            usable = {c: v / (1 + _meter_thresholds(cfg, bmeters.get(c), level, temperature, ranges)[0])
                      for c, v in usable.items()}
            bal_bias = 0.0  # 已逐表扣除，不再用整体平衡偏差
        groups: Dict[str, List[float]] = {}
        for c, v in usable.items():
            groups.setdefault(group_of[c], []).append(v)
        consensus = float(np.median(list(usable.values()))) if usable else None
        result["consensus"] = consensus
        if consensus and groups.get("供油") and groups.get("回油"):
            raw = (float(np.median(groups["供油"])) - float(np.median(groups["回油"]))) / consensus
            corrected = raw - bal_bias
            sev = ck.grade(corrected, bal_warn, bal_alarm)
            result["balance"] = {"raw": raw, "bias": bal_bias, "corrected": corrected, "warn": bal_warn,
                                 "alarm": bal_alarm, "severity": sev}
            if sev != INFO:
                findings.append(finding(
                    "balance", sev, "供回油流量不平衡",
                    f"供油流量比回油流量{'多' if corrected > 0 else '少'} {abs(corrected) * 100:.2f}%"
                    + ("，供油侧与回油侧的流量计各自一致、两侧整体相差" if leak_ratio is not None else "")
                    + "，可能存在泄漏或分流", loop["name"], loop["name"], "回油管路", corrected * 100,
                    f"预警 ±{bal_warn * 100:.1f}%，异常 ±{bal_alarm * 100:.1f}%"))

        # 5) 质量-体积校核
        if mass_col:
            mass_mean = ck.mean_of(seg[mass_col])
            rho, rho_source = _density(cfg, baseline, temperature, density_override)
            # 质量流量计与同一侧（如回油）的体积流量计比较；该侧没有可用的表时用整体共识值
            side = groups.get(mass_cfg.get("group", ""))
            ref_flow = float(np.median(side)) if side else consensus
            mass = {"column": mass_col, "label": mass_cfg["label"], "mean": mass_mean, "density": rho,
                    "density_source": rho_source, "temperature": temperature, "severity": INFO}
            if mass_mean is None or ck.is_stuck(seg[mass_col]):
                mass["severity"] = ABNORMAL
                findings.append(finding("sensor", ABNORMAL, "质量流量计无有效读数或卡死",
                                        f"{mass_cfg['label']}在稳定段内没有变化的有效读数", mass_col, mass_cfg["label"]))
            elif rho is None or not ref_flow:
                findings.append(finding("mass_volume", NOTICE, "无法做质量-体积校核",
                                        f"{rho_source if rho is None else '没有可用的体积流量'}", mass_col, mass_cfg["label"]))
            else:
                q_mass = mass_mean / rho * 1000.0
                dev = (q_mass - ref_flow) / ref_flow
                bmv = (baseline or {}).get("mass_volume", {}).get(loop["name"], {})
                warn, alarm = th["mass_volume"]["warn"], th["mass_volume"]["alarm"]
                if bmv.get("std"):
                    warn = max(warn, 4 * bmv["std"])
                    alarm = max(alarm, 8 * bmv["std"])
                sev = ck.grade(dev, warn, alarm)
                mass.update({"q_mass": q_mass, "reference_flow": ref_flow, "deviation": dev, "warn": warn,
                             "alarm": alarm, "severity": sev})
                if sev != INFO:
                    findings.append(finding(
                        "mass_volume", sev, "质量流量与体积流量不一致",
                        f"{mass_cfg['label']} {mass_mean:.1f} kg/h ÷ 密度 {rho:.1f} kg/m³ = {q_mass:.1f} L/h，"
                        f"比体积流量 {ref_flow:.1f} L/h {'高' if dev > 0 else '低'} {abs(dev) * 100:.2f}%",
                        mass_col, mass_cfg["label"], None, dev * 100,
                        f"预警 ±{warn * 100:.1f}%，异常 ±{alarm * 100:.1f}%"))
            result["mass"] = mass

            # 6) 原经验公式（仅参考）
            if cfg.get("legacy_model", {}).get("enabled") and mass_mean is not None and rho and ref_flow:
                speed = legacy.simulated_speed(mass_mean / 3600.0, rho)
                q_theory = legacy.theoretical_flow(speed)
                valid = speed > 0
                result["legacy"] = {"speed": speed, "q_theory": q_theory, "valid": valid,
                                    "deviation": (q_theory - ref_flow) / ref_flow}
        result["temperature"] = temperature
        result["checked"] = (any("corrected" in m for m in result["meters"]) or len(means) == 2
                             or "deviation" in (result.get("mass") or {}))
        if ranges and level is not None:
            outside = []
            if not ranges["flow"][0] * 0.9 <= level <= ranges["flow"][1] * 1.1:
                outside.append(f"流量 {level:.0f} L/h（基准 {ranges['flow'][0]:.0f}–{ranges['flow'][1]:.0f}）")
            if temperature is not None and not ranges["temperature"][0] - 3 <= temperature <= ranges["temperature"][1] + 3:
                outside.append(f"油温 {temperature:.1f}℃（基准 {ranges['temperature'][0]:.1f}–{ranges['temperature'][1]:.1f}）")
            if outside:
                findings.append(finding("baseline", NOTICE, "工况超出健康基准范围",
                                        "、".join(outside) + "，固有偏差按最接近的工况估算，结论可信度下降，"
                                        "建议补充该工况的健康数据后重建基准", loop["name"], loop["name"]))
        results.append(result)

    # 7) 传感器量程自检（全部数值列；诊断用到的列影响结论，其余只作“注意”）
    for col in df.columns:
        rule = ck.range_rule(col, cfg.get("sensor_ranges", []))
        if not rule or df[col].dtype.kind != "f":
            continue
        ratio = ck.out_of_range_ratio(df[col], rule)
        if ratio > 0.05:
            mean = ck.mean_of(df[col])
            sev = ABNORMAL if col in diag_columns else NOTICE
            findings.append(finding("sensor", sev, "传感器读数超出合理范围",
                                    f"{col} 均值 {mean:.3f}，{ratio * 100:.0f}% 的读数超出 [{rule['min']}, {rule['max']}]，"
                                    "可能是断线、未接入或量程设置错误", col, col, None, mean,
                                    f"[{rule['min']}, {rule['max']}]"))

    return {"segment": segment, "loops": results, "findings": findings,
            "condition": _condition(seg, cfg, results)}


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
def _simulation_findings(sim: Dict) -> List[Dict]:
    out = []
    for d in sim.get("details", []):
        if d.get("exceeded"):
            out.append(finding("simulation", INFO, "仿真对比偏差",
                               f"{d['variable']}：试验 {d['experiment_avg']:.4g}，仿真 {d['simulation_avg']:.4g}，"
                               f"偏差 {d['deviation_text']}", d["variable"], d["variable"]))
    if sim.get("is_abnormal"):
        out.append(finding("simulation", WARNING, "与仿真结果偏差较大", sim["conclusion"], "AMESim", "AMESim 仿真"))
    return out


_ADVICE = {
    "redundancy": "{label} 读数偏离其他流量计，建议对其校准或更换；处理前可暂以其他流量计读数为准。",
    "sensor": "检查 {label} 的接线、供电与量程设置，确认传感器是否损坏或卡死。",
    "balance": "供油与回油流量不平衡，检查管路接头与密封是否泄漏、旁通阀是否关闭严密。",
    "mass_volume": "质量流量与体积流量不一致：各体积流量计互校正常时，优先检查 {label} 的零点与标定，并核对燃油密度。",
    "zero": "无流量管路上 {label} 读数不为零，建议在停流状态下做零点校准。",
    "noise": "{label} 读数波动过大，检查信号屏蔽与接地，排查管路中的气泡或脉动。",
    "spike": "{label} 读数有突跳，检查信号线接触与干扰源。",
    "simulation": "试验数据与仿真结果偏差较大，核对仿真模型参数（转速、阀开度）与实际工况是否一致。",
}

_FAULT_NAME = {
    "redundancy": "流量计读数偏离", "sensor": "传感器故障", "balance": "供回油流量不平衡",
    "mass_volume": "质量-体积流量不一致", "zero": "零点偏移", "noise": "读数波动过大", "spike": "读数毛刺",
    "simulation": "与仿真偏差较大",
}


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
    return rows


def build_report_body(analysis: Dict, simulation: Optional[Dict] = None,
                      baseline: Optional[Dict] = None) -> Dict:
    findings = list(analysis["findings"])
    if simulation:
        findings += _simulation_findings(simulation)
    findings.sort(key=lambda f: -SEVERITY_RANK[f["severity"]])
    decisive = [f for f in findings if SEVERITY_RANK[f["severity"]] >= SEVERITY_RANK[WARNING]]
    active = [lp for lp in analysis["loops"] if lp["active"]]

    if any(f["severity"] == ABNORMAL for f in decisive):
        result = RESULT_ABNORMAL
    elif decisive:
        result = RESULT_WARNING
    elif not active or not any(lp.get("checked") for lp in active):
        result = RESULT_INCONCLUSIVE
    else:
        result = RESULT_NORMAL

    if decisive:
        names = list(dict.fromkeys(_FAULT_NAME.get(f["category"], f["title"]) for f in decisive))
        locations = list(dict.fromkeys(f["label"] for f in decisive if f["label"]))
        fault_name, location = "、".join(names), "、".join(locations[:6])
        analysis_text = "\n".join(f"[{ck.SEVERITY_TEXT[f['severity']]}] {f['detail']}" for f in decisive)
        advice = list(dict.fromkeys(_ADVICE.get(f["category"], "").format(label=f["label"]) for f in decisive))
        summary = f"{'异常' if result == RESULT_ABNORMAL else '预警'}：{fault_name}（{location}）"
    elif result == RESULT_INCONCLUSIVE and not active:
        fault_name, location = "无法判定", "—"
        analysis_text = "所有管路都没有流量，无法诊断流量计。"
        advice = ["在有流量的稳定工况下重新采集数据后再诊断。"]
        summary = "无法判定：没有流量"
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
        **({"simulation": simulation} if simulation else {}),
    }


def _loop_summary(loop: Dict) -> Dict:
    """供前端展示的管路摘要（只保留可序列化的字段）。"""
    keep = ("column", "label", "group", "component", "mean", "deviation", "bias", "corrected", "warn", "alarm",
            "severity", "cv", "stuck")
    out = {"name": loop["name"], "active": loop["active"], "consensus": loop.get("consensus"),
           "meters": [{k: m[k] for k in keep if k in m} for m in loop["meters"]]}
    for key in ("balance", "mass", "legacy"):
        if loop.get(key):
            out[key] = loop[key]
    return out


def diagnose_frame(df: pd.DataFrame, density: Optional[float] = None, simulation: Optional[Dict] = None,
                   baseline: Optional[Dict] = None, cfg: Optional[Dict] = None) -> Dict:
    cfg = cfg or load_config()
    return build_report_body(analyze(df, cfg, baseline, density), simulation, baseline)


def diagnose_file(path: Path, density: Optional[float] = None, simulation: Optional[Dict] = None) -> Dict:
    from pump_test_bench.app.diagnosis.baseline import load_baseline  # 避免循环导入
    _, df = read_table(path)
    return diagnose_frame(df, density, simulation, load_baseline())
