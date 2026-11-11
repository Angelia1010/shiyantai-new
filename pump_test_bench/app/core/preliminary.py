"""仿真对比：比较试验数据与 AMESim 仿真数据（作为诊断的辅助证据）。

对两边都有的每个变量比较均值：
- 一般变量看相对偏差，超过阈值 threshold（默认 15%）为超限；
- 接近 0 的变量（如回油压力约 0.05 MPa）相对偏差没有意义，改看绝对偏差是否超过该类变量的容差；
超限变量数大于 exceeded_limit 时认为与仿真偏差较大。
"""
from typing import Dict, Iterable, List, Mapping, Optional

DEFAULT_THRESHOLD = 0.15
DEFAULT_EXCEEDED_LIMIT = 3
# 变量类型 → (接近 0 的判断界限, 绝对容差, 单位)
ABS_TOLERANCE = {
    "压力": (0.1, 0.02, "MPa"),
    "流量": (10.0, 5.0, "L/h"),
    "温度": (5.0, 2.0, "℃"),
    "转速": (50.0, 20.0, "rpm"),
}


def _mean(values: Iterable) -> Optional[float]:
    nums = []
    for v in values or []:
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)) and v == v:  # 排除 NaN
            nums.append(float(v))
    return sum(nums) / len(nums) if nums else None


def _tolerance(name: str):
    for key, tol in ABS_TOLERANCE.items():
        if key in name:
            return tol
    return None


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
        diff = abs(sim_avg - exp_avg)
        tol = _tolerance(name)
        if tol and abs(exp_avg) < tol[0]:
            exceeded, deviation, text = diff > tol[1], diff, f"{diff:.4g} {tol[2]}（绝对，容差 {tol[1]}）"
        else:
            deviation = diff / abs(exp_avg) if abs(exp_avg) > 1e-9 else diff
            exceeded, text = deviation > thr, f"{deviation * 100:.1f}%"
        details.append({
            "variable": name,
            "experiment_avg": round(exp_avg, 6),
            "simulation_avg": round(sim_avg, 6),
            "deviation": round(deviation, 6),
            "deviation_text": text,
            "exceeded": exceeded,
        })

    exceeded = sum(1 for d in details if d["exceeded"])
    abnormal = exceeded > limit
    conclusion = (
        f"与 AMESim 仿真对比 {len(details)} 个变量，{exceeded} 个超限"
        f"（相对阈值 {thr * 100:.0f}%，接近 0 的变量按绝对容差；允许超限 {limit} 个）"
        + ("，偏差较大。" if abnormal else "，与仿真基本一致。")
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
