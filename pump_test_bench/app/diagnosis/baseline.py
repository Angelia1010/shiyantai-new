"""健康基准：用设备正常时的数据，统计每个流量计的固有偏差与波动，拟合密度-温度关系。

为什么需要：串联的几只流量计即使都正常，读数也有零点几到一个多百分点的差异（安装位置、
标定误差），而且随流量和油温有规律地变化。把每只表的固有偏差拟合成
    偏差 = c0 + c1·(Q/100) + c2·(T/10) + c3·(Q/100)·(T/10)        （Q：流量 L/h，T：油温 ℃）
诊断时扣除，阈值可以收得更紧，更早发现漂移。文件太少时退化为常数。

基准文件查找顺序：
1. <DB_PATH 所在目录>/baseline.json（在前端或用工具重新建立的）；
2. pump_test_bench/config/baseline_default.json（随代码提供，由 2026-11 的 60 个健康数据文件生成）。

建立基准：
    python -m pump_test_bench.tools.build_baseline <健康数据目录> [--save]
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from pump_test_bench.app.core.data_reader import TABLE_SUFFIXES, read_table
from pump_test_bench.app.diagnosis.config import load_config
from pump_test_bench.app.diagnosis.engine import analyze
from pump_test_bench.app.diagnosis.tolerances import features

logger = logging.getLogger(__name__)
DEFAULT_BASELINE = Path(__file__).resolve().parents[2] / "config" / "baseline_default.json"
MIN_FILES = 5
MIN_FILES_FOR_MODEL = 12  # 拟合流量-温度模型至少需要的文件数


def baseline_path() -> Path:
    from shared.config import get_settings
    return get_settings().db_path.parent / "baseline.json"


def load_baseline() -> Optional[Dict]:
    try:
        candidates = [baseline_path(), DEFAULT_BASELINE]
    except Exception:  # 没有服务配置（离线工具）时只用随代码提供的基准
        candidates = [DEFAULT_BASELINE]
    for path in candidates:
        try:
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("健康基准文件无法读取：%s", path)
    return None


def save_baseline(baseline: Dict, path: Optional[Path] = None) -> Path:
    path = path or baseline_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _files(source: Path) -> List[Path]:
    if source.is_file():
        return [source]
    return sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in TABLE_SUFFIXES)


def build_baseline(paths: Iterable[Path], source: str = "") -> Tuple[Dict, List[str]]:
    """返回 (基准, 跳过的文件说明)。只用找到稳定段、且主油路有流量的文件。"""
    cfg = load_config()
    dev: Dict[str, List[Tuple[float, float, float]]] = {}  # 列 → [(偏差, 流量, 温度)]
    cv: Dict[str, List[float]] = {}
    balance: Dict[str, List[float]] = {}
    density_points: List[Tuple[str, float, float]] = []  # (管路, 温度, 实测密度)
    skipped, used = [], 0

    for path in paths:
        try:
            _, df = read_table(path)
            result = analyze(df, cfg, baseline=None)
        except Exception as exc:  # 单个文件有问题不影响整体
            skipped.append(f"{path.name}：{exc}")
            continue
        active = [lp for lp in result["loops"] if lp["active"]]
        if not active or not result["segment"].found:
            skipped.append(f"{path.name}：没有流量或没有稳定段")
            continue
        used += 1
        for loop in active:
            for m in loop["meters"]:
                if "deviation" in m:
                    dev.setdefault(m["column"], []).append((m["deviation"], loop["consensus"], loop.get("temperature")))
                if m.get("cv") is not None:
                    cv.setdefault(m["column"], []).append(m["cv"])
            if loop.get("balance"):
                balance.setdefault(loop["name"], []).append(loop["balance"]["raw"])
            mass = loop.get("mass") or {}
            if loop.get("consensus") and mass.get("mean") and mass.get("temperature") is not None:
                # 健康状态下，质量流量 ÷ 体积流量 就是实际密度
                density_points.append((loop["name"], mass["temperature"], mass["mean"] / loop["consensus"] * 1000.0))

    if used < MIN_FILES:
        raise ValueError(f"可用的健康数据文件只有 {used} 个，至少需要 {MIN_FILES} 个")

    points = [p for v in dev.values() for p in v if p[1] is not None and p[2] is not None]
    ranges = {"flow": [min(p[1] for p in points), max(p[1] for p in points)],
              "temperature": [min(p[2] for p in points), max(p[2] for p in points)]} if points else None
    meters = {}
    for col, v in dev.items():
        d = np.array([p[0] for p in v])
        entry = {"bias": float(d.mean()), "std": float(d.std()), "n": len(v),
                 "cv": float(np.median(cv[col])) if cv.get(col) else None}
        complete = [p for p in v if p[1] is not None and p[2] is not None]
        if ranges and len(complete) >= MIN_FILES_FOR_MODEL:
            X = np.array([features(p[1], p[2], ranges) for p in complete])
            y = np.array([p[0] for p in complete])
            coef, *_ = np.linalg.lstsq(X, y, rcond=None)
            entry["coef"] = [float(c) for c in coef]
            entry["std"] = float(np.std(y - X @ coef))  # 模型残差，即扣除固有偏差后剩下的离散
        meters[col] = entry

    baseline: Dict = {
        "version": 2,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": source,
        "files": used,
        "ranges": ranges,
        "meters": meters,
        "balance": {name: {"bias": float(np.mean(v)), "std": float(np.std(v))} for name, v in balance.items()},
    }
    if len(density_points) >= MIN_FILES:
        names = [p[0] for p in density_points]
        temps = np.array([p[1] for p in density_points])
        rhos = np.array([p[2] for p in density_points])
        if np.ptp(temps) >= 5:
            slope, intercept = np.polyfit(temps - 15, rhos, 1)
        else:  # 温度范围太窄，拟合斜率不可靠：沿用配置的斜率
            slope = cfg["fuel"]["slope"]
            intercept = float(np.mean(rhos - slope * (temps - 15)))
        resid = rhos - (intercept + slope * (temps - 15))
        baseline["density"] = {"rho15": float(intercept), "slope": float(slope), "resid_std": float(np.std(resid)),
                               "t_min": float(temps.min()), "t_max": float(temps.max())}
        rel = resid / rhos
        baseline["mass_volume"] = {
            name: {"std": float(np.std([r for n, r in zip(names, rel) if n == name]))} for name in set(names)
        }
    return baseline, skipped


def build_from_directory(source: Path) -> Tuple[Dict, List[str]]:
    return build_baseline(_files(source), source=str(source))
