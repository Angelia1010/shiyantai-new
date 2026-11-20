"""在正常（健康）数据上做故障注入，生成异常数据文件，并用诊断引擎逐个验证。

生成的文件与试验台原始文件格式完全一致（同编码、同表头、同分隔符、同时间列），
只改动被注入故障的那几列，可以直接放进数据目录做实时监控 / 自动诊断测试。

用法：
    python -m pump_test_bench.tools.generate_fault_data 健康数据目录 --out 输出目录
    python -m pump_test_bench.tools.generate_fault_data 健康数据目录 --out 输出目录 --no-diagnose

输出：
    输出目录/F01_涡轮磨损偏低/36-38℃_S4975-P0.15_明显5%.txt ...
    输出目录/故障清单.csv     （逐个文件：故障、机理、受影响测点与注入规律、预期诊断、实际诊断）
    输出目录/故障注入清单.md  （按类别整理的说明：主要测点、测点关系、每种故障的机理与注入规律）
"""
import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from pump_test_bench.app.core.table_parser import decode_bytes, parse_time

# 诊断用的 9 个信号（config/bench.json 的 signals），另加涡轮流量计二级诊断参照用的回油质量流量
SUPPLY, RETURN = "供油流量1-2", "回油流量1-2"
P9, P1, P5, P6 = "P9控制腔压力", "P1进口压力", "P5低压压力", "P6定压压力"
T_SUPPLY, T_RETURN, SPEED = "供油温度1-2", "回油温度1-1", "电传实际转速"
MASS = "回油质量流量2"
FLOWS = [SUPPLY, RETURN]

# ---------------------------------------------------------------------------
# 时间曲线：故障从什么时候、以什么方式出现。g(t) ∈ [0, 1]，1 表示故障完全出现
# ---------------------------------------------------------------------------


def profile(kind: str, t: np.ndarray, at: float = 0.4) -> np.ndarray:
    span = max(float(t[-1] - t[0]), 1e-9)
    x = (t - t[0]) / span
    if kind == "const":       # 整个文件都有故障（开机前就已存在）
        return np.ones_like(x)
    if kind == "step":        # 在 at 处突然出现（断线、卡死、零点跳变）
        return (x >= at).astype(float)
    if kind == "ramp":        # 从 0 线性发展到 1（磨损、渐进泄漏）
        return x
    raise ValueError(kind)


PROFILE_LABEL = {"const": "全程", "step": "中途突发", "ramp": "逐渐发展"}

# ---------------------------------------------------------------------------
# 测点之间的关系（由 60 个正常文件拟合，见输出目录的 故障注入清单.md）
#   被试泵是容积泵：流量由电传转速决定；P5、P6 ∝ Q^0.82（P6 在 P5 下游，两者只差约 0.001 MPa）
#   供油段：P9 − P1 ∝ Q^1.57（P1 由增压泵闭环控制在设定值）
#   回油质量流量计（涡轮流量计二级诊断的参照）测的是实际回油流量
# ---------------------------------------------------------------------------
OUTLET_EXP, SUPPLY_DROP_EXP = 0.82, 1.57
Cols = Dict[str, np.ndarray]


# ---------------------------------------------------------------------------
# 故障模型：f(列数据字典, g, rng, 参数) -> 修改后的列数据字典（只返回改动的列）
# ---------------------------------------------------------------------------
def k_factor(cols: Cols, g, rng, col: str, ratio: float) -> Cols:
    """涡轮流量计 K 系数漂移：读数按比例偏移。磨损 → 偏低，沉积/流道变窄 → 偏高。"""
    return {col: cols[col] * (1 + ratio * g)}


def k_factor_many(cols: Cols, g, rng, names: List[str], ratio: float) -> Cols:
    """几只流量计同时 K 系数漂移（油品粘度与标定时不同、同一批次磨损、同一采集模块）。"""
    return {c: cols[c] * (1 + ratio * g) for c in names}


def bearing_drag(cols: Cols, g, rng, col: str, loss: float, jitter: float = 0.01) -> Cols:
    """轴承阻滞：克服摩擦要消耗一部分流量，读数少一个固定量（L/h），小流量时百分比更大，并伴随转速抖动。"""
    v = cols[col]
    j = rng.normal(0, jitter, len(v)) * v
    return {col: np.maximum(v - loss * g + j * g, 0.0)}


def freeze(cols: Cols, g, rng, col: str) -> Cols:
    """叶轮卡滞 / 变送器死机：从故障时刻起读数冻结在当时的值。"""
    v = cols[col].copy()
    on = np.flatnonzero(g > 0.5)
    if len(on):
        v[on] = v[on[0]]
    return {col: v}


def drop_zero(cols: Cols, g, rng, col: str) -> Cols:
    """信号线断开 / 叶轮卡死不转：从故障时刻起读数为 0（带少量零点噪声）。"""
    v = cols[col].copy()
    on = g > 0.5
    v[on] = np.abs(rng.normal(0, 0.05, on.sum()))
    return {col: v}


def emi_noise(cols: Cols, g, rng, col: str, ratio: float) -> Cols:
    """电磁干扰 / 屏蔽接地不良：脉冲信号上叠加干扰，读数随机抖动。"""
    v = cols[col]
    return {col: v + rng.normal(0, ratio, len(v)) * float(np.nanmean(v)) * g}


def pulse_loss(cols: Cols, g, rng, col: str, ratio: float, depth: float = 0.5) -> Cols:
    """脉冲丢失：接插件松动、前置放大器门限偏高，偶发漏计脉冲 → 向下的毛刺。"""
    v = cols[col].copy()
    idx = np.flatnonzero(g > 0.5)
    hit = rng.choice(idx, max(1, int(len(idx) * ratio)), replace=False)
    v[hit] *= 1 - rng.uniform(0.15, depth, len(hit))
    return {col: v}


def _flow_pressures(cols: Cols, out: Cols, k) -> None:
    """流过回油管路的流量变为 k 倍：P5、P6 ∝ Q^0.82。"""
    for c in (P5, P6):
        if c in cols:
            out[c] = cols[c] * k ** OUTLET_EXP


def leak(cols: Cols, g, rng, ratio: float) -> Cols:
    """供油流量计之后、回油流量计之前泄漏（接头、密封外漏或被试件内漏旁通）：回油流量与回油质量流量
    同时少 ratio；流过回油管路的油少了，P5、P6 随之降低。供油流量、P9、P1 不变。"""
    k = 1 - ratio * g
    out = {c: cols[c] * k for c in (RETURN, MASS) if c in cols}
    _flow_pressures(cols, out, k)
    return out


def pump_wear(cols: Cols, g, rng, ratio: float) -> Cols:
    """被试泵容积效率下降（内泄漏增大、配流面磨损）：同一转速下实际流量减少 ratio。两只流量计、
    回油质量流量同比例减少，P5、P6 ∝ Q^0.82 降低，供油段压差 P9 − P1 ∝ Q^1.57 减小，电传转速不变。"""
    k = 1 - ratio * g
    out = {c: cols[c] * k for c in FLOWS + [MASS] if c in cols}
    _flow_pressures(cols, out, k)
    out[P9] = cols[P1] + (cols[P9] - cols[P1]) * k ** SUPPLY_DROP_EXP
    return out


def speed_signal_high(cols: Cols, g, rng, ratio: float) -> Cols:
    """电传转速信号偏高（测速齿盘/编码器标定错误）：转速按显示值闭环控制，实际转速比显示值低 ratio，
    被试泵实际流量随之减少 ratio，显示的转速不变。数据上的表现与被试泵出力下降相同。"""
    return pump_wear(cols, g, rng, ratio)


def return_resistance(cols: Cols, g, rng, dp: float) -> Cols:
    """回油管路（P6 之后到油箱，如回油滤网）堵塞：阻力增大，P5、P6 同时升高 dp（MPa）。
    被试泵是容积泵，流量基本不变。"""
    return {c: cols[c] + dp * g for c in (P5, P6)}


def supply_clog(cols: Cols, g, rng, dp: float) -> Cols:
    """供油段（P9 与 P1 之间：供油流量计、滤网、管路）堵塞：多出压降 dp。P1 由增压泵闭环控制仍保持设定值，
    增压泵出口压力（P9）升高 dp。流量由被试泵决定，不变。"""
    return {P9: cols[P9] + dp * g}


def inlet_sensor_drift(cols: Cols, g, rng, offset: float) -> Cols:
    """P1 进口压力传感器零点漂移（读数偏高 offset）：P1 是闭环控制的被控量，控制器把“读数”保持在设定值，
    实际进口压力被带低 offset，增压泵出口压力 P9 也随之降低 offset；P1 读数不变。"""
    return {P9: cols[P9] - offset * g}


def inlet_off_setpoint(cols: Cols, g, rng, offset: float) -> Cols:
    """增压泵控制偏差：实际进口压力偏离设定档位 offset（P1、P9 同时变化，P1 传感器正常）。"""
    return {P1: cols[P1] + offset * g, P9: cols[P9] + offset * g}


def pressure_offset(cols: Cols, g, rng, col: str, offset: float) -> Cols:
    """压力传感器零点漂移（膜片疲劳、温漂、过压）：读数多一个固定量（MPa），其余测点不变。"""
    return {col: cols[col] + offset * g}


def signal_open(cols: Cols, g, rng, col: str, value: float = -0.375) -> Cols:
    """压力变送器断线（4–20 mA 回路开路）：读数跌到量程下限以下的固定值（约 −0.375 MPa，
    与本批数据中 P13 燃油油箱压力 的表现一致）。"""
    v = cols[col].copy()
    v[g > 0.5] = value
    return {col: v}


def temp_offset(cols: Cols, g, rng, col: str, offset: float) -> Cols:
    """热电阻偏移（老化、接线电阻、未插到油里）：读数多一个固定量（℃）。"""
    return {col: cols[col] + offset * g}


def temp_open(cols: Cols, g, rng, col: str, value: float = 157.595) -> Cols:
    """热电阻断路：变送器输出满量程，读数固定在约 157.6 ℃（与本批数据中 T6/T7 的表现一致）。"""
    v = cols[col].copy()
    v[g > 0.5] = value
    return {col: v}


# ---------------------------------------------------------------------------
# 故障清单
# ---------------------------------------------------------------------------


@dataclass
class Fault:
    code: str
    folder: str
    name: str
    target: str
    fn: Callable
    kwargs: Dict
    profile: str
    severity: str
    expect: str                     # 期望诊断结论：normal / warning / abnormal
    expect_text: str
    conditions: Sequence[str] = field(default_factory=lambda: ("B",))
    at: float = 0.4
    expect_by: Dict[str, str] = field(default_factory=dict)   # 个别工况的预期结论不同时
    cols: Sequence[str] = ()                                   # 需要读取的列（默认按 col 参数）
    effect: str = ""                                           # 受影响的测点与注入规律（写入清单）
    group: str = ""                                            # 故障类别


# 代表性工况（健康源文件）：低温中流量 / 中温中流量 / 高温大流量 / 中温小流量
CONDITIONS = {
    "A": ("20261102数据（15-25摄氏度）", "S250-P0.10.txt", "16℃_S250-P0.10"),
    "B": ("36-38摄氏度", "S4975-P0.15.txt", "36℃_S4975-P0.15"),
    "C": ("45-50摄氏度", "S9980-P0.10.txt", "46℃_S9980-P0.10"),
    "D": ("27-30摄氏度", "S1295-P0.15.txt", "27℃_S1295-P0.15"),
}

SYSTEM_COLUMNS = FLOWS + [MASS, P1, P5, P6, P9]
G_METER, G_SYSTEM, G_PRESSURE, G_TEMP = "流量计", "系统与管路", "压力测点与控制回路", "温度测点"


def _k(col: str, ratio: float) -> str:
    return f"{col} 读数 × {1 + ratio:.3f}（{ratio * 100:+.1f}%），其余测点不变"


PUMP_EFFECT = ("两只流量计与回油质量流量 × {k}；P5、P6 × {k}^0.82；P9 − P1 × {k}^1.57；电传转速、P1、温度不变")

FAULTS: List[Fault] = [
    # ---------------------------------------------------------------- 一、流量计
    Fault("F01", "F01_涡轮磨损偏低", "回油流量计 K 系数漂移（叶片/轴承磨损，读数偏低）", RETURN, k_factor,
          {"col": RETURN, "ratio": -0.02}, "const", "轻微2%", "warning",
          "回油流量1-2 计量偏差（预警）", ("A", "B"), group=G_METER, effect=_k(RETURN, -0.02)),
    Fault("F01", "F01_涡轮磨损偏低", "回油流量计 K 系数漂移（叶片/轴承磨损，读数偏低）", RETURN, k_factor,
          {"col": RETURN, "ratio": -0.05}, "const", "明显5%", "abnormal",
          "回油流量1-2 计量偏差（异常）", ("C",), group=G_METER, effect=_k(RETURN, -0.05)),
    Fault("F02", "F02_涡轮沉积偏高", "供油流量计 K 系数漂移（沉积/流道变窄，读数偏高）", SUPPLY, k_factor,
          {"col": SUPPLY, "ratio": 0.04}, "const", "明显4%", "abnormal",
          "供油流量1-2 计量偏差（异常）", ("B",), group=G_METER, effect=_k(SUPPLY, 0.04)),
    Fault("F03", "F03_渐进磨损", "回油流量计渐进磨损（测试中由 0 发展到 −8%）", RETURN, k_factor,
          {"col": RETURN, "ratio": -0.08}, "ramp", "末端8%", "abnormal",
          "回油流量1-2 计量偏差（正在发展）", ("B",), group=G_METER,
          effect="回油流量1-2 读数 × (1 − 0.08·x)，x 为测试进度 0→1"),
    Fault("F04", "F04_轴承阻滞", "供油流量计轴承阻滞（少计固定流量，伴随抖动）", SUPPLY, bearing_drag,
          {"col": SUPPLY, "loss": 12.0}, "const", "少计12L/h", "abnormal",
          "小流量时供油流量1-2 偏离明显（异常），大流量时较小（预警）", ("D", "C"),
          expect_by={"C": "warning"}, group=G_METER, effect="供油流量1-2 读数 − 12 L/h，并叠加标准差 1% 的随机抖动"),
    Fault("F05", "F05_叶轮卡滞冻结", "流量计读数冻结（叶轮卡滞/变送器死机）", RETURN, freeze,
          {"col": RETURN}, "step", "40%处冻结", "abnormal",
          "回油流量1-2 读数冻结", ("B",), group=G_METER, effect="回油流量1-2 从故障时刻起保持当时的读数不变"),
    Fault("F06", "F06_断线归零", "流量计信号断线（读数归零）", SUPPLY, drop_zero,
          {"col": SUPPLY}, "step", "50%处断线", "abnormal",
          "供油流量1-2 信号中断", ("C",), 0.5, group=G_METER, effect="供油流量1-2 从故障时刻起读数为 0（±0.05 L/h 噪声）"),
    Fault("F07", "F07_电磁干扰", "电磁干扰/接地不良（读数随机抖动）", RETURN, emi_noise,
          {"col": RETURN, "ratio": 0.04}, "const", "抖动4%", "warning",
          "回油流量1-2 读数波动过大", ("A",), group=G_METER, effect="回油流量1-2 叠加标准差为均值 4% 的随机噪声，均值不变"),
    Fault("F08", "F08_脉冲丢失", "脉冲丢失（接插件松动，偶发漏计，向下毛刺）", SUPPLY, pulse_loss,
          {"col": SUPPLY, "ratio": 0.01}, "const", "1%点丢失", "warning",
          "供油流量1-2 读数毛刺", ("B",), group=G_METER, effect="供油流量1-2 随机 1% 的采样点读数下跌 15–50%"),
    Fault("F09", "F09_中途突发偏低", "回油流量计中途突然偏低（异物卡入/叶片损伤，−4%）", RETURN, k_factor,
          {"col": RETURN, "ratio": -0.04}, "step", "50%处突变4%", "abnormal",
          "回油流量1-2 计量偏差（中途突变），给出变化开始时刻", ("B",), 0.5, group=G_METER,
          effect="回油流量1-2 从测试 50% 处起读数 × 0.96"),
    Fault("F10", "F10_两只流量计同时偏低", "两只流量计同时偏低（油品粘度与标定时不同等共模因素，−3%）", "供油流量1-2、回油流量1-2",
          k_factor_many, {"names": FLOWS, "ratio": -0.03}, "const", "轻微3%", "warning",
          "两只流量计同时偏低（预警；不是泵出力下降：P5、P6 与预期一致）", ("B",), cols=FLOWS, group=G_METER,
          effect="供油流量1-2、回油流量1-2 读数各 × 0.97；P5、P6、回油质量流量不变"),
    Fault("F10", "F10_两只流量计同时偏低", "两只流量计同时偏低（油品粘度与标定时不同等共模因素，−5%）", "供油流量1-2、回油流量1-2",
          k_factor_many, {"names": FLOWS, "ratio": -0.05}, "const", "明显5%", "abnormal",
          "两只流量计同时偏低（异常）", ("C",), cols=FLOWS, group=G_METER,
          effect="供油流量1-2、回油流量1-2 读数各 × 0.95；P5、P6、回油质量流量不变"),
    # ---------------------------------------------------------------- 二、系统与管路（实际状态变化，多个测点联动）
    Fault("F11", "F11_泄漏", "供回油之间泄漏（接头/密封外漏或被试件内漏旁通）", "主油路", leak,
          {"ratio": 0.02}, "const", "轻微2%", "warning",
          "供回油之间泄漏（预警），两只流量计本身正常", ("B",), cols=SYSTEM_COLUMNS, group=G_SYSTEM,
          effect="回油流量1-2、回油质量流量 × 0.98；P5、P6 × 0.98^0.82；供油流量、P9、P1 不变"),
    Fault("F11", "F11_泄漏", "供回油之间泄漏（接头/密封外漏或被试件内漏旁通）", "主油路", leak,
          {"ratio": 0.04}, "const", "明显4%", "abnormal",
          "供回油之间泄漏（异常），两只流量计本身正常", ("A", "C"), cols=SYSTEM_COLUMNS, group=G_SYSTEM,
          effect="回油流量1-2、回油质量流量 × 0.96；P5、P6 × 0.96^0.82；供油流量、P9、P1 不变"),
    Fault("F12", "F12_渐进泄漏", "泄漏逐渐扩大（由 0 发展到 6%）", "主油路", leak,
          {"ratio": 0.06}, "ramp", "末端6%", "abnormal",
          "供回油之间泄漏（正在扩大）", ("B",), cols=SYSTEM_COLUMNS, group=G_SYSTEM,
          effect="回油流量1-2、回油质量流量 × (1 − 0.06·x)；P5、P6 同步降低；x 为测试进度 0→1"),
    Fault("F13", "F13_被试泵出力下降", "被试泵容积效率下降（内泄漏增大，实际流量减少，各信号仍一致）", "被试泵", pump_wear,
          {"ratio": 0.04}, "const", "4%", "warning",
          "被试泵出力低于预期（预警）", ("B",), cols=SYSTEM_COLUMNS, group=G_SYSTEM, effect=PUMP_EFFECT.format(k="0.96")),
    Fault("F13", "F13_被试泵出力下降", "被试泵容积效率下降（内泄漏增大，实际流量减少，各信号仍一致）", "被试泵", pump_wear,
          {"ratio": 0.08}, "const", "8%", "abnormal",
          "被试泵出力低于预期（异常）", ("A", "C"), cols=SYSTEM_COLUMNS, group=G_SYSTEM, effect=PUMP_EFFECT.format(k="0.92")),
    Fault("F14", "F14_电传转速信号偏高", "电传转速信号偏高（测速标定错误，实际转速偏低 5%）", SPEED, speed_signal_high,
          {"ratio": 0.05}, "const", "5%", "warning",
          "被试泵出力低于预期（其他可能中列出“电传转速信号偏高”；数据上与 F13 无法区分）", ("C",),
          cols=SYSTEM_COLUMNS, group=G_SYSTEM, effect="显示的电传转速不变；实际转速低 5%，其余变化同 F13（k = 0.95）"),
    Fault("F15", "F15_回油管路阻力增大", "回油管路（P6 之后，如回油滤网）堵塞，背压升高", "回油管路", return_resistance,
          {"dp": 0.010}, "const", "背压+0.010MPa", "warning",
          "回油管路阻力增大（P5、P6 同时升高，流量正常）", ("B",), cols=[P5, P6], group=G_SYSTEM,
          effect="P5、P6 各 + 0.010 MPa；流量、P9、P1 不变"),
    Fault("F15", "F15_回油管路阻力增大", "回油管路（P6 之后，如回油滤网）堵塞，背压升高", "回油管路", return_resistance,
          {"dp": 0.025}, "ramp", "背压由0增至+0.025MPa", "abnormal",
          "回油管路阻力增大（正在发展）", ("C",), cols=[P5, P6], group=G_SYSTEM,
          effect="P5、P6 各 + 0.025·x MPa；x 为测试进度 0→1"),
    Fault("F16", "F16_供油段堵塞", "供油段（供油流量计、滤网）堵塞，P9 与 P1 之间压降增大", "供油段", supply_clog,
          {"dp": 0.035}, "const", "压降+0.035MPa", "warning",
          "供油段压差异常（最可能：供油段阻力增大）", ("B",), cols=[P9, P1], group=G_SYSTEM,
          effect="P9 + 0.035 MPa；P1 不变（闭环）；流量不变"),
    Fault("F16", "F16_供油段堵塞", "供油段（供油流量计、滤网）堵塞，P9 与 P1 之间压降增大", "供油段", supply_clog,
          {"dp": 0.06}, "const", "压降+0.06MPa", "abnormal",
          "供油段压差异常（最可能：供油段阻力增大）", ("C",), cols=[P9, P1], group=G_SYSTEM,
          effect="P9 + 0.06 MPa；P1 不变（闭环）；流量不变"),
    # ---------------------------------------------------------------- 三、压力测点与控制回路
    Fault("F17", "F17_P5传感器零漂", "被试泵出口压力传感器零点漂移（P5低压压力 +0.012 MPa）", P5, pressure_offset,
          {"col": P5, "offset": 0.012}, "const", "+0.012MPa", "abnormal",
          "P5低压压力 传感器偏差（P6 与流量正常）", ("B",), group=G_PRESSURE, effect="P5低压压力 读数 + 0.012 MPa，其余测点不变"),
    Fault("F18", "F18_P6传感器零漂", "定压压力传感器零点漂移（P6定压压力 −0.010 MPa）", P6, pressure_offset,
          {"col": P6, "offset": -0.010}, "const", "-0.010MPa", "warning",
          "P6定压压力 传感器偏差（P5 与流量正常）", ("C",), group=G_PRESSURE, effect="P6定压压力 读数 − 0.010 MPa，其余测点不变"),
    Fault("F19", "F19_P9传感器零漂", "P9 控制腔压力传感器零点漂移（+0.035 MPa）", P9, pressure_offset,
          {"col": P9, "offset": 0.035}, "const", "+0.035MPa", "warning",
          "供油段压差异常（其他可能中列出 P9 传感器偏高；单次测试与供油段堵塞无法区分）", ("C",), group=G_PRESSURE,
          effect="P9控制腔压力 读数 + 0.035 MPa，其余测点不变"),
    Fault("F20", "F20_P1传感器零漂", "P1 进口压力传感器零点漂移（读数偏高 0.035 MPa，被控量被带偏）", P1, inlet_sensor_drift,
          {"offset": 0.035}, "const", "+0.035MPa", "warning",
          "供油段压差异常（最可能：P1 传感器偏高）", ("B",), cols=[P9, P1], group=G_PRESSURE,
          effect="P1 读数不变（闭环保持设定值）；实际进口压力低 0.035 MPa，P9 − 0.035 MPa"),
    Fault("F21", "F21_增压泵控制偏差", "增压泵控制偏差（进口压力偏离设定档位 −0.015 MPa）", P1, inlet_off_setpoint,
          {"offset": -0.015}, "const", "-0.015MPa", "warning",
          "P1进口压力 偏离设定值", ("B",), cols=[P9, P1], group=G_PRESSURE,
          effect="P1、P9 各 − 0.015 MPa（实际压力变化，传感器正常）"),
    Fault("F22", "F22_压力变送器断线", "压力变送器断线（4–20 mA 回路开路，读数跌到量程下限）", P5, signal_open,
          {"col": P5}, "step", "40%处断线", "abnormal",
          "P5低压压力 读数冻结（固定在 −0.375 MPa，仍在压力量程内，按冻结报出）", ("B",), group=G_PRESSURE,
          effect="P5低压压力 从故障时刻起读数固定为 −0.375 MPa"),
    # ---------------------------------------------------------------- 四、温度测点
    Fault("F23", "F23_回油温度传感器偏移", "回油温度热电阻偏移（老化/接线电阻，+5 ℃）", T_RETURN, temp_offset,
          {"col": T_RETURN, "offset": 5.0}, "const", "+5℃", "warning",
          "温升异常（回油温度1-1 偏高或被试泵发热）", ("B",), group=G_TEMP, effect="回油温度1-1 读数 + 5 ℃"),
    Fault("F24", "F24_供油温度传感器偏移", "供油温度热电阻偏移（未插到油里，−7 ℃）", T_SUPPLY, temp_offset,
          {"col": T_SUPPLY, "offset": -7.0}, "const", "-7℃", "warning",
          "温升异常（其他可能中列出供油温度1-2 偏低）", ("C",), group=G_TEMP,
          effect="供油温度1-2 读数 − 7 ℃（它也是模型的油温输入）"),
    Fault("F25", "F25_油温传感器断路", "回油温度热电阻断路（读数固定约 157.6 ℃）", T_RETURN, temp_open,
          {"col": T_RETURN}, "step", "30%处断路", "abnormal",
          "回油温度1-1 传感器故障（超出量程）", ("B",), 0.3, group=G_TEMP, effect="回油温度1-1 从故障时刻起读数固定为 157.595 ℃"),
]

# ---------------------------------------------------------------------------
# 原样读写：只替换被改动列的文本，其余字节不变
# ---------------------------------------------------------------------------


@dataclass
class RawFile:
    text_lines: List[str]
    encoding: str
    header: List[str]
    data_idx: List[int]          # 数据行在 text_lines 中的下标
    fields: List[List[str]]      # 数据行拆分后的字段
    t: np.ndarray


def read_raw(path: Path) -> RawFile:
    text, encoding = decode_bytes(path.read_bytes())
    lines = text.split("\n")
    header = lines[0].rstrip("\r").split("\t")
    width = len([h for h in header if h.strip()])
    if parse_time(header[0]) is not None:
        raise ValueError(f"{path.name} 没有表头，请换一个带表头的健康文件")
    idx, fields, times = [], [], []
    for i, line in enumerate(lines[1:], start=1):
        parts = line.rstrip("\r").split("\t")
        if len([p for p in parts if p.strip()]) < width:
            continue
        tt = parse_time(parts[0])
        if tt is None:
            continue
        idx.append(i)
        fields.append(parts)
        times.append(tt)
    t = np.array(times, dtype=float)
    t = np.where(t < t[0] - 1, t + 86400, t)  # 跨零点
    return RawFile(lines, encoding, header, idx, fields, t)


def column(raw: RawFile, name: str) -> np.ndarray:
    j = raw.header.index(name)
    return np.array([float(f[j]) for f in raw.fields])


def write_raw(raw: RawFile, changed: Dict[str, np.ndarray], path: Path) -> None:
    lines = list(raw.text_lines)
    js = {raw.header.index(c): v for c, v in changed.items()}
    for k, i in enumerate(raw.data_idx):
        parts = list(raw.fields[k])
        for j, v in js.items():
            parts[j] = f"{v[k]:.3f}"
        cr = "\r" if lines[i].endswith("\r") else ""
        lines[i] = "\t".join(parts) + cr
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes("\n".join(lines).encode(raw.encoding))


def _slug(text: str) -> str:
    return re.sub(r"[\\/:*?\"<>|\s]+", "", text)


def generate(src_root: Path, out: Path, seed: int = 2026) -> List[Dict]:
    rows = []
    cache: Dict[str, RawFile] = {}
    for n, fault in enumerate(FAULTS):
        for key in fault.conditions:
            folder, name, label = CONDITIONS[key]
            src = src_root / folder / name
            raw = cache.setdefault(key, read_raw(src))
            needed = set(fault.cols) or {fault.kwargs["col"]}
            cols = {c: column(raw, c) for c in needed}
            g = profile(fault.profile, raw.t, fault.at)
            rng = np.random.default_rng(seed + n * 10 + ord(key))
            changed = fault.fn(cols, g, rng, **fault.kwargs)
            dst = out / fault.folder / f"{label}_{_slug(fault.severity)}.txt"
            write_raw(raw, changed, dst)
            onset = raw.t[0] + (raw.t[-1] - raw.t[0]) * fault.at if fault.profile == "step" else None
            rows.append({
                "文件": dst.relative_to(out).as_posix(), "故障编号": fault.code, "类别": fault.group, "故障": fault.name,
                "故障机理": " ".join((fault.fn.__doc__ or "").split()), "受影响测点与注入规律": fault.effect,
                "注入位置": fault.target, "程度": fault.severity, "出现方式": PROFILE_LABEL[fault.profile],
                "出现时刻(s)": f"{onset - raw.t[0]:.1f}" if onset is not None else "",
                "源文件": f"{folder}/{name}", "预期结论": fault.expect_by.get(key, fault.expect), "预期诊断": fault.expect_text,
            })
    return rows


def diagnose(out: Path, rows: List[Dict]) -> None:
    import json
    from pump_test_bench.app.core.data_reader import read_table
    from pump_test_bench.app.diagnosis.baseline import DEFAULT_BASELINE
    from pump_test_bench.app.diagnosis.engine import diagnose_frame
    baseline = json.loads(Path(DEFAULT_BASELINE).read_text(encoding="utf-8"))
    for r in rows:
        _, df = read_table(out / r["文件"])
        rep = diagnose_frame(df, baseline=baseline)
        res = rep.get("result") or rep.get("diagnosis_result")
        r["实际结论"] = res
        r["实际诊断"] = "；".join(c["name"] for c in rep.get("causes", [])) or rep.get("summary", "")
        r["是否符合"] = "是" if res == r["预期结论"] else ("偏严" if res == "abnormal" else "否")


MANIFEST_HEAD = """# 故障注入清单

本目录的数据由 `python -m pump_test_bench.tools.generate_fault_data` 在正常数据（`标准台性能录取数据`）上注入故障生成。
文件格式与试验台原始文件完全一致，只改动下面写明的测点，其余列的每个字节都与正常数据相同。
逐个文件的清单见同目录的 `故障清单.csv`。

## 一、诊断用的信号

按标准台原理图：增压泵 → P9 → 供油温度/流量1-2 → P1 → 被试泵（电传） → P5 → 回油温度1-1/流量1-2 → P6 → 油箱。

| 信号 | 数据列 | 位置 |
|---|---|---|
| P9控制腔压力 | P9控制腔压力 | 增压泵出口、供油流量计前 |
| 供油温度1-2 | 供油温度1-2 | 供油流量计处（也是模型的油温输入） |
| 供油流量1-2 | 供油流量1-2 | 供油管路（涡轮流量计） |
| P1进口压力 | P1进口压力 | 被试泵进口，由增压泵闭环控制在 0.10 / 0.15 / 0.25 MPa |
| 电传转速 | 电传实际转速 | 被试泵驱动，决定流量 |
| P5低压压力 | P5低压压力 | 被试泵出口 |
| 回油温度1-1 | 回油温度1-1 | 回油流量计处 |
| 回油流量1-2 | 回油流量1-2 | 回油管路（涡轮流量计） |
| P6定压压力 | P6定压压力 | 回油流量计后、油箱前 |
| （二级诊断参照）回油质量流量 | 回油质量流量2 | 回油管路，只在涡轮流量计二级诊断中使用 |

## 二、注入时用到的测点关系（由 60 个正常文件拟合）

- 被试泵是容积泵：流量由电传转速决定，基本不受进出口压力影响。
- P5、P6 ∝ Q^0.82（P6 在 P5 下游，两者只差约 0.001 MPa）。
- 供油段压差 P9 − P1 ∝ Q^1.57；P1 由增压泵闭环控制在设定值。
- 回油质量流量计测的是实际回油流量（泄漏、泵出力变化时随之变化，流量计 K 系数漂移时不变）。

系统类故障（泄漏、被试泵出力下降、电传转速信号偏差、管路堵塞、P1 传感器漂移）按这些关系让相关测点一起变化，
而不是只改一个测点。

## 三、源文件（正常数据）

| 代号 | 源文件 | 工况 |
|---|---|---|
"""


def write_markdown(out: Path, rows: List[Dict]) -> None:
    """人读的清单：按类别列出每种故障的机理、注入规律、文件与诊断结果。"""
    text = [MANIFEST_HEAD.rstrip("\n")]
    for key, (folder, name, label) in CONDITIONS.items():
        text.append(f"| {key} | {folder}/{name} | {label} |")
    text.append("\n出现方式：全程 = 整个文件都有故障；中途突发 = 在“出现时刻”突然出现；逐渐发展 = 从 0 线性发展到给定程度。")
    text.append("\n## 四、故障清单\n")
    diagnosed = "实际结论" in rows[0]
    groups: Dict[str, List[Dict]] = {}
    for r in rows:
        groups.setdefault(r["类别"], []).append(r)
    result_text = {"normal": "正常", "warning": "预警", "abnormal": "异常", "inconclusive": "无法判定"}
    for group, items in groups.items():
        text.append(f"### {group}\n")
        by_fault: Dict[str, List[Dict]] = {}
        for r in items:
            by_fault.setdefault(r["故障编号"], []).append(r)
        for code, rs in by_fault.items():
            text.append(f"**{code} {rs[0]['故障']}**\n")
            text.append(f"- 故障机理：{rs[0]['故障机理']}")
            text.append(f"- 注入位置：{rs[0]['注入位置']}\n")
            head = "| 文件 | 程度 | 出现方式 | 受影响测点与注入规律 | 预期结论 | 预期诊断 |"
            text.append(head + (" 实际结论 | 实际诊断 |" if diagnosed else ""))
            text.append("|---|---|---|---|---|---|" + ("---|---|" if diagnosed else ""))
            for r in rs:
                how = r["出现方式"] + (f"（第 {r['出现时刻(s)']} 秒）" if r["出现时刻(s)"] else "")
                line = (f"| {r['文件']} | {r['程度']} | {how} | {r['受影响测点与注入规律']} | "
                        f"{result_text[r['预期结论']]} | {r['预期诊断']} |")
                if diagnosed:
                    line += f" {result_text.get(r['实际结论'], r['实际结论'])} | {r['实际诊断']} |"
                text.append(line)
            text.append("")
    if diagnosed:
        ok = sum(r["是否符合"] == "是" for r in rows)
        text.append(f"共 {len(rows)} 个文件，诊断结论（正常/预警/异常）与预期一致的 {ok} 个。")
    (out / "故障注入清单.md").write_text("\n".join(text) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path, help="健康数据目录（含 15-25 / 27-30 / 36-38 / 45-50 摄氏度子目录）")
    ap.add_argument("--out", type=Path, required=True, help="输出目录")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--no-diagnose", action="store_true", help="只生成，不跑诊断")
    args = ap.parse_args(argv)
    rows = generate(args.src, args.out, args.seed)
    if not args.no_diagnose:
        diagnose(args.out, rows)
    with open(args.out / "故障清单.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    write_markdown(args.out, rows)
    for r in rows:
        print(r["文件"], r.get("实际结论", ""), r.get("是否符合", ""), r.get("实际诊断", ""), sep=" | ")
    if not args.no_diagnose:
        ok = sum(r["是否符合"] == "是" for r in rows)
        print(f"\n{ok}/{len(rows)} 与预期一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
