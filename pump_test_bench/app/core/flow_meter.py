"""涡轮流量计诊断（“精确诊断”）。

对每个回路：
1. 取回油质量流量的均值，单位由 kg/h 换算为 kg/s，记为 X1；
2. 介质密度 X2：优先使用调用方传入的值，其次使用文件中“介质密度”列的均值，都没有时取默认值；
3. 仿真转速模型：Y = 2696.17 + 15468.63·X1 − 3.42·X2（rad/s）；
4. 涡轮脉冲频率：f = N·Y / (2π)，N 为涡轮叶片数（6）；
5. 转速-流量标定曲线：q = 0.304921·f + 0.210230（L/h），即理论流量；
6. 理论流量与该回路实测流量均值的相对偏差超过阈值（15%）即判定该流量计异常。

注意：第 4 步原实现写成了 f = Y·2π/6，量纲不对，已按 f = 6·Y/(2π) 修正，
修正后理论流量比原实现低约 9%。
"""
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from pump_test_bench.app.core.data_reader import find_column, iter_excel_sheets, read_table

DEVIATION_THRESHOLD = 0.15
DEFAULT_DENSITY = 820.0          # kg/m³，航空燃油典型密度
KG_PER_HOUR_TO_KG_PER_SECOND = 1 / 3600.0
TURBINE_BLADES = 6
DENSITY_COLUMN = "介质密度"


@dataclass(frozen=True)
class FlowMeter:
    name: str
    mass_flow_column: str   # 质量流量列（kg/h）
    flow_column: str        # 实测体积流量列（L/h）


FLOW_METERS = (
    FlowMeter("回路1流量计", "回油质量流量1", "回油流量1-1"),
    FlowMeter("回路2流量计", "回油质量流量2", "回油流量1-2"),
)

RESULT_NORMAL = "normal"
RESULT_ABNORMAL = "abnormal"
RESULT_INCONCLUSIVE = "inconclusive"


def simulated_speed(mass_flow_kg_s: float, density: float) -> float:
    """仿真转速模型，返回 rad/s。"""
    return 2696.17 + 15468.63 * mass_flow_kg_s - 3.42 * density


def theoretical_flow(speed_rad_s: float) -> float:
    """由涡轮转速计算理论体积流量（L/h）。"""
    frequency_hz = TURBINE_BLADES * speed_rad_s / (2 * math.pi)
    return 0.304921 * frequency_hz + 0.210230


def relative_deviation(expected: float, actual: float) -> float:
    if abs(actual) < 1e-9:
        return abs(expected - actual)
    return abs(expected - actual) / abs(actual)


def _load_frame(path: Path) -> pd.DataFrame:
    """读取包含质量流量列的工作表（Excel 会依次查找所有工作表）。"""
    wanted = [m.mass_flow_column for m in FLOW_METERS]
    _, df = read_table(path)
    if any(find_column(list(df.columns), col) for col in wanted):
        return df
    if path.suffix.lower() in (".xlsx", ".xls"):
        for _, sheet_df in iter_excel_sheets(path):
            if any(find_column(list(sheet_df.columns), col) for col in wanted):
                return sheet_df
    raise ValueError(f"文件 {path.name} 中没有找到 {'、'.join(wanted)} 列，无法进行流量计诊断")


def _column_mean(df: pd.DataFrame, keyword: str) -> Optional[float]:
    col = find_column(list(df.columns), keyword)
    if col is None:
        return None
    values = pd.to_numeric(df[col], errors="coerce").dropna()
    return float(values.mean()) if len(values) else None


def _diagnose_meter(meter: FlowMeter, df: pd.DataFrame, density: float) -> Optional[Dict]:
    mass_flow_mean = _column_mean(df, meter.mass_flow_column)
    if mass_flow_mean is None:
        return None
    x1 = mass_flow_mean * KG_PER_HOUR_TO_KG_PER_SECOND
    speed = simulated_speed(x1, density)
    q_theory = theoretical_flow(speed)
    actual = _column_mean(df, meter.flow_column)

    indicators = [
        {"name": f"{meter.name} 质量流量均值", "reference": "输入值", "value": f"{x1:.6f} kg/s"},
        {"name": f"{meter.name} 仿真转速", "reference": "计算值", "value": f"{speed:.2f} rad/s"},
        {"name": f"{meter.name} 理论流量", "reference": "计算值", "value": f"{q_theory:.2f} L/h"},
    ]

    if actual is None:
        return {
            "name": meter.name,
            "result": RESULT_INCONCLUSIVE,
            "indicators": indicators,
            "analysis": f"{meter.name}：理论流量={q_theory:.2f} L/h，文件中缺少“{meter.flow_column}”列，无法对比。",
        }

    deviation = relative_deviation(q_theory, actual)
    abnormal = deviation > DEVIATION_THRESHOLD
    indicators += [
        {"name": f"{meter.name} 实际流量均值", "reference": "测量值", "value": f"{actual:.2f} L/h"},
        {
            "name": f"{meter.name} 流量偏差",
            "reference": f"阈值 {DEVIATION_THRESHOLD * 100:.1f}%",
            "value": f"{deviation * 100:.2f}%",
            "abnormal": abnormal,
        },
    ]
    verdict = "异常" if abnormal else "正常"
    return {
        "name": meter.name,
        "result": RESULT_ABNORMAL if abnormal else RESULT_NORMAL,
        "indicators": indicators,
        "analysis": (
            f"{meter.name}：质量流量均值={x1:.6f} kg/s，仿真转速={speed:.2f} rad/s，"
            f"理论流量={q_theory:.2f} L/h，实际流量={actual:.2f} L/h，"
            f"相对偏差={deviation * 100:.2f}%（阈值 {DEVIATION_THRESHOLD * 100:.1f}%），判定为{verdict}。"
        ),
    }


def diagnose_flow_meters(path: Path, density: Optional[float] = None) -> Dict:
    """对文件做流量计诊断，返回报告主体：{result, indicators, diagnosis, repair_advice}。"""
    df = _load_frame(path)
    if density is not None:
        density_source = "输入值"
    else:
        density = _column_mean(df, DENSITY_COLUMN)
        density_source = "文件"
        if density is None:
            density, density_source = DEFAULT_DENSITY, "默认值"

    meters = [m for m in (_diagnose_meter(meter, df, density) for meter in FLOW_METERS) if m]
    indicators: List[Dict] = [
        {"name": "介质密度", "reference": density_source, "value": f"{density:.1f} kg/m³"}
    ]
    for m in meters:
        indicators.extend(m["indicators"])

    abnormal = [m for m in meters if m["result"] == RESULT_ABNORMAL]
    inconclusive = [m for m in meters if m["result"] == RESULT_INCONCLUSIVE]
    if abnormal:
        result = RESULT_ABNORMAL
        diagnosis = {
            "fault_name": "涡轮流量计状态异常",
            "location": "、".join(m["name"] for m in abnormal),
            "analysis": "\n".join(m["analysis"] for m in abnormal),
        }
        advice_tail = "建议：对异常流量计进行校准或更换。"
    elif inconclusive:
        result = RESULT_INCONCLUSIVE
        diagnosis = {
            "fault_name": "部分流量计无法诊断",
            "location": "、".join(m["name"] for m in inconclusive),
            "analysis": "\n".join(m["analysis"] for m in meters),
        }
        advice_tail = "建议：补充缺失的实测流量数据后重新诊断。"
    else:
        result = RESULT_NORMAL
        diagnosis = {
            "fault_name": "涡轮流量计状态正常",
            "location": "、".join(m["name"] for m in meters),
            "analysis": "理论流量与实际流量偏差均在允许范围内。\n" + "\n".join(m["analysis"] for m in meters),
        }
        advice_tail = "无需处理。"

    repair_advice = "【流量计诊断结果】\n" + "\n".join(f"· {m['analysis']}" for m in meters) + f"\n\n{advice_tail}"
    return {"result": result, "indicators": indicators, "diagnosis": diagnosis, "repair_advice": repair_advice}
