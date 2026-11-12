"""内置数学公式模型。每个公式：输入 {输入名: 值} → 输出 {输出名: 值}。"""
from typing import Callable, Dict

from pump_test_bench.app.core import flow_meter


def turbine_meter(cond: Dict[str, float]) -> Dict[str, float]:
    """涡轮流量计：质量流量（kg/h）、燃油密度（kg/m³）→ 涡轮转速 → 叶片频率 → 理论体积流量（L/h）。"""
    speed = flow_meter.simulated_speed(cond["质量流量"] / 3600.0, cond["燃油密度"])
    if speed <= 0:  # 质量流量太小，超出公式适用范围
        return {}
    return {"理论体积流量": flow_meter.theoretical_flow(speed), "涡轮转速": speed}


FORMULAS: Dict[str, Callable[[Dict[str, float]], Dict[str, float]]] = {
    "turbine_meter": turbine_meter,
}
