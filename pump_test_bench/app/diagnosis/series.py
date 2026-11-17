"""报告里画图用的信号曲线：每个诊断信号按时间分箱的实测值，以及同一时刻模型给出的正常预期值和正常范围。

- 预期值：每个时间箱按该箱的工况（电传转速、油温、P1）查仿真模型，再加上测点的固有偏差，
  与 expectation.model_view 对稳定段的算法一致，只是逐箱计算，所以升降速过程中的预期也跟着变；
- 正常范围：预期值 ± 预警限（流量、P5、P6 为相对值，P9、温度为绝对值，与报告中模型对比的限值相同）；
- 工况输入信号（电传转速、供油温度、P1）没有模型预期，只给实测值，P1 另给设定档位；
- 实测曲线按 3 秒滑动平均（判定用的也是均值），另附未平均的读数 raw；
- 每个信号还给出稳定段内的偏差、判定等级、隔离时的指纹（实测偏差与最可能解释的拟合值）。

只用于展示，不参与判定。
"""
import logging
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from pump_test_bench.app.diagnosis.checks import INFO, SEVERITY_RANK
from pump_test_bench.app.simulation.calibration import bias_at
from pump_test_bench.app.simulation.condition import condition_of
from pump_test_bench.app.simulation.config import residual_mode
from pump_test_bench.app.simulation.table import predict

logger = logging.getLogger(__name__)
MAX_POINTS = 300
SMOOTH_S = 3.0     # 曲线的滑动平均窗口（秒）：低转速时 P5、P6 读数波动约 ±10%，平均后才能和正常范围对比


def _bins(t: np.ndarray) -> np.ndarray:
    """每行所属的时间箱序号：行数不多时每行一箱，否则等宽分箱，总箱数不超过 MAX_POINTS。"""
    n = len(t)
    if n <= MAX_POINTS:
        return np.arange(n)
    span = max(float(t[-1] - t[0]), 1e-9)
    return np.minimum(np.floor((t - t[0]) / (span / MAX_POINTS)).astype(int), MAX_POINTS - 1)


def _modes(mcfg: Dict) -> Dict[str, tuple]:
    """列 → (残差方式, 种类)。"""
    return {col: (residual_mode(o), o["kind"]) for o in mcfg["outputs"] for col in o["columns"]}


def _expected_columns(mcfg: Dict, table: Dict, cond: Dict) -> Dict[str, float]:
    pred, _ = predict(table, cond)
    calib = (table.get("calibration") or {}).get("columns", {})
    out = {}
    for o in mcfg["outputs"]:
        p, mode = pred.get(o["name"]), residual_mode(o)
        if p is None or not np.isfinite(p):
            continue
        for col in o["columns"]:
            c = calib.get(col, {})
            b = bias_at(c, mcfg, cond) if c else 0.0
            out[col] = p + b if mode == "absolute" else p * (1 + b)
    return out


def _digits(unit: str) -> int:
    """曲线数据保留的小数位（够画图即可，减小报告体积）：压力 4 位，其余 2 位。"""
    return 4 if unit == "MPa" else 2


def _round(values, digits: int = 5) -> List[Optional[float]]:
    return [None if v is None or not np.isfinite(v) else round(float(v), digits) for v in values]


def build(df: pd.DataFrame, t: np.ndarray, segment, signals, status: Dict, view, cfg: Dict, sims,
          density_fn, findings: List[Dict], model_rows: List[Dict], isolation: Optional[Dict],
          limits: Callable[[str, str, str], tuple]) -> Dict:
    """limits(列, 种类, 残差方式) → (预警限, 异常限)：没有模型对比行（如读数冻结、不参与对比）的信号用它给正常范围。"""
    bins = _bins(t)
    rate = (len(t) - 1) / max(float(t[-1] - t[0]), 1e-9) if len(t) > 1 else 1.0
    smooth = max(1, int(round(rate * SMOOTH_S)))
    groups = pd.Series(np.arange(len(df))).groupby(bins)
    times = [round(float(t[idx.to_numpy()].mean()), 2) for _, idx in groups]

    mcfg, table = next(((m, tb) for m, tb in sims or [] if m["id"] == view.model_id), (None, None))
    expected: Dict[str, List[Optional[float]]] = {}
    modes = _modes(mcfg) if mcfg else {}
    if view.available and mcfg is not None:
        rows = []
        for _, idx in groups:
            part = df.iloc[idx.to_numpy()]
            try:
                cond, _ = condition_of(part, mcfg, density_fn)
                rows.append(_expected_columns(mcfg, table, cond) if len(cond) >= len(table["inputs"]) else {})
            except Exception:
                logger.debug("时间箱模型预期计算失败", exc_info=True)
                rows.append({})
        for col in modes:
            if any(r.get(col) is not None for r in rows):
                expected[col] = [r.get(col) for r in rows]

    by_row = {r["column"]: r for r in model_rows}
    obs = {o["key"]: o for o in (isolation or {}).get("observations") or []}
    out = []
    for s in signals:
        col = s.column
        if col not in df.columns:
            continue
        series_ = pd.to_numeric(df[col], errors="coerce")
        raw = series_.groupby(bins).mean().to_numpy(dtype=float)
        # 判定用的是均值，正常范围也是针对均值的：曲线按 SMOOTH_S 秒滑动平均画，另附未平均的读数（看噪声、毛刺）
        values = series_.rolling(smooth, center=True, min_periods=1).mean().groupby(bins).mean().to_numpy(dtype=float)
        st = status.get(col)
        row = by_row.get(col)
        severity = st.severity if st else INFO
        hits = [f for f in findings if f.get("target") == col]
        for sev in [f["severity"] for f in hits] + ([row["severity"]] if row else []):
            if SEVERITY_RANK.get(sev, 0) > SEVERITY_RANK.get(severity, 0):
                severity = sev
        entry = {"column": col, "key": s.key, "label": s.label, "unit": s.unit, "kind": s.kind,
                 "component": s.component, "position": s.position, "severity": severity,
                 "usable": bool(st.usable) if st else False, "flags": sorted(st.flags) if st else [],
                 "mean": st.mean if st else None, "values": _round(values, _digits(s.unit)),
                 "raw": _round(raw, _digits(s.unit)),
                 "findings": [f["title"] for f in hits]}
        if col in expected:
            mode, kind = modes[col]
            exp = np.array([np.nan if v is None else v for v in expected[col]], dtype=float)
            warn, alarm = (row["warn"], row["alarm"]) if row else limits(col, kind, mode)
            if mode == "absolute":
                lo, hi = exp - warn, exp + warn
            else:
                lo, hi = exp * (1 - warn), exp * (1 + warn)
            nd = _digits(s.unit)
            entry.update(mode=mode, expected=_round(exp, nd), band_low=_round(lo, nd), band_high=_round(hi, nd),
                         warn=warn, alarm=alarm, expected_mean=row["expected"] if row else None,
                         residual=row["residual"] if row else None)
        elif s.setpoints:
            entry["setpoints"] = list(s.setpoints)
        if col in obs:
            o = obs[col]
            entry["fingerprint"] = {k: o[k] for k in ("value", "fitted", "sigma")}
            # 最可能的故障解释让该信号明显偏离正常（拟合值超过 2σ 且超过预警限的一半）：示意图上标为“受影响”
            entry["affected"] = bool(abs(o["fitted"]) >= max(2 * o["sigma"], 0.5 * entry.get("warn", 0)))
        out.append(entry)
    return {"time": times, "segment": [segment.start_s, segment.end_s] if segment.found else None,
            "signals": out}
