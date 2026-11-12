"""用正常数据标定模型：每个测点的固有偏差（随工况平滑变化）与离散（std）。

残差 = 实测/预期 − 1（相对，流量、压力）或 实测 − 预期（绝对，温度）。
诊断时先扣除固有偏差，再按离散定阈值。模型越准，离散越小，能发现的偏离越小。

代理模型由同一批正常数据拟合，直接在拟合数据上算离散会偏乐观；因此按“留一组”交叉验证
（每次留出一个数据目录，如一个油温段，用其余数据拟合后预测它）计算离散。AMESim 模型不经拟合，固有偏差也按留一组交叉验证。
"""
import logging
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import numpy as np

from pump_test_bench.app.simulation.condition import DensityFn, condition_of, measured_means
from pump_test_bench.app.simulation.config import residual_mode
from pump_test_bench.app.simulation.models import SurrogateModel, make_model
from pump_test_bench.app.simulation.table import build_table, predict

logger = logging.getLogger(__name__)
MIN_FILES = 10


def healthy_density_fn() -> DensityFn:
    """正常数据所用油品的密度模型（健康基准拟合的密度-温度关系）。"""
    from pump_test_bench.app.diagnosis.baseline import load_baseline
    from pump_test_bench.app.diagnosis.config import load_config
    from pump_test_bench.app.diagnosis.engine import _density
    cfg, baseline = load_config(), load_baseline()
    return lambda t: _density(cfg, baseline, t, None)[0]


def collect_samples(paths: Iterable[Path], sim_cfg: Dict, density_fn: Optional[DensityFn] = None) -> List[Dict]:
    """读取正常数据，取稳定段的工况与各测点均值。"""
    from pump_test_bench.app.core.data_reader import read_table
    from pump_test_bench.app.diagnosis.config import load_config
    from pump_test_bench.app.diagnosis.engine import analyze

    diag_cfg = load_config()
    density_fn = density_fn or healthy_density_fn()
    samples = []
    for path in paths:
        try:
            _, df = read_table(path)
            seg_info = analyze(df, diag_cfg, baseline=None)["segment"]
        except Exception as exc:
            logger.info("跳过 %s：%s", path.name, exc)
            continue
        if not seg_info.found:
            continue
        seg = df.iloc[seg_info.start:seg_info.end]
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


def _zs(sim_cfg: Dict, cond: Dict[str, float]) -> List[float]:
    """各输入按网格归一化到约 [-1, 1]。"""
    out = []
    for spec in sim_cfg["inputs"]:
        grid = spec["grid"]
        c, s = (max(grid) + min(grid)) / 2, max((max(grid) - min(grid)) / 2, 1e-9)
        out.append((cond[spec["name"]] - c) / s)
    return out


def _bias_features(z: List[float]) -> List[float]:
    """固有偏差模型：随第一个输入二次变化、随第二个输入线性变化（如流量计偏差随流量、粘度变化）。"""
    return [1.0, z[0], z[0] ** 2] + ([z[1]] if len(z) > 1 else [])


def _residuals(table: Dict, samples: List[Dict], sim_cfg: Dict) -> Dict[str, List[tuple]]:
    """{列: [(归一化输入, 残差), ...]}"""
    outputs = {c: o for o in sim_cfg["outputs"] for c in o["columns"]}
    res: Dict[str, List[tuple]] = {}
    for s in samples:
        pred, _ = predict(table, s["condition"])
        for col, value in s["measured"].items():
            o = outputs.get(col)
            p = pred.get(o["name"]) if o else None
            if p is None or (residual_mode(o) == "relative" and abs(p) < 1e-9):
                continue
            res.setdefault(col, []).append((_zs(sim_cfg, s["condition"]), residual(value, p, residual_mode(o)), s["group"]))
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


def calibrate(fit_points: Dict[str, List[tuple]], spread_points: Optional[Dict[str, List[tuple]]], sim_cfg: Dict) -> Dict:
    """fit_points 用来拟合固有偏差；spread_points（代理模型的交叉验证残差）用来估计离散，
    不给时对固有偏差本身做留一组交叉验证。"""
    outputs = {c: o for o in sim_cfg["outputs"] for c in o["columns"]}
    cols = {}
    for col, pts in fit_points.items():
        coef = _fit_bias(pts)
        if spread_points is None:  # 固有偏差也按留一组交叉验证，离散不偏乐观
            spread = np.array(_cv_spread(pts))
        else:
            spread = np.array([p[1] - float(np.dot(coef, _bias_features(p[0]))) for p in spread_points.get(col, pts)])
        o = outputs[col]
        mean_bias = float(np.mean([np.dot(coef, _bias_features(p[0])) for p in pts]))
        cols[col] = {"output": o["name"], "mode": residual_mode(o), "bias": mean_bias, "bias_coef": coef,
                     "std": float(spread.std()), "n": int(len(pts)), "max_abs": float(np.max(np.abs(spread)))}
    return {"columns": cols}


def bias_at(calib_col: Dict, sim_cfg: Dict, cond: Dict[str, float]) -> float:
    """该测点在当前工况下的固有偏差。"""
    coef = calib_col.get("bias_coef")
    if not coef:
        return calib_col.get("bias", 0.0)
    feats = _bias_features(_zs(sim_cfg, cond))
    return float(np.dot(coef, feats[:len(coef)]))


def build_reference(paths: List[Path], sim_cfg: Dict, kind: Optional[str] = None,
                    progress: Optional[Callable[[str, int, int], None]] = None, source: str = "") -> Dict:
    """建立一个模型的仿真基准表并标定。progress(阶段说明, 已完成, 总数)。"""
    kind = kind or sim_cfg.get("engine", {}).get("type", "surrogate")
    say = progress or (lambda *_: None)
    say("读取正常数据", 0, len(paths))
    samples = collect_samples(paths, sim_cfg)
    if len(samples) < MIN_FILES:
        raise ValueError(f"可用的正常数据只有 {len(samples)} 个文件（需要有稳定段且工况完整），至少需要 {MIN_FILES} 个")

    if kind == "surrogate":
        groups = sorted({s["group"] for s in samples})
        cv: Dict[str, List[tuple]] = {}
        for k, g in enumerate(groups):
            train = [s for s in samples if s["group"] != g]
            test = [s for s in samples if s["group"] == g]
            if len(groups) < 2 or len(train) < MIN_FILES:
                train = test = samples
            say(f"交叉验证 {k + 1}/{len(groups)}", k, len(groups))
            part = build_table(SurrogateModel.fit(train, sim_cfg), sim_cfg)
            for col, r in _residuals(part, test, sim_cfg).items():
                cv.setdefault(col, []).extend(r)
        table = build_table(SurrogateModel.fit(samples, sim_cfg), sim_cfg, lambda i, n: say("生成基准表", i, n))
        calib = calibrate(_residuals(table, samples, sim_cfg), cv, sim_cfg)
        calib["method"] = f"代理模型，按 {len(groups)} 个数据目录留一交叉验证"
    else:
        table = build_table(make_model(sim_cfg, kind), sim_cfg, lambda i, n: say("运行模型", i, n))
        calib = calibrate(_residuals(table, samples, sim_cfg), None, sim_cfg)
        calib["method"] = "AMESim 模型，固有偏差按留一组交叉验证"

    calib.update({"files": len(samples), "source": source})
    table["calibration"] = calib
    table["source"] = source
    say("完成", 1, 1)
    return table
