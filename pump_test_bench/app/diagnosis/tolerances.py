"""随工况平滑变化的固有偏差模型的输入特征（健康基准中两只流量计的固有差异、涡轮流量计模型的固有偏差共用）。

    偏差 = c0 + c1·(Q/100) + c2·(T/10) + c3·(Q/100)·(T/10)        （Q：流量 L/h，T：油温 ℃）
"""
from typing import Dict, List


def features(flow: float, temperature: float, ranges: Dict) -> List[float]:
    """超出建基准时的范围就截断，避免外推。"""
    q = min(max(flow, ranges["flow"][0]), ranges["flow"][1]) / 100
    t = min(max(temperature, ranges["temperature"][0]), ranges["temperature"][1]) / 10
    return [1.0, q, t, q * t]
