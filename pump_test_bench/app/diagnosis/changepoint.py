"""变点检测：稳定段内各测点的相对读数是否在某一时刻突变（step）或开始逐渐变化（ramp）。

输入是按时间窗求均值后的相对读数序列 y_i(w)（各表相对同一时刻的共识值，实际流量的波动已经抵消），
并按各表的预警阈值归一化。做法：
1. 在每个候选分割点 k 计算前后两段均值之差，取多测点联合统计量 Σ(Δ_i/噪声_i)²·k(n−k)/n 最大的 k；
2. 变化幅度达到预警阈值的 min_shift 倍、且统计上显著（z 检验，噪声用一阶差分的鲁棒估计）的测点才算变化；
3. 对发生变化的测点的合成信号分别拟合“阶跃”和“折线（在 k0 处开始线性变化）”，残差小的为变化类型；
   按该类型逐个测点求变化量，变化量还须达到拟合残差标准差的 effect 倍——健康数据中小流量时
   个别表会缓慢游走（几十秒内 ±2%），这种“变化”与残差同一量级，不算；
4. 给出变化开始时刻、各测点的变化量，以及代表“当前状态”的时间窗范围（阶跃后 / 渐变的末段），
   供故障隔离只用变化后的数据判断当前的故障。
本模块只做数学，不涉及测点含义。
"""
from dataclasses import dataclass, fields
from typing import Dict, Optional

import numpy as np

STEP, RAMP = "step", "ramp"


@dataclass(frozen=True)
class Options:
    min_windows: int = 5          # 变化前后各至少多少个时间窗
    min_shift: float = 0.5        # 变化量至少为预警阈值的多少倍
    z: float = 6.0                # 显著性（时间窗均值有自相关，取得比常规严格）
    effect: float = 3.0           # 变化量至少为拟合残差标准差的多少倍（排除健康数据的缓慢游走）
    tail: float = 0.2             # 渐变时用最后多少比例的时间窗代表当前状态
    margin: int = 1               # 阶跃后跳过的过渡时间窗

    @staticmethod
    def from_config(cfg: Dict) -> "Options":
        """配置中的同名项覆盖默认值（忽略说明等其他键）。"""
        known = {f.name for f in fields(Options)}
        return Options(**{k: v for k, v in (cfg or {}).items() if k in known})


@dataclass(frozen=True)
class Change:
    kind: str                     # STEP / RAMP
    onset_s: float                # 变化开始时刻（相对稳定段起点，秒）
    current_from: int             # 代表当前状态的时间窗起点（下标）
    shifts: Dict[str, float]      # 发生变化的测点 → 变化量（相对读数）


def _noise(z: np.ndarray) -> float:
    d = np.diff(z)
    return max(1.4826 * float(np.median(np.abs(d - np.median(d)))) / np.sqrt(2), 1e-3)


def _step_sse(u: np.ndarray, m: int):
    n = len(u)
    best = (np.inf, m)
    for k in range(m, n - m + 1):
        sse = float(((u[:k] - u[:k].mean()) ** 2).sum() + ((u[k:] - u[k:].mean()) ** 2).sum())
        best = min(best, (sse, k))
    return best


def _hinge(t: np.ndarray, k0: int) -> np.ndarray:
    return np.column_stack([np.ones(len(t)), np.maximum(t - t[k0], 0.0)])


def _ramp_sse(u: np.ndarray, t: np.ndarray, m: int):
    best = (np.inf, 0)
    for k0 in range(0, len(u) - m + 1):
        X = _hinge(t, k0)
        coef, *_ = np.linalg.lstsq(X, u, rcond=None)
        best = min(best, (float(((u - X @ coef) ** 2).sum()), k0))
    return best


def detect(t: np.ndarray, series: Dict[str, np.ndarray], scale: Dict[str, float],
           opts: Options = Options()) -> Optional[Change]:
    """t：各时间窗的时刻（秒）；series：测点 → 相对读数序列；scale：测点 → 预警阈值（用于归一化）。"""
    keys = [k for k in series if len(series[k]) == len(t) and np.isfinite(series[k]).all() and scale.get(k)]
    n, m = len(t), opts.min_windows
    if not keys or n < 2 * m + 1:
        return None
    Z = {k: np.asarray(series[k], dtype=float) / scale[k] for k in keys}
    noise = {k: _noise(Z[k]) for k in keys}

    def shifts_at(k: int) -> Dict[str, float]:
        return {c: float(Z[c][k:].mean() - Z[c][:k].mean()) for c in keys}

    def stat(k: int) -> float:
        return sum((d / noise[c]) ** 2 for c, d in shifts_at(k).items()) * k * (n - k) / n

    k_star = max(range(m, n - m + 1), key=stat)
    weight = np.sqrt(k_star * (n - k_star) / n)
    # 渐变时分割点两侧均值之差只有总变化量的一半左右，这里先放宽一半，最后按总变化量筛选
    moved = {c: d for c, d in shifts_at(k_star).items()
             if abs(d) >= opts.min_shift / 2 and abs(d) / noise[c] * weight >= opts.z}
    if not moved:
        return None

    # 合成信号：发生变化的测点按变化方向叠加
    u = np.mean([np.sign(d) * Z[c] for c, d in moved.items()], axis=0)
    t = np.asarray(t, dtype=float)
    sse_step, k_step = _step_sse(u, m)
    sse_ramp, k_ramp = _ramp_sse(u, t, m)
    if sse_ramp < sse_step:
        kind, onset, current = RAMP, k_ramp, max(n - max(m, int(round(n * opts.tail))), k_ramp)
        X = _hinge(t, k_ramp)
    else:
        kind, onset, current = STEP, k_step, min(k_step + opts.margin, n - m)
        X = np.column_stack([np.ones(n), (np.arange(n) >= k_step).astype(float)])
    total = {}
    for c in moved:
        y = np.asarray(series[c], dtype=float)
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        change = float(coef[1] * (t[-1] - t[k_ramp]) if kind == RAMP else coef[1])
        spread = float(np.std(y - X @ coef))
        if abs(change) >= opts.min_shift * scale[c] and abs(change) >= opts.effect * spread:
            total[c] = change
    if not total:
        return None
    return Change(kind, float(t[onset] - t[0]), int(current), total)
