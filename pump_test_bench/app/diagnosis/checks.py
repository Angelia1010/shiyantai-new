"""诊断用到的基础检查与统计。"""
import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# 严重程度：提示信息 < 注意（不影响结论） < 预警 < 异常
INFO, NOTICE, WARNING, ABNORMAL = "info", "notice", "warning", "abnormal"
SEVERITY_RANK = {INFO: 0, NOTICE: 1, WARNING: 2, ABNORMAL: 3}
SEVERITY_TEXT = {INFO: "提示", NOTICE: "注意", WARNING: "预警", ABNORMAL: "异常"}


def finding(category: str, severity: str, title: str, detail: str, target: str = "", label: str = "",
            component: Optional[str] = None, value: Optional[float] = None, threshold: Optional[str] = None) -> Dict:
    return {
        "category": category, "severity": severity, "title": title, "detail": detail,
        "target": target, "label": label or target, "component": component,
        "value": None if value is None or (isinstance(value, float) and math.isnan(value)) else round(float(value), 6),
        "threshold": threshold,
    }


def grade(deviation: float, warn: float, alarm: float) -> str:
    d = abs(deviation)
    if d > alarm:
        return ABNORMAL
    if d > warn:
        return WARNING
    return INFO


def mean_of(series: pd.Series) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if len(values) else None


def is_stuck(series: pd.Series) -> bool:
    """整段读数完全不变（注意：试验台按 100 Hz 记录、传感器约 10 Hz 更新，相邻读数重复是正常的）。"""
    values = pd.to_numeric(series, errors="coerce").dropna()
    return len(values) > 10 and values.nunique() <= 1


def longest_constant_run(series: pd.Series, t: np.ndarray) -> float:
    """读数连续不变的最长时长（秒）。健康数据中流量计最长约 0.2 秒（10 Hz 更新），远超此值说明读数冻结。"""
    v = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    if len(v) < 2:
        return 0.0
    change = np.r_[True, v[1:] != v[:-1]]
    starts = np.flatnonzero(change)
    ends = np.r_[starts[1:], len(v)] - 1
    return float(np.max(t[ends] - t[starts]))


def zero_fraction(series: pd.Series, level: float, ratio: float = 0.02) -> float:
    """读数接近 0（低于 level 的 ratio）的比例：断线、叶轮卡死不转时读数掉零。"""
    v = pd.to_numeric(series, errors="coerce").dropna()
    if not len(v) or level <= 0:
        return 0.0
    return float((v.abs() < level * ratio).mean())


def window_means(frame: pd.DataFrame, t: np.ndarray, window: float = 1.0) -> pd.DataFrame:
    """按时间窗求各列均值（行 = 时间窗）。"""
    ids = np.floor((t - t[0]) / window).astype(int)
    return frame.apply(pd.to_numeric, errors="coerce").groupby(ids).mean()


def end_change(values: pd.Series, part: float = 0.25) -> Optional[float]:
    """后 part 段中位数减前 part 段中位数，表示测试过程中的持续变化（渐变故障）。"""
    v = values.dropna().to_numpy(dtype=float)
    k = int(len(v) * part)
    if k < 3:
        return None
    return float(np.median(v[-k:]) - np.median(v[:k]))


def window_cv(series: pd.Series, t: np.ndarray, window: float = 1.0) -> Optional[float]:
    """各时间窗内变异系数的中位数，表示读数的短时波动（噪声）水平。"""
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    if len(values) < 10:
        return None
    ids = np.floor((t - t[0]) / window).astype(int)
    frame = pd.DataFrame({"w": ids, "v": values}).dropna()
    grouped = frame.groupby("w")["v"]
    m, s = grouped.mean(), grouped.std()
    ok = (m.abs() > 1e-9) & s.notna()
    if not ok.any():
        return None
    return float((s[ok] / m[ok].abs()).median())


def spike_ratio(series: pd.Series, z: float) -> float:
    """鲁棒 z 分数（基于中位数绝对偏差）超过 z 的点所占比例。"""
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) < 20:
        return 0.0
    med = np.median(values)
    mad = np.median(np.abs(values - med)) * 1.4826
    mad = max(mad, abs(med) * 0.002, 1e-6)  # 量化分辨率造成 MAD 为 0 时给个下限
    return float(np.mean(np.abs(values - med) / mad > z))


def range_rule(column: str, rules: List[Dict]) -> Optional[Dict]:
    for rule in rules:
        if rule["match"] in column:
            return rule
    return None


def out_of_range_ratio(series: pd.Series, rule: Dict) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if not len(values):
        return 0.0
    return float(((values < rule["min"]) | (values > rule["max"])).mean())


def loo_deviation(means: Dict[str, float], column: str) -> Optional[float]:
    """该表相对其余各表均值中位数的相对偏差（留一法，单个坏表不会污染参考值）。"""
    others = [v for c, v in means.items() if c != column]
    if not others:
        return None
    ref = float(np.median(others))
    if abs(ref) < 1e-9:
        return None
    return (means[column] - ref) / ref
