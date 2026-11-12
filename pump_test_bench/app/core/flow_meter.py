"""涡轮流量计数学公式（仿真模型“涡轮流量计模型”的引擎，见 app/simulation/formulas.py）。

模型：质量流量 X1（kg/s）与密度 X2（kg/m³）→ 仿真涡轮转速
    Y = 2696.17 + 15468.63·X1 − 3.42·X2（rad/s）
→ 叶片频率 f = N·Y/(2π)，N = 6 → 理论流量 q = 0.304921·f + 0.210230（L/h）。

用 2026-11 实测数据核对：配对正确的质量流量计、按油温修正密度后，理论流量与实测
相差 −3.5%～+5%，且随流量、密度有规律地变化；涡轮流量计模型用正常数据标定这部分固有偏差后，
各表剩余离散约 1.1–1.5%（留一组交叉验证）。
Y ≤ 0（质量流量太小）时超出模型适用范围。
"""
import math

TURBINE_BLADES = 6


def simulated_speed(mass_flow_kg_s: float, density: float) -> float:
    """仿真转速模型，返回 rad/s。"""
    return 2696.17 + 15468.63 * mass_flow_kg_s - 3.42 * density


def theoretical_flow(speed_rad_s: float) -> float:
    """由涡轮转速计算理论体积流量（L/h）。"""
    frequency_hz = TURBINE_BLADES * speed_rad_s / (2 * math.pi)
    return 0.304921 * frequency_hz + 0.210230
