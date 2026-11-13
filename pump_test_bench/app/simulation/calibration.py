"""用正常数据标定模型：每个测点的固有偏差（随工况平滑变化）与离散（std）。

残差 = 实测/预期 − 1（相对，流量、压力）或 实测 − 预期（绝对，温度）。
诊断时先扣除固有偏差，再按离散定阈值。模型越准，离散越小，能发现的偏离越小。

数据代理模型由同一批正常数据拟合，直接在拟合数据上算离散会偏乐观；因此按“留一组”交叉验证
（每次留出一个数据目录，如一个油温段，用其余数据拟合后预测它）计算离散（见 surrogate.py）。
不经拟合的模型（AMESim、系数全部固定的公式）固有偏差按留一组交叉验证。
"""
import logging
import threading
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from pump_test_bench.app.simulation.condition import DensityFn, applicable, condition_of, measured_means
from pump_test_bench.app.simulation.config import residual_mode
from pump_test_bench.app.simulation.models import make_model
from pump_test_bench.app.simulation.table import build_table, predict

logger = logging.getLogger(__name__)
MIN_FILES = 10
LARGE_BIAS = 0.05  # 固定公式与现场相差超过 5%（相对）时提示核对

# 每个文件稳定段各列的均值（一行的 DataFrame），按 (路径, 修改时间) 缓存：反复验证公式时不必重读文件
_seg_cache: Dict[Tuple[str, float], Optional[pd.DataFrame]] = {}
_seg_lock = threading.Lock()
_SEG_CACHE_MAX = 3000


def healthy_density_fn() -> DensityFn:
    """正常数据所用油品的密度模型（健康基准拟合的密度-温度关系）。"""
    from pump_test_bench.app.diagnosis.baseline import load_baseline
    from pump_test_bench.app.diagnosis.config import load_config
    from pump_test_bench.app.diagnosis.fuel import density as _density
    cfg, baseline = load_config(), load_baseline()
    return lambda t: _density(cfg, baseline, t, None)[0]


def _segment_means(path: Path) -> Optional[pd.DataFrame]:
    """文件稳定段各数值列的均值（一行）；没有稳定段返回 None。"""
    key = (str(path), path.stat().st_mtime)
    with _seg_lock:
        if key in _seg_cache:
            return _seg_cache[key]
    from pump_test_bench.app.core.data_reader import read_table
    from pump_test_bench.app.diagnosis.config import load_config
    from pump_test_bench.app.diagnosis.engine import analyze
    _, df = read_table(path)
    seg_info = analyze(df, load_config(), baseline=None)["segment"]
    means = None
    if seg_info.found:
        seg = df.iloc[seg_info.start:seg_info.end].apply(pd.to_numeric, errors="coerce")
        means = seg.mean(numeric_only=True).to_frame().T
    with _seg_lock:
        if len(_seg_cache) >= _SEG_CACHE_MAX:
            _seg_cache.clear()
        _seg_cache[key] = means
    return means


def collect_samples(paths: Iterable[Path], sim_cfg: Dict, density_fn: Optional[DensityFn] = None) -> List[Dict]:
    """读取正常数据，取稳定段的工况与各测点均值。模型配置 exclude_files（"目录名/文件名"）中的文件不用。"""
    density_fn = density_fn or healthy_density_fn()
    excluded = set(sim_cfg.get("exclude_files") or [])
    samples = []
    for path in paths:
        path = Path(path)
        if f"{path.parent.name}/{path.name}" in excluded:
            continue
        try:
            seg = _segment_means(path)
        except Exception as exc:
            logger.info("跳过 %s：%s", path.name, exc)
            continue
        if seg is None or not applicable(seg, sim_cfg)[0]:
            continue
        cond, _ = condition_of(seg, sim_cfg, density_fn)
        if len(cond) < len(sim_cfg["inputs"]):
            continue
        measured = measured_means(seg, sim_cfg)
        outputs = {}
        for o in sim_cfg["outputs"]:
            vals = [measured[c] for c in o["columns"] if c in measured]
            if vals:
                outputs[o["name"]] = float(np.median(vals))
        samples.append({"file": path.name, "group": path.parent.name, "condition": cond,
                        "measured": measured, "outputs": outputs})
    return samples


def residual(measured: float, expected: float, mode: str) -> float:
    return measured - expected if mode == "absolute" else measured / expected - 1


def _zs(sim_cfg: Dict, cond: Dict[str, float], ranges: Optional[Dict[str, List[float]]] = None) -> List[float]:
    """各输入归一化到约 [-1, 1]：按建模数据的范围（ranges），没有时按网格。"""
    out = []
    for spec in sim_cfg["inputs"]:
        rng = (ranges or {}).get(spec["name"]) or ([min(spec["grid"]), max(spec["grid"])] if spec.get("grid") else None)
        if not rng:
            out.append(0.0)
            continue
        c, s = (rng[1] + rng[0]) / 2, max((rng[1] - rng[0]) / 2, 1e-9)
        out.append((cond.get(spec["name"], c) - c) / s)
    return out


def _bias_features(z: List[float]) -> List[float]:
    """固有偏差模型：随第一个输入二次变化、随第二个输入线性变化（如流量计偏差随流量、粘度变化）。"""
    return [1.0, z[0], z[0] ** 2] + ([z[1]] if len(z) > 1 else [])


def _residuals(table: Dict, samples: List[Dict], sim_cfg: Dict,
               ranges: Optional[Dict[str, List[float]]] = None) -> Dict[str, List[tuple]]:
    """{列: [(归一化输入, 残差, 组), ...]}"""
    outputs = {c: o for o in sim_cfg["outputs"] for c in o["columns"]}
    res: Dict[str, List[tuple]] = {}
    for s in samples:
        pred, _ = predict(table, s["condition"])
        for col, value in s["measured"].items():
            o = outputs.get(col)
            p = pred.get(o["name"]) if o else None
            if p is None or (residual_mode(o) == "relative" and abs(p) < 1e-9):
                continue
            res.setdefault(col, []).append((_zs(sim_cfg, s["condition"], ranges), residual(value, p, residual_mode(o)),
                                            s["group"]))
    return res


def _fit_bias(points: List[tuple]) -> List[float]:
    X = np.array([_bias_features(p[0]) for p in points])
    r = np.array([p[1] for p in points])
    if len(r) < 4 * X.shape[1]:
        return [float(r.mean())] + [0.0] * (X.shape[1] - 1)
    coef, *_ = np.linalg.lstsq(X, r, rcond=None)
    return [float(c) for c in coef]


def _cv_spread(points: List[tuple]) -> List[float]:
    groups = sorted({p[2] for p in points})
    if len(groups) < 2:
        coef = _fit_bias(points)
        return [p[1] - float(np.dot(coef, _bias_features(p[0]))) for p in points]
    out = []
    for g in groups:
        coef = _fit_bias([p for p in points if p[2] != g])
        out += [p[1] - float(np.dot(coef, _bias_features(p[0]))) for p in points if p[2] == g]
    return out


def calibrate(fit_points: Dict[str, List[tuple]], spread_points: Optional[Dict[str, List[tuple]]], sim_cfg: Dict,
              ranges: Optional[Dict[str, List[float]]] = None) -> Dict:
    """fit_points 用来拟合固有偏差；spread_points（由数据拟合的输出的交叉验证残差）用来估计离散，
    某列没有时对固有偏差本身做留一组交叉验证。"""
    outputs = {c: o for o in sim_cfg["outputs"] for c in o["columns"]}
    cols = {}
    for col, pts in fit_points.items():
        if col not in outputs:
            continue
        coef = _fit_bias(pts)
        cv_pts = (spread_points or {}).get(col)
        if not cv_pts:  # 固有偏差也按留一组交叉验证，离散不偏乐观
            spread = np.array(_cv_spread(pts))
        else:
            spread = np.array([p[1] - float(np.dot(coef, _bias_features(p[0]))) for p in cv_pts])
        o = outputs[col]
        mean_bias = float(np.mean([np.dot(coef, _bias_features(p[0])) for p in pts]))
        item = {"output": o["name"], "mode": residual_mode(o), "bias": mean_bias, "bias_coef": coef,
                "std": float(spread.std()), "n": int(len(pts)), "max_abs": float(np.max(np.abs(spread))),
                "z_ranges": ranges}
        if item["mode"] == "relative" and abs(mean_bias) > LARGE_BIAS:
            item["warning"] = (f"模型与现场平均相差 {mean_bias * 100:+.1f}%，诊断时会扣除，但请在后端模型配置中核对系数和单位"
                               "（例如流量计 K 系数、质量流量的单位）")
        cols[col] = item
    return {"columns": cols}


def bias_at(calib_col: Dict, sim_cfg: Dict, cond: Dict[str, float]) -> float:
    """该测点在当前工况下的固有偏差。"""
    coef = calib_col.get("bias_coef")
    if not coef:
        return calib_col.get("bias", 0.0)
    feats = _bias_features(_zs(sim_cfg, cond, calib_col.get("z_ranges")))
    return float(np.dot(coef, feats[:len(coef)]))


def build_reference(paths: List[Path], sim_cfg: Dict, kind: Optional[str] = None,
                    progress: Optional[Callable[[str, int, int], None]] = None, source: str = "") -> Dict:
    """建立一个模型的仿真基准表并标定。progress(阶段说明, 已完成, 总数)。"""
    kind = kind or sim_cfg.get("engine", {}).get("type", "surrogate")
    say = progress or (lambda *_: None)
    say("读取正常数据", 0, len(paths))
    samples = collect_samples(paths, sim_cfg)
    if len(samples) < MIN_FILES:
        need = "；".join(c.get("note") or c["column"] for c in sim_cfg.get("active_if") or [])
        raise ValueError(f"可用的正常数据只有 {len(samples)} 个文件（需要有稳定段、工况完整"
                         + (f"、且{need}" if need else "") + f"），至少需要 {MIN_FILES} 个")
    silent = [o["name"] for o in sim_cfg["outputs"]
              if all(abs(s["outputs"].get(o["name"]) or 0) < 1e-6 for s in samples)]
    if len(silent) == len(sim_cfg["outputs"]):
        raise ValueError(f"正常数据中这个模型的输出（{'、'.join(silent)}）都没有信号（如该管路没有流量），"
                         "无法用数据建立基准表；请用有流量的正常数据，或改用 AMESim 模型")

    if kind == "surrogate":
        from pump_test_bench.app.simulation.surrogate import fit_model, formula_table
        fitted = fit_model(samples, sim_cfg, progress=say)
        failed = {n: r["error"] for n, r in fitted["outputs"].items() if "error" in r}
        if len(failed) == len(sim_cfg["outputs"]):
            raise ValueError("；".join(f"{n}：{e}" for n, e in failed.items()))
        table = formula_table(sim_cfg, fitted, source)
        ranges = fitted["ranges"]
        # 由数据拟合的输出：离散用交叉验证预测的残差
        spread: Dict[str, List[tuple]] = {}
        data = fitted["data"]
        for name, r in fitted["outputs"].items():
            if "error" in r or not r["fitted_from_data"]:
                continue
            o = next(o for o in sim_cfg["outputs"] if o["name"] == name)
            mode = residual_mode(o)
            for k, s in enumerate(data["samples"]):
                p = r["_cv"][k]
                if not np.isfinite(p) or (mode == "relative" and abs(p) < 1e-9):
                    continue
                for col in o["columns"]:
                    if col in s["measured"]:
                        spread.setdefault(col, []).append(
                            (_zs(sim_cfg, s["condition"], ranges), residual(s["measured"][col], p, mode), s["group"]))
        calib = calibrate(_residuals(table, data["samples"], sim_cfg, ranges), spread, sim_cfg, ranges)
        calib["method"] = f"按 {len(set(data['groups']))} 个数据目录留一交叉验证"
        if failed:
            calib["failed_outputs"] = failed
    else:
        table = build_table(make_model(sim_cfg, kind), sim_cfg, lambda i, n: say("运行模型", i, n))
        ranges = {s["name"]: [min(s["grid"]), max(s["grid"])] for s in sim_cfg["inputs"] if s.get("grid")}
        calib = calibrate(_residuals(table, samples, sim_cfg, ranges), None, sim_cfg, ranges)
        calib["method"] = "仿真结果，固有偏差按留一组交叉验证"

    calib.update({"files": len(samples), "source": source})
    table["calibration"] = calib
    table["source"] = source
    say("完成", 1, 1)
    return table
