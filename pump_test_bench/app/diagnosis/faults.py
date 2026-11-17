"""故障注入：在健康数据上人为制造典型故障，用来检验诊断能否查出、会不会误报。

每个函数接收 DataFrame，返回修改后的副本。
"""
from typing import Callable, Dict, List

import numpy as np
import pandas as pd


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce")


def drift(df: pd.DataFrame, col: str, ratio: float) -> pd.DataFrame:
    """读数整体偏大/偏小 ratio（标定漂移）。"""
    out = df.copy()
    out[col] = _num(out, col) * (1 + ratio)
    return out


def stuck(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """读数卡死在第一个值。"""
    out = df.copy()
    first = _num(out, col).dropna().iloc[0]
    out[col] = first
    return out


def noise(df: pd.DataFrame, col: str, ratio: float, seed: int = 0) -> pd.DataFrame:
    """叠加相对幅度为 ratio 的随机噪声（接地不良、气泡）。"""
    out = df.copy()
    v = _num(out, col)
    out[col] = v + np.random.default_rng(seed).normal(0, ratio * float(v.mean()), len(v))
    return out


def spikes(df: pd.DataFrame, col: str, ratio: float = 0.02, size: float = 0.5, seed: int = 0) -> pd.DataFrame:
    """随机 ratio 比例的点突跳 size（相对值）。"""
    out = df.copy()
    v = _num(out, col).to_numpy(dtype=float).copy()
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(v), max(1, int(len(v) * ratio)), replace=False)
    v[idx] *= 1 + size * rng.choice([-1, 1], len(idx))
    out[col] = v
    return out


def leak(df: pd.DataFrame, return_flow: str, pressures: List[str], ratio: float,
         mass: str = "", pressure_exp: float = 0.82) -> pd.DataFrame:
    """供油后、回油前泄漏 ratio：回油流量（及回油质量流量）减少 ratio，随回油流量变化的压力按 Q^0.82 降低。"""
    out = df.copy()
    for col in [return_flow] + ([mass] if mass and mass in out.columns else []):
        out[col] = _num(out, col) * (1 - ratio)
    for col in pressures:
        out[col] = _num(out, col) * (1 - ratio) ** pressure_exp
    return out


def offset(df: pd.DataFrame, col: str, value: float) -> pd.DataFrame:
    """读数多一个固定量（压力、温度传感器零点漂移）。"""
    out = df.copy()
    out[col] = _num(out, col) + value
    return out


def scenarios(cfg: Dict) -> Dict[str, Callable[[pd.DataFrame], pd.DataFrame]]:
    """按配置的诊断信号生成一组典型故障场景：{场景名: 注入函数}。场景名以被注入的列开头（泄漏除外）。"""
    from pump_test_bench.app.diagnosis.bench_signals import (BACK_PRESSURE, OUTLET_PRESSURE, RETURN_FLOW,
                                                              SUPPLY_FLOW, SignalSet)
    sig = SignalSet.from_config(cfg)
    S, R = sig.column(SUPPLY_FLOW), sig.column(RETURN_FLOW)
    p5, p6 = sig.column(OUTLET_PRESSURE), sig.column(BACK_PRESSURE)
    mass = (cfg.get("turbine") or {}).get("mass_column", "")
    return {
        f"{S} 漂移 +3%": lambda d: drift(d, S, 0.03),
        f"{S} 漂移 +5%": lambda d: drift(d, S, 0.05),
        f"{R} 漂移 -5%": lambda d: drift(d, R, -0.05),
        f"{S} 卡死": lambda d: stuck(d, S),
        f"{R} 噪声 5%": lambda d: noise(d, R, 0.05),
        f"{S} 毛刺 2%": lambda d: spikes(d, S),
        f"{p5} 零漂 +0.012MPa": lambda d: offset(d, p5, 0.012),
        "供回油泄漏 3%": lambda d: leak(d, R, [p5, p6], 0.03, mass),
    }
