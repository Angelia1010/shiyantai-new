"""初步诊断：比较试验数据与 AMESim 仿真数据。

对两边都有的每个变量，比较均值的相对偏差；超过阈值的变量数大于“超限数量”时
判定为异常，此时需要进一步做流量计精确诊断。
"""
from typing import Dict, Iterable, List, Mapping, Optional

DEFAULT_THRESHOLD = 0.15
DEFAULT_EXCEEDED_LIMIT = 3


def _mean(values: Iterable) -> Optional[float]:
    nums = []
    for v in values or []:
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)) and v == v:  # 排除 NaN
            nums.append(float(v))
    return sum(nums) / len(nums) if nums else None


def compare(
    experiment: Mapping[str, List[float]],
    simulation: Mapping[str, List[float]],
    threshold: Optional[float] = None,
    exceeded_limit: Optional[int] = None,
) -> Dict:
    """experiment / simulation 均为 {变量名: [数值, ...]}。"""
    if not isinstance(experiment, Mapping) or not isinstance(simulation, Mapping):
        raise ValueError("experiment_data 与 simulation_data 必须是 {变量名: 数值数组} 格式")
    thr = DEFAULT_THRESHOLD if threshold is None else float(threshold)
    limit = DEFAULT_EXCEEDED_LIMIT if exceeded_limit is None else int(exceeded_limit)
    if thr <= 0:
        raise ValueError("threshold 必须大于 0")

    details = []
    for name in simulation:
        exp_avg = _mean(experiment.get(name))
        sim_avg = _mean(simulation.get(name))
        if exp_avg is None or sim_avg is None:
            continue
        base = abs(exp_avg)
        deviation = abs(sim_avg - exp_avg) / base if base > 1e-9 else abs(sim_avg - exp_avg)
        details.append({
            "variable": name,
            "experiment_avg": round(exp_avg, 6),
            "simulation_avg": round(sim_avg, 6),
            "deviation": round(deviation, 6),
            "exceeded": deviation > thr,
        })

    exceeded = sum(1 for d in details if d["exceeded"])
    abnormal = exceeded > limit
    conclusion = (
        f"共对比 {len(details)} 个变量，{exceeded} 个偏差超过阈值 {thr * 100:.1f}%"
        f"（允许超限 {limit} 个）。"
        + ("系统存在异常，需要执行精确诊断。" if abnormal else "系统状态正常。")
    )
    return {
        "is_abnormal": abnormal,
        "exceeded_count": exceeded,
        "total_compared": len(details),
        "exceeded_limit": limit,
        "threshold": thr,
        "details": details,
        "conclusion": conclusion,
    }


def normal_report_body(prelim: Dict) -> Dict:
    """初步诊断正常时生成的报告主体，格式与精确诊断一致。"""
    indicators = [
        {
            "name": f"{d['variable']}（偏差）",
            "reference": f"阈值 ±{prelim['threshold'] * 100:.1f}%",
            "value": f"{d['deviation'] * 100:.2f}%",
            "abnormal": d["exceeded"],
        }
        for d in prelim["details"]
    ]
    indicators.append({
        "name": "超限变量数",
        "reference": f"≤{prelim['exceeded_limit']}",
        "value": str(prelim["exceeded_count"]),
    })
    lines = [
        f"{'⚠' if d['exceeded'] else '✓'} {d['variable']}：试验均值={d['experiment_avg']:.4f}，"
        f"仿真均值={d['simulation_avg']:.4f}，偏差={d['deviation'] * 100:.2f}%"
        for d in prelim["details"]
    ]
    return {
        "result": "normal",
        "indicators": indicators,
        "diagnosis": {
            "fault_name": "初步诊断正常",
            "location": f"超限变量 {prelim['exceeded_count']}/{prelim['total_compared']}",
            "analysis": prelim["conclusion"],
        },
        "repair_advice": "【初步诊断结果】\n" + prelim["conclusion"] + "\n\n" + "\n".join(lines)
                         + "\n\n无需进一步精确诊断。",
    }
