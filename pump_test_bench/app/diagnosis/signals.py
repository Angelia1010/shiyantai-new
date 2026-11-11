"""时间轴与稳定段识别。"""
from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd

from pump_test_bench.app.core.table_parser import parse_time

FALLBACK_ROW_RATE = 100.0  # 没有时间列时按 100 行/秒


def time_axis(df: pd.DataFrame) -> np.ndarray:
    """每一行的时间（秒，从 0 开始）。时间列缺失或无法解析时按行号估算；处理整点/午夜回绕。"""
    n = len(df)
    if "时间" not in df.columns:
        return np.arange(n) / FALLBACK_ROW_RATE
    raw = [parse_time(str(v)) if v is not None else None for v in df["时间"].tolist()]
    if sum(v is not None for v in raw) < n * 0.9:
        return np.arange(n) / FALLBACK_ROW_RATE
    t = np.empty(n)
    offset, last = 0.0, None
    for i, v in enumerate(raw):
        if v is None:
            v = last if last is not None else 0.0
        elif last is not None and v < last - 30:
            offset += 86400 if last >= 3600 else 3600
        last = v
        t[i] = v + offset
    return t - t[0]


@dataclass
class Segment:
    start: int  # 行号（含）
    end: int  # 行号（不含）
    start_s: float
    end_s: float
    found: bool  # False 表示没有找到满足条件的稳定段，使用了整段数据

    @property
    def duration(self) -> float:
        return self.end_s - self.start_s

    def as_dict(self) -> Dict:
        return {"found": self.found, "start_s": round(self.start_s, 2), "end_s": round(self.end_s, 2),
                "duration_s": round(self.duration, 2), "rows": self.end - self.start}


def find_steady(values: np.ndarray, t: np.ndarray, cfg: Dict) -> Segment:
    """在 values（如流量共识值）中找最长的稳定段。"""
    n = len(values)
    whole = Segment(0, n, float(t[0]) if n else 0.0, float(t[-1]) if n else 0.0, False)
    if n == 0:
        return whole
    window = float(cfg.get("window_s", 1.0))
    ids = np.floor((t - t[0]) / window).astype(int)
    frame = pd.DataFrame({"w": ids, "v": values}).dropna()
    if frame.empty:
        return whole
    grouped = frame.groupby("w")["v"]
    means, stds = grouped.mean(), grouped.std().fillna(0.0)
    win_ids = means.index.to_numpy()
    m, s = means.to_numpy(), stds.to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        cv = np.where(np.abs(m) > 1e-9, s / np.abs(m), np.inf)
    max_cv = float(cfg.get("max_cv", 0.02))
    max_change = float(cfg.get("max_level_change", 0.02))

    best: Optional[tuple] = None
    i = 0
    while i < len(m):
        if cv[i] > max_cv:
            i += 1
            continue
        j = i + 1
        while j < len(m) and cv[j] <= max_cv:
            ref = np.median(m[i:j])
            if abs(ref) < 1e-9 or abs(m[j] - ref) / abs(ref) > max_change:
                break
            j += 1
        if best is None or (j - i) > (best[1] - best[0]):
            best = (i, j)
        i = j if j > i + 1 else i + 1

    if best is None:
        return whole
    lo_w, hi_w = win_ids[best[0]], win_ids[best[1] - 1]
    rows = np.where((ids >= lo_w) & (ids <= hi_w))[0]
    seg = Segment(int(rows[0]), int(rows[-1]) + 1, float(t[rows[0]]), float(t[rows[-1]]), True)
    if seg.duration < float(cfg.get("min_duration_s", 5)):
        return whole
    return seg
