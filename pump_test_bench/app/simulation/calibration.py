"""用正常数据标定模型：每个测点“实测 / 模型预期 − 1”的固有偏差（bias）与离散（std）。

诊断时先扣除固有偏差，再按离散定阈值。这样无论模型是代理模型还是 AMESim，阈值都有依据：
模型越准，离散越小，能发现的偏离越小。

代理模型由同一批正常数据拟合，直接在拟合数据上算离散会偏乐观；因此按“留一组”交叉验证
（每次留出一个油温目录，用其余数据拟合后预测它）计算离散。AMESim 模型不经拟合，直接计算。
"""
import logging
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import numpy as np

from pump_test_bench.app.simulation.condition import condition_of, measured_means
from pump_test_bench.app.simulation.models import SurrogateModel, make_model
from pump_test_bench.app.simulation.table import build_table, predict

logger = logging.getLogger(__name__)
MIN_FILES = 10


def collect_samples(paths: Iterable[Path], sim_cfg: Dict) -> List[Dict]:
    """读取正常数据，取稳定段的工况与各测点均值。"""
    from pump_test_bench.app.core.data_reader import read_table
    from pump_test_bench.app.diagnosis.config import load_config
    from pump_test_bench.app.diagnosis.engine import analyze

    diag_cfg = load_config()
    samples = []
    for path in paths:
        try:
            _, df = read_table(path)
            seg_info = analyze(df, diag_cfg, baseline=None, sim_table=None)["segment"]
        except Exception as exc:
            logger.info("跳过 %s：%s", path.name, exc)
            continue
        if not seg_info.found:
            continue
        seg = df.iloc[seg_info.start:seg_info.end]
        cond, _ = condition_of(seg, sim_cfg)
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


def _residuals(table: Dict, samples: List[Dict], sim_cfg: Dict) -> Dict[str, List[float]]:
    col_out = {c: o["name"] for o in sim_cfg["outputs"] for c in o["columns"]}
    res: Dict[str, List[float]] = {}
    for s in samples:
        pred, _ = predict(table, s["condition"])
        for col, value in s["measured"].items():
            p = pred.get(col_out.get(col))
            if p is not None and abs(p) > 1e-9:
                res.setdefault(col, []).append(value / p - 1)
    return res


def calibrate(residuals: Dict[str, List[float]], sim_cfg: Dict) -> Dict:
    col_out = {c: o["name"] for o in sim_cfg["outputs"] for c in o["columns"]}
    cols = {}
    for col, r in residuals.items():
        r = np.asarray(r)
        cols[col] = {"output": col_out[col], "bias": float(r.mean()), "std": float(r.std()), "n": int(len(r)),
                     "max_abs": float(np.max(np.abs(r - r.mean())))}
    return {"columns": cols}


def build_reference(paths: List[Path], sim_cfg: Dict, kind: Optional[str] = None,
                    progress: Optional[Callable[[str, int, int], None]] = None, source: str = "") -> Dict:
    """建立仿真基准表并标定。progress(阶段说明, 已完成, 总数)。"""
    kind = kind or sim_cfg.get("model", {}).get("type", "surrogate")
    say = progress or (lambda *_: None)
    say("读取正常数据", 0, len(paths))
    samples = collect_samples(paths, sim_cfg)
    if len(samples) < MIN_FILES:
        raise ValueError(f"可用的正常数据只有 {len(samples)} 个文件（需要有稳定段且工况完整），至少需要 {MIN_FILES} 个")

    if kind == "surrogate":
        # 交叉验证求离散：每次留出一组（一个油温目录）
        groups = sorted({s["group"] for s in samples})
        residuals: Dict[str, List[float]] = {}
        for k, g in enumerate(groups):
            train = [s for s in samples if s["group"] != g]
            test = [s for s in samples if s["group"] == g]
            if len(groups) < 2 or len(train) < MIN_FILES:
                train = test = samples
            say(f"交叉验证 {k + 1}/{len(groups)}", k, len(groups))
            part = build_table(SurrogateModel.fit(train, sim_cfg), sim_cfg)
            for col, r in _residuals(part, test, sim_cfg).items():
                residuals.setdefault(col, []).extend(r)
        model = SurrogateModel.fit(samples, sim_cfg)
        table = build_table(model, sim_cfg, lambda i, n: say("生成基准表", i, n))
        calib = calibrate(residuals, sim_cfg)
        # 固有偏差用全量模型的残差（交叉验证只用来估计离散）
        for col, r in _residuals(table, samples, sim_cfg).items():
            if col in calib["columns"]:
                calib["columns"][col]["bias"] = float(np.mean(r))
        calib["method"] = f"按 {len(groups)} 个数据目录留一交叉验证"
    else:
        model = make_model(sim_cfg, kind)
        table = build_table(model, sim_cfg, lambda i, n: say("运行仿真", i, n))
        calib = calibrate(_residuals(table, samples, sim_cfg), sim_cfg)
        calib["method"] = "模型预期与正常数据直接比较"

    calib.update({"files": len(samples), "source": source})
    table["calibration"] = calib
    table["source"] = source
    say("完成", 1, 1)
    return table
