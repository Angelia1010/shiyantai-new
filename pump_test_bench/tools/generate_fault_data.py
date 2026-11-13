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

RETURN_METERS = ["回油流量1-1", "回油流量1-2"]
MASS = "回油质量流量2"
TEMP = "供油温度1-1"

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
# 故障模型：f(列数据字典, g, rng, 参数) -> 修改后的列数据字典（只返回改动的列）
# ---------------------------------------------------------------------------
Cols = Dict[str, np.ndarray]


def k_factor(cols: Cols, g, rng, col: str, ratio: float) -> Cols:
    """涡轮流量计 K 系数漂移：读数按比例偏移。磨损 → 偏低，沉积/流道变窄 → 偏高。"""
    return {col: cols[col] * (1 + ratio * g)}


def k_factor_many(cols: Cols, g, rng, names: List[str], ratio: float) -> Cols:
    """几只流量计同时 K 系数漂移（同一批次、同样工况下磨损）：互校只能看出“一侧整体偏了”。"""
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


def mass_zero(cols: Cols, g, rng, col: str, offset: float) -> Cols:
    """科氏质量流量计零点漂移：测量管应力、安装振动或未做零点标定，读数多一个固定量（kg/h）。"""
    return {col: cols[col] + offset * g}


def leak(cols: Cols, g, rng, ratio: float) -> Cols:
    """供油流量计之后、回油流量计之前泄漏（或内漏旁通）：回油侧所有表（含质量流量计）同时少 ratio；
    流过回油管路的油少了，回油管路压降（回油压力1-2 − 回油压力1-1）按 ΔP ∝ Q^1.1 相应减小。"""
    out = {c: cols[c] * (1 - ratio * g) for c in RETURN_METERS + [MASS]}
    _return_drop(cols, out, (1 - ratio * g) ** RETURN_DROP_EXP)
    return out


def aeration(cols: Cols, g, rng, ratio: float) -> Cols:
    """回油夹气 / 气穴：气泡占体积，涡轮表读的是混合物体积 → 偏高且抖动；科氏表两相解耦 → 偏低且抖动。"""
    out = {}
    for c in RETURN_METERS:
        v = cols[c]
        out[c] = v * (1 + ratio * g) + rng.normal(0, 0.02, len(v)) * v * g
    v = cols[MASS]
    out[MASS] = v * (1 - 0.5 * ratio * g) + rng.normal(0, 0.04, len(v)) * v * g
    return out


# ---------------------------------------------------------------------------
# 主要测点之间的关系（由 60 个正常文件拟合，见 docs/故障注入清单.md）
#   离心泵（燃油泵）：供油压力、P1 ≈ K·n² + 常数（n 为燃油泵转速，P1 由转速闭环控制在设定值）
#   供油管路压降：供油压力 − P1 ∝ Q^0.25        被试件出口：P5 ∝ Q^0.82
#   回油管路压降：回油压力1-2 − 回油压力1-1 ∝ Q^1.1（回油压力1-1 靠近油箱，恒为约 0.048 MPa）
# ---------------------------------------------------------------------------
PUMP_HEAD_K = 1.69e-7            # MPa / rpm²
SUPPLY_DROP_EXP, OUTLET_EXP, RETURN_DROP_EXP = 0.25, 0.82, 1.1
FEED_SPEED, DRIVE_SPEED = "燃油泵实际转速", "电传实际转速"
INLET_P, OUTLET_P = "P1进口压力", "P5低压压力"
SUPPLY_P = ["供油压力1-1", "供油压力1-2"]
RETURN_P_UP, RETURN_P_DOWN = "回油压力1-2", "回油压力1-1"
FLOW_PRESSURE = {OUTLET_P: OUTLET_EXP, "P6定压压力": 0.9}   # P6 不是主要测点，只为保持数据自洽一并修改
ALL_FLOW_METERS = ["供油流量1-1", "供油流量1-2", "齿轮流量计"] + RETURN_METERS
PRESSURES = SUPPLY_P + [INLET_P, OUTLET_P, RETURN_P_UP, RETURN_P_DOWN]
PUMP_COLUMNS = ALL_FLOW_METERS + [MASS] + list(FLOW_PRESSURE) + PRESSURES
LOOP_COLUMNS = PRESSURES + [FEED_SPEED]


def _return_drop(cols: Cols, out: Cols, factor) -> None:
    """回油管路压降按 factor 变化（缺少这两列时不处理）。"""
    if RETURN_P_UP in cols and RETURN_P_DOWN in cols:
        down = float(np.nanmean(cols[RETURN_P_DOWN]))
        out[RETURN_P_UP] = down + (cols[RETURN_P_UP] - down) * factor


def _feed_speed(cols: Cols, out: Cols, extra_head) -> None:
    """闭环控制为了保持 P1 设定值，离心泵需要多提供 extra_head（MPa）的压力：转速按 P ∝ n² 变化。"""
    if FEED_SPEED in cols:
        out[FEED_SPEED] = np.sqrt(np.maximum(cols[FEED_SPEED] ** 2 + extra_head / PUMP_HEAD_K, 0.0))


def pump_wear(cols: Cols, g, rng, ratio: float) -> Cols:
    """被试泵容积效率下降（内泄漏增大、配流面磨损）：同一转速下实际流量减少 ratio，
    所有流量计（含质量流量计）同比例减少，各表彼此仍然一致；与流量相关的压力同步变化：
    P5 ∝ Q^0.82，回油管路压降 ∝ Q^1.1，供油管路压降（供油压力 − P1）∝ Q^0.25。"""
    k = 1 - ratio * g
    out = {c: cols[c] * k for c in ALL_FLOW_METERS + [MASS] if c in cols}
    for c, e in FLOW_PRESSURE.items():
        if c in cols:
            out[c] = cols[c] * k ** e
    _return_drop(cols, out, k ** RETURN_DROP_EXP)
    if INLET_P in cols:
        for c in SUPPLY_P:
            if c in cols:
                out[c] = cols[INLET_P] + (cols[c] - cols[INLET_P]) * k ** SUPPLY_DROP_EXP
    return out


def speed_signal_high(cols: Cols, g, rng, ratio: float) -> Cols:
    """电传转速信号偏高（测速齿盘/编码器标定错误）：转速按显示值闭环控制，实际转速比显示值低 ratio，
    被试泵实际流量随之减少 ratio，显示的转速不变。数据上的表现与被试泵出力下降相同。"""
    return pump_wear(cols, g, rng, ratio)


def gear_slip(cols: Cols, g, rng, col: str, loss20: float, temp: str = TEMP) -> Cols:
    """齿轮流量计内泄漏（齿顶/端面间隙磨损）：一部分油从间隙漏过不带动齿轮，少计一个基本固定的流量；
    间隙泄漏量与粘度成反比，油温越高漏得越多（按每升高 1 ℃ 增加 2.5% 估算），小流量时百分比更大。"""
    t = float(np.nanmean(cols[temp])) if temp in cols else 20.0
    return {col: np.maximum(cols[col] - loss20 * (1 + 0.025 * (t - 20)) * g, 0.0)}


def supply_clog(cols: Cols, g, rng, dp: float) -> Cols:
    """供油管路/被试件进口滤网堵塞：供油压力测点到 P1 之间多出压降 dp（MPa）。P1 由离心泵转速闭环控制，
    仍保持设定值；离心泵转速升高（P ∝ n²），供油压力1-1、1-2 同时升高 dp。流量由被试泵（容积泵）决定，不变。"""
    out = {c: cols[c] + dp * g for c in SUPPLY_P}
    _feed_speed(cols, out, dp * g)
    return out


def feed_pump_wear(cols: Cols, g, rng, ratio: float) -> Cols:
    """离心泵（燃油泵）性能衰退（叶轮磨损、口环间隙增大、气蚀）：同一转速下扬程下降 ratio。
    P1 闭环控制仍保持设定值，各压力不变，离心泵转速升高到 n/√(1−ratio) 才能维持同样的压力。"""
    return {FEED_SPEED: cols[FEED_SPEED] / np.sqrt(1 - ratio * g)}


def return_clog(cols: Cols, g, rng, ratio: float) -> Cols:
    """回油管路/回油滤堵塞：回油管路阻力增大，回油压降（回油压力1-2 − 回油压力1-1）增大 ratio 倍；
    被试件出口背压（P5）升高同样的压力值。被试泵是容积泵，流量基本不变。"""
    out: Cols = {}
    _return_drop(cols, out, 1 + ratio * g)
    out[OUTLET_P] = cols[OUTLET_P] + (out[RETURN_P_UP] - cols[RETURN_P_UP])
    return out


def inlet_sensor_drift(cols: Cols, g, rng, offset: float) -> Cols:
    """P1 进口压力传感器零点漂移（读数偏高 offset）：P1 是闭环控制的被控量，控制器把“读数”保持在设定值，
    实际进口压力被带低 offset：离心泵转速降低，供油压力1-1、1-2 同时降低 offset，而 P1 读数不变。"""
    out = {c: cols[c] - offset * g for c in SUPPLY_P}
    _feed_speed(cols, out, -offset * g)
    return out


def signal_open(cols: Cols, g, rng, col: str, value: float = -0.375) -> Cols:
    """压力变送器断线（4–20 mA 回路开路）：读数跌到量程下限以下的固定值（约 −0.375 MPa，
    与本批数据中 P13 燃油油箱压力 的表现一致）。"""
    v = cols[col].copy()
    v[g > 0.5] = value
    return {col: v}


def level_drop(cols: Cols, g, rng, col: str, drop: float) -> Cols:
    """油箱液位持续下降（外漏、回油没有回到油箱）：液位读数随时间线性降低。"""
    return {col: cols[col] - drop * g}


def false_pulses(cols: Cols, g, rng, col: str, level: float) -> Cols:
    """无流量时涡轮流量计有读数（管路振动使叶轮微动、或干扰产生虚假脉冲）。"""
    v = cols[col]
    return {col: v + np.abs(level + rng.normal(0, 0.15 * level, len(v))) * g}


def pressure_offset(cols: Cols, g, rng, col: str, offset: float) -> Cols:
    """压力传感器零点漂移：膜片疲劳、温漂或安装应力，读数多一个固定值（MPa）。该测点没有冗余表。"""
    return {col: cols[col] + offset * g}


def temp_offset(cols: Cols, g, rng, col: str, offset: float) -> Cols:
    """温度传感器偏移：热电阻老化、接线电阻、安装不到位（未插到油里）。"""
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
    cols: Sequence[str] = ()                                   # 需要读取的列（默认按 col 参数或回油侧）
    effect: str = ""                                           # 受影响的测点与注入规律（写入清单）
    group: str = ""                                            # 故障类别


# 代表性工况（健康源文件）：低温中流量 / 中温中流量 / 高温大流量 / 中温小流量
CONDITIONS = {
    "A": ("20261102数据（15-25摄氏度）", "S250-P0.10.txt", "16℃_S250-P0.10"),
    "B": ("36-38摄氏度", "S4975-P0.15.txt", "36℃_S4975-P0.15"),
    "C": ("45-50摄氏度", "S9980-P0.10.txt", "46℃_S9980-P0.10"),
    "D": ("27-30摄氏度", "S1295-P0.15.txt", "27℃_S1295-P0.15"),
}

LEAK_COLUMNS = RETURN_METERS + [MASS, RETURN_P_UP, RETURN_P_DOWN]
SUPPLY_METERS = ["供油流量1-1", "供油流量1-2", "齿轮流量计"]
G_METER, G_MASS, G_SYSTEM, G_PRESSURE, G_OTHER = "流量计本体", "质量流量计", "系统与管路", "压力测点与控制回路", "温度、液位与小流量管路"


def _k(col: str, ratio: float) -> str:
    return f"{col} 读数 × {1 + ratio:.3f}（{ratio * 100:+.1f}%），其余测点不变"


FAULTS: List[Fault] = [
    # ---------------------------------------------------------------- 一、流量计本体（涡轮 / 齿轮）
    Fault("F01", "F01_涡轮磨损偏低", "涡轮流量计K系数漂移（叶片/轴承磨损，读数偏低）", "回油流量1-2", k_factor,
          {"col": "回油流量1-2", "ratio": -0.02}, "const", "轻微2%", "warning",
          "回油流量1-2 计量偏差（预警）", ("A", "B"), group=G_METER, effect=_k("回油流量1-2", -0.02)),
    Fault("F01", "F01_涡轮磨损偏低", "涡轮流量计K系数漂移（叶片/轴承磨损，读数偏低）", "回油流量1-2", k_factor,
          {"col": "回油流量1-2", "ratio": -0.05}, "const", "明显5%", "abnormal",
          "回油流量1-2 计量偏差（异常）", ("C",), group=G_METER, effect=_k("回油流量1-2", -0.05)),
    Fault("F02", "F02_涡轮沉积偏高", "涡轮流量计K系数漂移（沉积/流道变窄，读数偏高）", "供油流量1-1", k_factor,
          {"col": "供油流量1-1", "ratio": 0.04}, "const", "明显4%", "abnormal",
          "供油流量1-1 计量偏差（异常）", ("B",), group=G_METER, effect=_k("供油流量1-1", 0.04)),
    Fault("F03", "F03_渐进磨损", "涡轮流量计渐进磨损（测试中由 0 发展到 −8%）", "回油流量1-1", k_factor,
          {"col": "回油流量1-1", "ratio": -0.08}, "ramp", "末端8%", "abnormal",
          "回油流量1-1 计量偏差（正在发展）", ("B",), group=G_METER,
          effect="回油流量1-1 读数 × (1 − 0.08·x)，x 为测试进度 0→1"),
    Fault("F04", "F04_轴承阻滞", "涡轮流量计轴承阻滞（少计固定流量，伴随抖动）", "供油流量1-2", bearing_drag,
          {"col": "供油流量1-2", "loss": 12.0}, "const", "少计12L/h", "abnormal",
          "小流量时供油流量1-2 偏离明显（异常），大流量时偏离较小（预警）", ("D", "C"),
          expect_by={"C": "warning"}, group=G_METER,
          effect="供油流量1-2 读数 − 12 L/h，并叠加标准差 1% 的随机抖动"),
    Fault("F05", "F05_叶轮卡滞冻结", "流量计读数冻结（叶轮卡滞/变送器死机）", "回油流量1-1", freeze,
          {"col": "回油流量1-1"}, "step", "40%处冻结", "abnormal",
          "回油流量1-1 读数冻结", ("B",), group=G_METER, effect="回油流量1-1 从故障时刻起保持当时的读数不变"),
    Fault("F06", "F06_断线归零", "流量计信号断线（读数归零）", "供油流量1-1", drop_zero,
          {"col": "供油流量1-1"}, "step", "50%处断线", "abnormal",
          "供油流量1-1 读数掉零", ("C",), 0.5, group=G_METER, effect="供油流量1-1 从故障时刻起读数为 0（±0.05 L/h 噪声）"),
    Fault("F07", "F07_电磁干扰", "电磁干扰/接地不良（读数随机抖动）", "回油流量1-2", emi_noise,
          {"col": "回油流量1-2", "ratio": 0.04}, "const", "抖动4%", "warning",
          "回油流量1-2 波动过大", ("A",), group=G_METER, effect="回油流量1-2 叠加标准差为均值 4% 的随机噪声，均值不变"),
    Fault("F08", "F08_脉冲丢失", "脉冲丢失（接插件松动，偶发漏计，向下毛刺）", "齿轮流量计", pulse_loss,
          {"col": "齿轮流量计", "ratio": 0.01}, "const", "1%点丢失", "warning",
          "齿轮流量计有毛刺", ("B",), group=G_METER, effect="齿轮流量计随机 1% 的采样点读数下跌 15–50%"),
    Fault("F24", "F24_齿轮流量计内泄漏", "齿轮流量计内泄漏（齿顶/端面间隙磨损，少计，油温越高越明显）", "齿轮流量计", gear_slip,
          {"col": "齿轮流量计", "loss20": 6.0}, "const", "20℃时少计6L/h", "abnormal",
          "小流量时齿轮流量计偏低明显（异常），大流量时较小（预警）", ("D", "C"), expect_by={"C": "warning"},
          cols=["齿轮流量计", TEMP], group=G_METER,
          effect="齿轮流量计读数 − 6·(1 + 0.025·(油温 − 20)) L/h：27℃ 约 −7.1 L/h，46℃ 约 −9.9 L/h"),
    Fault("F22", "F22_中途突发偏低", "回油流量计中途突然偏低（异物卡入/叶片损伤，−4%）", "回油流量1-2", k_factor,
          {"col": "回油流量1-2", "ratio": -0.04}, "step", "50%处突变4%", "abnormal",
          "回油流量1-2 计量偏差（中途突变），给出变化开始时刻", ("B",), 0.5, group=G_METER,
          effect="回油流量1-2 从测试 50% 处起读数 × 0.96"),
    Fault("F23", "F23_两只表同时偏低", "一只回油、一只供油流量计同时偏低（两处独立故障，−3%）", "回油流量1-1、供油流量1-1",
          k_factor_many, {"names": ["回油流量1-1", "供油流量1-1"], "ratio": -0.03}, "const", "明显3%", "abnormal",
          "只报回油流量1-1 与供油流量1-1，其余表正常", ("C",), cols=["回油流量1-1", "供油流量1-1"], group=G_METER,
          effect="回油流量1-1、供油流量1-1 读数各 × 0.97"),
    Fault("F19", "F19_两只回油表同时偏低", "两只回油流量计同时 K 系数漂移（同批磨损，−4%）", "回油流量1-1、1-2", k_factor_many,
          {"names": RETURN_METERS, "ratio": -0.04}, "const", "明显4%", "abnormal",
          "两只回油流量计同时偏低（不是泄漏：质量流量计与供油侧一致）", ("B",), cols=RETURN_METERS, group=G_METER,
          effect="回油流量1-1、1-2 读数各 × 0.96；回油质量流量、压力不变"),
    Fault("F20", "F20_供油侧整体偏高", "三只供油侧流量计同时偏高（同批次/同一采集模块，+3%）", "供油侧", k_factor_many,
          {"names": SUPPLY_METERS, "ratio": 0.03}, "const", "明显3%", "warning",
          "供油侧流量计整体偏高（不是泄漏：模型预期流量与回油侧一致）", ("B", "C"), expect_by={"C": "abnormal"},
          cols=SUPPLY_METERS, group=G_METER, effect="供油流量1-1、1-2、齿轮流量计 读数各 × 1.03"),
    Fault("F21", "F21_体积表共模偏低", "全部体积流量计同时偏低（油品粘度变化等共模因素，−3%）", "体积流量计", k_factor_many,
          {"names": ALL_FLOW_METERS, "ratio": -0.03}, "const", "明显3%", "abnormal",
          "体积流量计整体偏低（不是质量流量计漂移：模型预期流量与质量流量计一致）", ("B", "C"), expect_by={"C": "warning"},
          cols=ALL_FLOW_METERS, group=G_METER, effect="5 只体积流量计读数各 × 0.97；回油质量流量不变"),
    # ---------------------------------------------------------------- 二、质量流量计
    Fault("F09", "F09_质量计零漂", "科氏质量流量计零点漂移（安装应力/未做零点标定，+12 kg/h）", MASS, mass_zero,
          {"col": MASS, "offset": 12.0}, "const", "+12kg/h", "abnormal",
          "小流量时质量-体积不一致明显（异常），大流量时较小（预警）", ("D", "C"),
          expect_by={"C": "warning"}, group=G_MASS,  # 46℃ 约 530 L/h 时 12 kg/h 仅约 2.9%，低于 3% 的异常阈值
          effect="回油质量流量（数据列 回油质量流量2）读数 + 12 kg/h"),
    Fault("F10", "F10_质量计标定漂移", "科氏质量流量计标定系数漂移（+5%）", MASS, k_factor,
          {"col": MASS, "ratio": 0.05}, "const", "明显5%", "abnormal",
          "质量流量与体积流量不一致（异常）", ("A",), group=G_MASS, effect=_k("回油质量流量（数据列 回油质量流量2）", 0.05)),
    # ---------------------------------------------------------------- 三、系统与管路（实际状态变化，多个测点联动）
    Fault("F11", "F11_泄漏", "供回油之间泄漏（接头/密封外漏或内漏旁通）", "回油侧", leak,
          {"ratio": 0.015}, "const", "轻微1.5%", "warning",
          "供回油之间泄漏（预警），各流量计本身正常", ("B",), cols=LEAK_COLUMNS, group=G_SYSTEM,
          effect="回油流量1-1、1-2、回油质量流量 × 0.985；回油管路压降（回油压力1-2 − 1-1）× 0.985^1.1"),
    Fault("F11", "F11_泄漏", "供回油之间泄漏（接头/密封外漏或内漏旁通）", "回油侧", leak,
          {"ratio": 0.04}, "const", "明显4%", "abnormal",
          "供回油之间泄漏（异常），各流量计本身正常", ("A", "C"), cols=LEAK_COLUMNS, group=G_SYSTEM,
          effect="回油流量1-1、1-2、回油质量流量 × 0.96；回油管路压降（回油压力1-2 − 1-1）× 0.96^1.1"),
    Fault("F12", "F12_渐进泄漏", "泄漏逐渐扩大（由 0 发展到 6%）", "回油侧", leak,
          {"ratio": 0.06}, "ramp", "末端6%", "abnormal",
          "供回油之间泄漏（正在扩大）", ("B",), cols=LEAK_COLUMNS, group=G_SYSTEM,
          effect="回油流量1-1、1-2、回油质量流量 × (1 − 0.06·x)；回油管路压降同步减小，x 为测试进度 0→1"),
    Fault("F13", "F13_回油夹气", "回油夹气/气穴（涡轮偏高、质量计偏低，均抖动）", "回油侧", aeration,
          {"ratio": 0.04}, "const", "含气约4%", "abnormal",
          "回油夹气（回油比供油多，不可能是泄漏）", ("C",), group=G_SYSTEM,
          effect="回油流量1-1、1-2 × 1.04 并叠加 2% 抖动；回油质量流量 × 0.98 并叠加 4% 抖动"),
    Fault("F16", "F16_被试泵出力下降", "被试泵容积效率下降（内泄漏增大，实际流量减少，各表仍一致）", "被试泵", pump_wear,
          {"ratio": 0.035}, "const", "3.5%", "warning",
          "被试泵出力低于预期（预警）；不用仿真模型时判为正常", ("B",), cols=PUMP_COLUMNS, group=G_SYSTEM,
          effect="全部流量计（含质量流量计）× 0.965；P5 × 0.965^0.82；回油管路压降 × 0.965^1.1；"
                 "供油管路压降（供油压力 − P1）× 0.965^0.25；电传转速不变"),
    Fault("F16", "F16_被试泵出力下降", "被试泵容积效率下降（内泄漏增大，实际流量减少，各表仍一致）", "被试泵", pump_wear,
          {"ratio": 0.08}, "const", "8%", "abnormal",
          "被试泵出力低于预期（异常）；不用仿真模型时判为正常", ("A", "C"), cols=PUMP_COLUMNS, group=G_SYSTEM,
          effect="全部流量计（含质量流量计）× 0.92；P5 × 0.92^0.82；回油管路压降 × 0.92^1.1；"
                 "供油管路压降（供油压力 − P1）× 0.92^0.25；电传转速不变"),
    Fault("F25", "F25_供油管路堵塞", "供油管路/被试件进口滤网堵塞（供油压力到 P1 之间压降增大）", "供油管路", supply_clog,
          {"dp": 0.03}, "const", "压降+0.03MPa", "abnormal",
          "压力测点偏离（按燃油泵转速，P1 低于模型预期；目前不能直接给出“供油管路堵塞”）", ("B",), cols=LOOP_COLUMNS, group=G_SYSTEM,
          effect="供油压力1-1、1-2 各 + 0.03 MPa；P1 不变（闭环）；燃油泵转速 n → √(n² + 0.03/1.69e-7)（约 +8%）；流量不变"),
    Fault("F25", "F25_供油管路堵塞", "供油管路/被试件进口滤网堵塞（供油压力到 P1 之间压降增大）", "供油管路", supply_clog,
          {"dp": 0.05}, "ramp", "压降由0增至0.05MPa", "abnormal",
          "压力测点偏离（按燃油泵转速，P1 低于模型预期；目前不能直接给出“供油管路堵塞”）", ("C",), cols=LOOP_COLUMNS, group=G_SYSTEM,
          effect="供油压力1-1、1-2 各 + 0.05·x MPa；燃油泵转速同步升高；x 为测试进度 0→1"),
    Fault("F26", "F26_离心泵性能衰退", "离心泵（燃油泵）性能衰退（叶轮磨损/口环间隙增大/气蚀，扬程下降）", "离心泵", feed_pump_wear,
          {"ratio": 0.12}, "const", "扬程-12%", "abnormal",
          "供油压力1-1、1-2、P1 同时低于模型预期（目前不能直接给出“离心泵性能衰退”）", ("B",), cols=[FEED_SPEED], group=G_SYSTEM,
          effect="燃油泵转速 n → n/√(1 − 0.12)（约 +6.6%）；各压力、流量不变（P1 闭环）"),
    Fault("F27", "F27_回油管路堵塞", "回油管路/回油滤堵塞（回油阻力增大，背压升高）", "回油管路", return_clog,
          {"ratio": 0.5}, "const", "回油压降+50%", "abnormal",
          "P5、回油压力1-2 同时高于模型预期，流量正常（目前不能直接给出“回油管路堵塞”）", ("B",), cols=PRESSURES, group=G_SYSTEM,
          effect="回油管路压降（回油压力1-2 − 1-1）× 1.5；P5 升高同样的压力值；回油压力1-1、流量不变"),
    Fault("F27", "F27_回油管路堵塞", "回油管路/回油滤堵塞（回油阻力增大，背压升高）", "回油管路", return_clog,
          {"ratio": 0.8}, "ramp", "回油压降由0增至+80%", "abnormal",
          "P5、回油压力1-2 同时高于模型预期，流量正常（目前不能直接给出“回油管路堵塞”）", ("C",), cols=PRESSURES, group=G_SYSTEM,
          effect="回油管路压降 × (1 + 0.8·x)；P5 升高同样的压力值；x 为测试进度 0→1"),
    # ---------------------------------------------------------------- 四、压力测点与控制回路
    Fault("F17", "F17_压力传感器零漂", "被试件出口压力传感器零点漂移（P5低压压力 +0.02 MPa）", OUTLET_P, pressure_offset,
          {"col": OUTLET_P, "offset": 0.02}, "const", "+0.02MPa", "abnormal",
          "P5低压压力 压力测点偏离（无冗余表，只能靠模型发现）", ("B",), group=G_PRESSURE,
          effect="P5低压压力 读数 + 0.02 MPa，其余测点不变"),
    Fault("F28", "F28_P1传感器零漂", "P1 进口压力传感器零点漂移（+0.02 MPa，被控量被带偏）", INLET_P, inlet_sensor_drift,
          {"offset": 0.02}, "const", "+0.02MPa", "abnormal",
          "P1进口压力 压力测点偏离（P1 高于模型预期，供油压力与模型一致）", ("B",), cols=LOOP_COLUMNS, group=G_PRESSURE,
          effect="P1 读数不变（闭环保持设定值）；供油压力1-1、1-2 各 − 0.02 MPa；燃油泵转速 n → √(n² − 0.02/1.69e-7)（约 −6%）"),
    Fault("F29", "F29_供油压力传感器零漂", "供油压力1-1 传感器零点漂移（膜片疲劳/温漂，+0.02 MPa）", "供油压力1-1", pressure_offset,
          {"col": "供油压力1-1", "offset": 0.02}, "const", "+0.02MPa", "abnormal",
          "供油压力1-1 压力测点偏离（供油压力1-2、P1 正常）", ("B",), group=G_PRESSURE,
          effect="供油压力1-1 读数 + 0.02 MPa，其余测点不变"),
    Fault("F30", "F30_回油压力传感器零漂", "回油压力1-2 传感器零点漂移（+0.015 MPa）", RETURN_P_UP, pressure_offset,
          {"col": RETURN_P_UP, "offset": 0.015}, "const", "+0.015MPa", "abnormal",
          "回油压力1-2 压力测点偏离（P5、流量正常）", ("C",), group=G_PRESSURE,
          effect="回油压力1-2 读数 + 0.015 MPa，其余测点不变"),
    Fault("F31", "F31_压力变送器断线", "压力变送器断线（4–20 mA 回路开路，读数跌到量程下限）", "供油压力1-2", signal_open,
          {"col": "供油压力1-2"}, "step", "40%处断线", "abnormal",
          "供油压力1-2 压力测点偏离", ("B",), group=G_PRESSURE,
          effect="供油压力1-2 从故障时刻起读数固定为 −0.375 MPa"),
    Fault("F32", "F32_电传转速信号偏高", "电传转速信号偏高（测速标定错误，实际转速偏低 3.5%）", DRIVE_SPEED, speed_signal_high,
          {"ratio": 0.035}, "const", "3.5%", "warning",
          "被试泵出力低于预期（其他可能中列出“电传转速信号偏高”；数据上与 F16 无法区分）", ("C",), cols=PUMP_COLUMNS,
          group=G_PRESSURE, effect="显示的电传转速不变；实际转速低 3.5%，全部流量与相关压力的变化同 F16（3.5%）"),
    # ---------------------------------------------------------------- 五、温度、液位与小流量管路
    Fault("F14", "F14_油温传感器偏移", "油温传感器偏移（热电阻老化/未插到油里，密度修正被带偏）", TEMP, temp_offset,
          {"col": TEMP, "offset": 4.0}, "const", "+4℃", "warning",
          "同位置两只温度传感器不一致（预警）", ("B",), group=G_OTHER, effect="供油温度1-1 读数 + 4 ℃"),
    Fault("F14", "F14_油温传感器偏移", "油温传感器偏移（热电阻老化/未插到油里，密度修正被带偏）", TEMP, temp_offset,
          {"col": TEMP, "offset": 8.0}, "const", "+8℃", "abnormal",
          "同位置两只温度传感器不一致（异常）", ("C",), group=G_OTHER, effect="供油温度1-1 读数 + 8 ℃"),
    Fault("F15", "F15_油温传感器断路", "油温热电阻断路（读数固定约157.6℃）", TEMP, temp_open,
          {"col": TEMP}, "step", "30%处断路", "abnormal",
          "供油温度1-1 超出量程（异常）", ("B",), 0.3, group=G_OTHER, effect="供油温度1-1 从故障时刻起读数固定为 157.595 ℃"),
    Fault("F33", "F33_油箱液位下降", "油箱液位持续下降（外漏/回油没有回到油箱）", "YW1燃油油箱液位", level_drop,
          {"col": "YW1燃油油箱液位", "drop": 5.0}, "ramp", "测试中下降5", "abnormal",
          "YW1燃油油箱液位 测点偏离（低于模型预期）", ("B",), group=G_OTHER, effect="YW1燃油油箱液位 读数 − 5·x，x 为测试进度 0→1"),
    Fault("F34", "F34_小流量表虚假读数", "小流量管路无流量时涡轮流量计有读数（振动/干扰产生虚假脉冲）", "回油流量2-1", false_pulses,
          {"col": "回油流量2-1", "level": 4.0}, "const", "约4L/h", "warning",
          "无流量时回油流量2-1 读数不为零", ("B",), group=G_OTHER, effect="回油流量2-1 读数 + 4 L/h（±15% 抖动）；该管路实际无流量"),
    Fault("F35", "F35_小流量质量计零漂", "小流量管路质量流量计零点漂移（无流量时读数偏大）", "回油质量流量1", mass_zero,
          {"col": "回油质量流量1", "offset": 20.0}, "const", "+20kg/h", "warning",
          "质量流量计零点偏移", ("B",), group=G_OTHER,
          effect="小流量管路质量流量计（数据列 回油质量流量1）读数 + 20 kg/h；该管路实际无流量"),
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
            needed = set(fault.cols) or ({fault.kwargs["col"]} if "col" in fault.kwargs else set(RETURN_METERS + [MASS]))
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

## 一、涉及的主要测量点

| 系统 | 主要测量点 | 数据文件中的列 | 说明 |
|---|---|---|---|
| 油箱系统 | 油箱供油压力 | P13燃油油箱压力 | 本批正常数据中恒为 −0.375 MPa（疑似未接入），不注入故障 |
| 油箱系统 | 油箱液位 | YW1燃油油箱液位 | 正常时约 47.9，几乎不变 |
| 离心泵驱动电机 | 电机转速 | 燃油泵实际转速 | 闭环调节，使 P1 保持设定值 |
| 供油系统 | 供油压力 1-1、1-2 | 供油压力1-1、供油压力1-2 | |
| 供油系统 | 供油流量 1-1、1-2 | 供油流量1-1、供油流量1-2 | 涡轮流量计 |
| 传动系统 | 电传实际转速 | 电传实际转速 | 决定被试泵流量 |
| 被试件 | P1 进口压力 | P1进口压力 | 被控量：0.10 / 0.15 / 0.25 MPa |
| 被试件 | 总流量计 | 齿轮流量计 | |
| 被试件 | 被试件出口压力 | P5低压压力 | |
| 回油系统（大流量管路） | 回油压力 1-1、1-2 | 回油压力1-1、回油压力1-2 | 1-1 靠近油箱，恒为约 0.048 MPa |
| 回油系统（大流量管路） | 回油流量 1-1、1-2 | 回油流量1-1、回油流量1-2 | 涡轮流量计 |
| 回油系统（大流量管路） | 回油质量流量 1 | 回油质量流量2 | 数据列名与原理图编号相反 |
| 回油系统（小流量管路） | 回油压力 / 流量 2-1、2-2，回油质量流量 2 | 回油流量2-1 等，回油质量流量1 | 本批数据中该管路没有流量 |
| （辅助） | 油温 | 供油温度1-1 | 用于密度修正和模型工况 |

## 二、注入时用到的测点关系（由 60 个正常文件拟合）

- 离心泵：供油压力、P1 ≈ 1.69×10⁻⁷ · n² + 常数（n 为燃油泵转速，rpm；压力 MPa）。P1 由燃油泵转速闭环控制。
- 供油管路压降：供油压力 − P1 ∝ Q^0.25。
- 被试件出口压力：P5 ∝ Q^0.82。
- 回油管路压降：回油压力1-2 − 回油压力1-1 ∝ Q^1.1。
- 被试泵是容积泵：流量由电传转速决定，基本不受进出口压力影响。

系统类故障（泄漏、被试泵出力下降、管路堵塞、离心泵衰退、P1 传感器漂移）按这些关系让相关测点一起变化，
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
