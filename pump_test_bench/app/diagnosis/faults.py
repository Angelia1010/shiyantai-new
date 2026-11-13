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


def leak(df: pd.DataFrame, return_cols: List[str], ratio: float) -> pd.DataFrame:
    """供油后、回油前泄漏 ratio：回油侧所有表读数同时减少。"""
    out = df.copy()
    for col in return_cols:
        out[col] = _num(out, col) * (1 - ratio)
    return out


def scenarios(cfg: Dict) -> Dict[str, Callable[[pd.DataFrame], pd.DataFrame]]:
    """按配置生成一组典型故障场景：{场景名: 注入函数}。"""
    main = next(lp for lp in cfg["loops"] if lp.get("meters"))
    meters = [m["column"] for m in main["meters"]]
    returns = [m["column"] for m in main["meters"] if m.get("group") == "回油"]
    mass = main.get("mass_meter", {}).get("column")
    first, second = meters[0], meters[1]
    s = {
        f"{first} 漂移 +3%": lambda d: drift(d, first, 0.03),
        f"{first} 漂移 +5%": lambda d: drift(d, first, 0.05),
        f"{second} 漂移 -5%": lambda d: drift(d, second, -0.05),
        f"{first} 卡死": lambda d: stuck(d, first),
        f"{second} 噪声 5%": lambda d: noise(d, second, 0.05),
        f"{first} 毛刺 2%": lambda d: spikes(d, first),
        "回油侧泄漏 3%": lambda d: leak(d, returns + ([mass] if mass else []), 0.03),
    }
    if mass:
        s[f"{mass} 漂移 +4%"] = lambda d: drift(d, mass, 0.04)
    return s
