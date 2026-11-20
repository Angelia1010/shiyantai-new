"""原因推断：把各项检查发现的“现象”归并为最可能的“故障原因”。

一个故障通常同时触发好几项检查（例如中途突发的流量计偏差 = 计量偏差 + 偏差突然变化）。这里按物理关系
把现象归到原因上，每个原因给出：名称、严重程度、位置、判断依据、可能性、其他可能、处理建议。

规则按“证据最直接”的顺序匹配，已被归因的发现不再参与后面的规则：
1. 传感器本身坏了（掉零、冻结、卡死、超量程、无数据）；
2. 故障隔离给出的原因（flow_diagnosis.py）：它已在各种解释中比较过，直接给出原因、可能性与其他解释，
   涡轮流量计二级诊断的结果写进依据；
3. 分段检查（供油段压差、温升）：按偏离方向列出几种可能；
4. 其余现象（两只流量计不一致、P1 偏离设定、波动、毛刺、未解释的变化）按测点归并。
"""
from typing import Dict, List, Optional

from pump_test_bench.app.diagnosis import hypotheses as hy
from pump_test_bench.app.diagnosis.checks import ABNORMAL, NOTICE, SEVERITY_RANK, WARNING
from pump_test_bench.app.diagnosis.sensor_checks import KIND_NAME

DECISIVE = (WARNING, ABNORMAL)


def _worst(items: List[Dict]) -> str:
    return max((f["severity"] for f in items), key=lambda s: SEVERITY_RANK[s])


def _cause(name: str, items: List[Dict], explanation: str, advice: str, location: str = "",
           component: Optional[str] = None, alternatives: Optional[List[str]] = None, target: str = "") -> Dict:
    return {
        "name": name, "severity": _worst(items), "location": location or (items[0].get("label") or ""),
        "target": target or items[0].get("target") or "", "component": component or items[0].get("component"),
        "explanation": explanation, "evidence": [f"{f['title']}：{f['detail']}" for f in items],
        "alternatives": alternatives or [], "advice": advice,
    }


# --------------------------------------------------------------------------- 1) 传感器损坏
def _sensor_cause(f: Dict, items: List[Dict], kinds: Dict[str, str]) -> Dict:
    kind = KIND_NAME.get(kinds.get(f["target"], ""), "传感器")
    cat = f["category"]
    if cat == "dropout":
        name, why = f"{kind}信号中断", "读数在有流量时跌到 0，说明脉冲信号没有到达采集系统"
    elif cat == "frozen" or "卡死" in f["title"]:
        name, why = f"{kind}读数冻结", "读数长时间完全不变，而其他信号正常变化，说明该传感器或其采集通道停止更新"
    elif "超出" in f["title"]:
        name, why = f"{kind}故障", "读数超出物理上可能的范围，常见于断线（4–20 mA 回路开路）、热电阻断路或量程设置错误"
    else:
        name, why = f"{kind}无有效数据", "稳定段内没有有效读数"
    advice = "检查信号线与接插件、变送器供电" + ("；停机后检查叶轮能否自由转动。" if kind == "流量计" else "。")
    alt = ["采集卡该通道故障（可把信号线换到备用通道确认）"]
    return _cause(f"{f['label']} {name}", items, why + "。该信号已不参与其他判断", advice, alternatives=alt)


# --------------------------------------------------------------------------- 2) 故障隔离给出的原因
_SUFFIX = {"ramp": {hy.LEAK: "（正在扩大）", "default": "（正在发展）"}, "step": {"default": "（中途突变）"}}


def _alternatives(fault: Dict, physical: List[str]) -> List[str]:
    data = [f"{a['text']}（可能性约 {a['probability'] * 100:.0f}%）" for a in fault.get("alternatives", [])]
    return data + physical


def _turbine_text(fault: Dict) -> str:
    out = []
    for t in fault.get("turbine") or []:
        if not t.get("available"):
            out.append(f"涡轮流量计模型复核 {t['label']}：无法判断（{t.get('note', '')}）")
            continue
        out.append(f"涡轮流量计模型复核 {t['label']}：按回油质量流量与油温，叶轮转速应为 {t['expected_hz']:.1f} Hz，"
                   f"实测 {t['measured_hz']:.1f} Hz（{t['residual'] * 100:+.2f}%），{t.get('verdict', '')}“该表偏离”的判断"
                   f"（可能性 {t['probability_before'] * 100:.0f}% → {t.get('probability_after', 0) * 100:.0f}%）")
    return "；".join(out)


def _isolated_cause(f: Dict, items: List[Dict]) -> Dict:
    fault = f["fault"]
    kind, v, label = fault["kind"], (f.get("value") or 0.0) / 100, f["label"]
    change = fault.get("change") or {}
    suffix = _SUFFIX.get(change.get("kind"), {})
    suffix = suffix.get(kind, suffix.get("default", ""))
    jitter = any(x["category"] in ("noise", "spike") for x in items)
    if kind == hy.METER:
        name = f"{label} 计量偏差"
        if v < 0:
            why = "该表比其余信号推算的实际流量偏低；涡轮流量计偏低常见于叶片/轴承磨损（叶轮打滑）或轴承阻滞"
            alt = ["轴承阻滞（若小流量工况下偏低更明显，更可能是这种）"]
        else:
            why = "该表比其余信号推算的实际流量偏高；涡轮流量计偏高常见于管壁沉积使流道变窄、流速变快"
            alt = ["前后直管段不足或整流器损坏引起旋流"]
        if jitter:
            why += "；读数同时有抖动或毛刺，轴承损坏的可能性更大"
        advice = f"对 {label} 进行校准或更换；处理前可暂以另一只流量计的读数为准。"
    elif kind == hy.FLOW_CHANGE:
        low = v > 0   # 锚点偏离为正：实际流量低于模型预期
        name = "被试泵出力低于预期" if low else "实际流量高于预期"
        why = ("两只流量计彼此一致，随流量变化的 P5、P6 也同步变化，说明实际流量确实"
               + ("减少" if low else "增加") + "，而不是某只表的问题")
        alt = (["电传转速信号偏高（转速按显示值控制，实际转速偏低）", "进口供油不足或吸入不畅"] if low
               else ["电传转速信号偏低", "仿真模型与当前设备状态不符（检修后未重建模型）"])
        advice = ("检查被试泵容积效率（内泄漏、配流面磨损），用独立的转速表核对电传转速；可在相同工况下复测确认。" if low
                  else "核对电传转速信号；设备检修后请重建仿真模型。")
        label = "被试泵/电传"
    elif kind == hy.LEAK:
        name = "供回油之间泄漏"
        why = "供油流量与模型预期一致，回油流量和随回油流量变化的 P5、P6 一起偏低，说明油确实没有全部回来"
        alt = []
        advice = "检查供油流量计之后、回油流量计之前的接头、密封与旁通阀，确认被试件是否内漏。"
        if change.get("kind") == "ramp":
            advice += "泄漏在扩大，建议尽快停机。"
        label = "主油路"
    elif kind == hy.METERS_COMMON:
        name = f"两只流量计同时{'偏高' if v > 0 else '偏低'}"
        why = "两只流量计一致地偏离预期，而随流量变化的 P5、P6 与预期一致，实际流量没有变，是两只流量计共同的测量偏差"
        alt = ["油品粘度与标定时不同（涡轮流量计系数随粘度变化）", "被试泵出力变化，同时 P5、P6 传感器也有偏差（可能性小）"]
        advice = "核对当前油品与流量计标定条件；对两只流量计做校准，检查是否有共同原因（同一批次、同一采集模块）。"
    elif kind == hy.RETURN_RESISTANCE:
        name = "回油管路阻力增大"
        why = "两只流量计正常（流量没变），P5、P6 同时升高，说明被试泵出口到油箱之间的阻力增大"
        alt = ["P5、P6 两只压力传感器同时偏高（可能性小）"]
        advice = "检查回油滤网、回油流量计、阀门开度，清洗或更换滤芯。"
        label = "回油管路"
    else:  # pressure_sensor
        name = f"{label} 传感器偏差"
        why = "该压力与相邻的压力、两只流量计都对不上，而其他信号彼此一致，更可能是该传感器零点或量程漂移"
        alt = ["该处局部阻力变化（阀门、接头）"]
        advice = f"用标准压力表比对 {label}，停机泄压后检查零点。"
    turbine = _turbine_text(fault)
    if turbine:
        why += "。" + turbine
    if change.get("kind") == "ramp":
        why += f"；偏差从第 {change['onset_s']:.0f} 秒起持续变化，故障正在发展"
    elif change.get("kind") == "step":
        why += f"；偏差在第 {change['onset_s']:.0f} 秒突然出现，结论按变化后的数据给出"
    cause = _cause(name + suffix, items, why, advice, alternatives=_alternatives(fault, alt),
                   location=label, component=f.get("component"), target=f["target"])
    cause["confidence"] = fault.get("probability")
    cause["kind"] = kind
    return cause


def _related_to(f: Dict):
    """与一个隔离出的原因属于同一对象的其他现象：同一信号/管路的变化、同一表的噪声与毛刺。"""
    target = f["target"]
    keys = set(f["fault"].get("keys", []))

    def pred(x: Dict) -> bool:
        if x is f:
            return True
        return x["category"] in ("trend", "noise", "spike") and (x["target"] == target or x["target"] in keys)
    return pred


# --------------------------------------------------------------------------- 3) 分段检查
def _section_cause(f: Dict) -> Dict:
    hyps = f.get("hypotheses") or [f["title"]]
    if f["category"] == "supply_drop":
        name = "供油段压差异常"
        advice = ("用标准压力表比对 P9、P1；检查供油滤网与供油流量计前后是否堵塞。在不同流量下复测："
                  "偏差随流量变大更像堵塞，各流量相同更像传感器零点漂移。")
    else:
        name = "温升异常"
        advice = "用标准温度计比对供油温度1-2、回油温度1-1；两只温度都正常时检查被试泵效率（内泄漏）。"
    return _cause(name, [f], f"最可能：{hyps[0]}。" + f["detail"].split("。可能：")[0], advice,
                  alternatives=hyps[1:])


# --------------------------------------------------------------------------- 入口
def infer_causes(findings: List[Dict], signals: Optional[List[Dict]] = None) -> List[Dict]:
    """signals：报告中的信号状态（用来给出传感器类型的名称）。"""
    pool = [f for f in findings if f["severity"] in DECISIVE]
    kinds = {s["column"]: s.get("kind", "") for s in signals or []}
    causes: List[Dict] = []

    def take(pred) -> List[Dict]:
        hit = [f for f in pool if pred(f)]
        for f in hit:
            pool.remove(f)
        return hit

    # 1) 传感器本身坏了：同一测点的其他现象都是它的后果
    for f in [f for f in pool if f["category"] in ("dropout", "frozen", "sensor")]:
        if f in pool:
            causes.append(_sensor_cause(f, take(lambda x, t=f["target"]: x["target"] == t), kinds))

    # 2) 故障隔离给出的原因
    for f in [f for f in pool if f.get("fault")]:
        if f in pool:
            causes.append(_isolated_cause(f, take(_related_to(f))))

    # 3) 分段检查
    for f in take(lambda x: x["category"] in ("supply_drop", "temperature_rise")):
        causes.append(_section_cause(f))

    # 4) 其余现象按测点归并
    names = {"noise": "读数波动过大", "spike": "读数毛刺", "trend": "偏差在测试中变化", "pair": "两只流量计不一致",
             "setpoint": "偏离设定值"}
    why = {"noise": "读数均值正常但短时抖动明显变大，常见于电磁干扰、接地不良",
           "spike": "偶发读数突跳，常见于接触不良、触发门限偏高导致的脉冲丢失",
           "pair": "两只流量计扣除健康时的固有差异后仍不一致；没有模型参照，分不清是哪一只、还是泄漏",
           "setpoint": "P1 由增压泵闭环控制，偏离设定档位说明控制不稳，或 P1 传感器偏差"}
    advice = {"noise": "检查信号屏蔽与接地，远离变频器/加热器动力线。",
              "spike": "检查接插件是否松动、前置放大器触发门限。",
              "trend": "故障可能正在发展或间歇出现，建议复测并关注诊断趋势。",
              "pair": "在“仿真模型”页面建立标准台系统模型后重新诊断，可以定位是哪只流量计或是否泄漏。",
              "setpoint": "检查增压泵控制回路；用标准压力表比对 P1。"}
    signal = ("noise", "spike")
    while pool:
        f = pool[0]
        if f["category"] in signal:  # 同一测点的抖动与毛刺是同一类信号问题，合并
            items = take(lambda x, t=f["target"]: x["target"] == t and x["category"] in signal)
            if any(x["category"] == "spike" for x in items):
                f = next(x for x in items if x["category"] == "spike")
        else:
            items = take(lambda x, t=f["target"], c=f["category"]: x["target"] == t and x["category"] == c)
        name = names["pair"] if f["category"] == "pair" else f"{f['label']} {names.get(f['category'], f['title'])}"
        causes.append(_cause(name, items, why.get(f["category"], f["detail"]), advice.get(f["category"], "检查该测点。"),
                             alternatives=["其中一只流量计计量偏差", "供回油之间泄漏"] if f["category"] == "pair" else None))

    causes.sort(key=lambda c: -SEVERITY_RANK[c["severity"]])
    return causes


def notices(findings: List[Dict]) -> List[Dict]:
    return [f for f in findings if f["severity"] == NOTICE]
