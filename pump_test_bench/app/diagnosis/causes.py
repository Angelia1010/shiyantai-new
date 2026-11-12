"""原因推断：把各项检查发现的“现象”归并为最可能的“故障原因”。

一个故障通常同时触发好几项检查（例如逐渐扩大的泄漏 = 供回油不平衡 + 两只回油表偏差都在变化），
报告如果只罗列现象，读者要自己推理。这里按物理关系把现象归到原因上，每个原因给出：
名称、严重程度、位置、判断依据（对应的发现）、其他可能的解释、处理建议。

规则按“证据最直接”的顺序匹配，已被归因的发现不再参与后面的规则；最后剩下的发现各自成为一个原因。
"""
from typing import Dict, List, Optional

from pump_test_bench.app.diagnosis.checks import ABNORMAL, NOTICE, SEVERITY_RANK, WARNING

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


def _meter_groups(loops: List[Dict]) -> Dict[str, str]:
    return {m["column"]: m.get("group", "") for lp in loops for m in lp.get("meters", [])}


def infer_causes(findings: List[Dict], loops: List[Dict]) -> List[Dict]:
    pool = [f for f in findings if f["severity"] in DECISIVE]
    group = _meter_groups(loops)
    causes: List[Dict] = []

    def take(pred) -> List[Dict]:
        hit = [f for f in pool if pred(f)]
        for f in hit:
            pool.remove(f)
        return hit

    # 1) 传感器本身坏了（掉零、冻结、卡死、无数据）：最直接的证据，同一测点的其他现象都是它的后果
    for f in [f for f in pool if f["category"] in ("dropout", "frozen", "sensor")]:
        if f not in pool:
            continue
        items = take(lambda x, t=f["target"]: x["target"] == t)
        cat = f["category"]
        if cat == "dropout":
            name, why = "流量计信号中断", "读数在有流量时跌到 0，说明脉冲信号没有到达采集系统"
        elif cat == "frozen" or "卡死" in f["title"]:
            name, why = "流量计读数冻结", "读数长时间完全不变，而其他流量计正常变化，说明该表或其采集通道停止更新"
        else:
            name, why = "传感器故障", "读数超出物理上可能的范围或没有有效数据"
        alt = ["采集卡该通道故障（可把信号线换到备用通道确认）"] if cat in ("dropout", "frozen") else []
        causes.append(_cause(f"{f['label']} {name}", items, why,
                             "检查信号线与接插件、变送器供电；停机后检查叶轮能否自由转动。", alternatives=alt))

    # 2) 回油比供油多：只能是回油侧“多计”了，最常见的是夹气
    air = take(lambda x: x["category"] == "aeration")
    if air:
        extra = take(lambda x: x["category"] == "mass_volume" or
                     (x["category"] in ("noise", "spike", "trend") and group.get(x["target"]) == "回油"))
        noisy = any(x["category"] in ("noise", "spike") for x in extra)
        mass_low = any(x["category"] == "mass_volume" and (x.get("value") or 0) < 0 for x in extra)
        why = "回油流量计读数比供油多，泄漏不可能造成这种结果；涡轮流量计会把气泡体积也计入"
        if mass_low:
            why += "，同时科氏质量流量计偏低（两相流下测量管与流体解耦），符合夹气特征"
        if noisy:
            why += "，回油侧读数抖动也是气泡的典型表现"
        causes.append(_cause("回油夹气/气穴", air + extra, why,
                             "检查回油管路接头密封、油箱液位与回油背压，排气后复测。",
                             location=air[0]["label"], component="回油管路",
                             alternatives=["供油侧流量计整体偏低（若回油侧读数平稳、质量流量计正常，更可能是这种）"]))

    # 3) 供油比回油多：泄漏，或两只回油表同时偏低。用质量流量计（也在回油侧）区分
    leak = take(lambda x: x["category"] == "balance")
    if leak:
        trend = take(lambda x: x["category"] == "trend" and (group.get(x["target"]) == "回油" or x["target"] == leak[0]["target"]))
        mass = take(lambda x: x["category"] == "mass_volume")
        mass_high = any((x.get("value") or 0) > 0 for x in mass)
        if mass_high:
            causes.append(_cause(
                "两只回油流量计同时偏低", leak + trend + mass,
                "供油比回油多，但同在回油侧的质量流量计比回油流量计高，说明油实际回来了，是回油流量计少计",
                "对两只回油流量计做校准，检查是否有共同原因（同一批次磨损、同一油滤堵塞后的杂质冲刷）。",
                location="回油流量计", component="回油管路", alternatives=["泄漏，同时质量流量计偏高（两处同时故障，可能性小）"]))
        else:
            growing = bool(trend)
            why = "供油侧各流量计彼此一致、回油侧各流量计彼此一致，两侧整体相差一个比例"
            if mass:
                why += "；质量流量计也有偏差，需结合质量-体积校核判断"
            else:
                why += "；回油侧的质量流量计与回油流量计一致，支持油确实没有全部回来"
            if growing:
                why += "；且差值在测试过程中持续扩大"
            causes.append(_cause(
                "供回油之间泄漏" + ("（正在扩大）" if growing else ""), leak + trend + mass, why,
                "检查供油流量计之后、回油流量计之前的接头、密封与旁通阀，确认被试件是否内漏。"
                + ("泄漏在扩大，建议尽快停机。" if growing else ""),
                location=leak[0]["label"], component="回油管路",
                alternatives=["两只回油流量计和质量流量计同时偏低（三只表同向漂移，可能性小）"]))

    # 4) 单只流量计偏离（K 系数漂移），合并同一表的渐变、噪声、毛刺
    for f in [f for f in pool if f["category"] == "redundancy"]:
        if f not in pool:
            continue
        items = take(lambda x, t=f["target"]: x["target"] == t)
        low = (f.get("value") or 0) < 0
        growing = any(x["category"] == "trend" for x in items)
        jitter = any(x["category"] in ("noise", "spike") for x in items)
        if low:
            why = "该表比其余流量计的中位数偏低，而其余各表彼此一致；涡轮流量计偏低常见于叶片/轴承磨损（叶轮打滑）或轴承阻滞"
            alt = ["轴承阻滞（若小流量工况下偏低更明显，更可能是这种）"]
        else:
            why = "该表比其余流量计的中位数偏高，而其余各表彼此一致；涡轮流量计偏高常见于管壁沉积使流道变窄、流速变快"
            alt = ["前后直管段不足或整流器损坏引起旋流"]
        if growing:
            why += "；偏差在测试过程中持续变化，故障正在发展"
        if jitter:
            why += "；读数同时有抖动或毛刺，轴承损坏的可能性更大"
        causes.append(_cause(f"{f['label']} 计量偏差" + ("（正在发展）" if growing else ""), items, why,
                             f"对 {f['label']} 进行校准或更换；处理前可暂以其他流量计读数为准。", alternatives=alt))

    # 5) 质量流量计与体积流量不一致（各体积流量计互校正常）
    mv = take(lambda x: x["category"] == "mass_volume")
    if mv:
        f = mv[0]
        why = ("体积流量计之间互相一致，只有质量流量换算成体积后对不上。零点漂移在小流量时百分比更大，"
               "标定漂移在各流量下百分比相同——在任务列表“诊断趋势”中比较不同流量工况的偏差可以区分")
        fuel = next((x for x in findings if x["category"] == "fuel"), None)
        if fuel:
            why += (f"。注意：设置的燃油密度与建立健康基准时的油品相差 {fuel['value']:+.1f}%，"
                    "请先确认密度设置是否正确（单位 kg/m³，20 ℃）")
        causes.append(_cause(
            f"{f['label']} 零点或标定漂移", mv, why,
            f"对 {f['label']} 做零点校准（停流、充满油）；零点正常则送检标定。",
            alternatives=["燃油密度设置有误（换了油品但没有更新 20 ℃ 密度）", "油温传感器偏差（会带偏密度修正）"]))

    # 6) 其余：按测点归并
    names = {"noise": "读数波动过大", "spike": "读数毛刺", "trend": "偏差持续变化", "temperature": "温度传感器偏差",
             "zero": "零点偏移", "simulation": "与仿真偏差较大"}
    advice = {"noise": "检查信号屏蔽与接地，远离变频器/加热器动力线。",
              "spike": "检查接插件是否松动、前置放大器触发门限。",
              "trend": "故障可能正在发展，建议尽快停机检查。",
              "temperature": "用标准温度计比对两只传感器，检查安装深度与接线。",
              "zero": "在停流状态下做零点校准。",
              "simulation": "核对仿真模型参数（转速、阀开度）与实际工况是否一致。"}
    signal = ("noise", "spike")
    while pool:
        f = pool[0]
        if f["category"] in signal:  # 同一测点的抖动与毛刺是同一类信号问题，合并
            items = take(lambda x, t=f["target"]: x["target"] == t and x["category"] in signal)
            if any(x["category"] == "spike" for x in items):
                f = next(x for x in items if x["category"] == "spike")
        else:
            items = take(lambda x, t=f["target"], c=f["category"]: x["target"] == t and x["category"] == c)
        why = {"noise": "读数均值正常但短时抖动明显变大，常见于电磁干扰、接地不良",
               "spike": "偶发读数突跳（多为向下），常见于接触不良、触发门限偏高导致的脉冲丢失",
               "temperature": "同一位置的两只温度传感器读数相差过大，至少一只有偏差"}.get(f["category"], f["detail"])
        causes.append(_cause(f"{f['label']} {names.get(f['category'], f['title'])}", items, why,
                             advice.get(f["category"], "检查该测点。")))

    causes.sort(key=lambda c: -SEVERITY_RANK[c["severity"]])
    return causes


def notices(findings: List[Dict]) -> List[Dict]:
    return [f for f in findings if f["severity"] == NOTICE]
