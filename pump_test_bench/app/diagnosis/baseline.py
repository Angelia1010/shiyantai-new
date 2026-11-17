"""健康基准：用设备正常时的数据，统计诊断要用的各种“健康时的离散”和固有差异。

内容：
- signals：各信号 1 秒内的短时波动（噪声检查的参照）；
- isolation.sigma：故障隔离中各观测量（两只流量计、P5、P6 相对模型预期的偏离，实际流量参照）的离散。
  按“无故障”假设对每个健康文件做加权最小二乘，残差的均方根迭代估计；
- pair：两只流量计之间随流量、油温变化的固有差异（没有模型参照时比较两只表用）；
- turbine：涡轮流量计二级诊断中各表相对涡轮流量计模型的固有偏差与离散；
- density：燃油密度-温度关系（涡轮流量计模型的密度输入），由回油质量流量与体积流量拟合；
- ranges：建基准的流量、油温范围（固有偏差模型不外推）。
固有偏差模型：偏差 = c0 + c1·(Q/100) + c2·(T/10) + c3·(Q/100)·(T/10)（见 tolerances.py）。

基准文件查找顺序：
1. <DB_PATH 所在目录>/baseline.json（在前端或用工具重新建立的）；
2. pump_test_bench/config/baseline_default.json（随代码提供，由 2026-11 的 60 个健康数据文件生成）。

建立基准（需要先建立仿真模型的基准表）：
    python -m pump_test_bench.tools.build_baseline <健康数据目录> [--save]
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from pump_test_bench.app.core.data_reader import TABLE_SUFFIXES, read_table
from pump_test_bench.app.diagnosis import checks as ck, hypotheses as hy, isolation as iso
from pump_test_bench.app.diagnosis.bench_signals import RETURN_FLOW, SUPPLY_FLOW, SignalSet
from pump_test_bench.app.diagnosis.config import load_config
from pump_test_bench.app.diagnosis.engine import analyze
from pump_test_bench.app.diagnosis.fuel import density
from pump_test_bench.app.diagnosis.tolerances import features
from pump_test_bench.app.simulation.condition import input_columns

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


def _fit(points: List[Tuple[float, float, float]], ranges: Dict) -> Dict:
    """points：(值, 流量, 温度)。按工况拟合固有偏差，返回 {coef, std, ranges, n}；点少时退化为常数。"""
    y = np.array([p[0] for p in points])
    if len(points) >= MIN_FILES_FOR_MODEL:
        X = np.array([features(p[1], p[2], ranges) for p in points])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        return {"coef": [float(c) for c in coef], "std": float(np.std(y - X @ coef)), "ranges": ranges,
                "n": len(points)}
    return {"coef": [float(y.mean()), 0.0, 0.0, 0.0], "std": float(y.std()), "ranges": ranges, "n": len(points)}


def _isolation_sigma(samples: List[List[iso.Observation]], cfg: Dict) -> Dict[str, float]:
    """按“无故障”假设拟合每个健康文件（只有实际流量偏移一个参数），残差均方根迭代估计各观测量的离散。"""
    sigma = dict(cfg["isolation"]["sigma"])
    for _ in range(6):
        res: Dict[str, List[float]] = {}
        for obs in samples:
            obs = [iso.Observation(o.key, o.value, sigma.get(o.key, o.sigma), o.level) for o in obs]
            fit = iso.fit(obs, ())
            if fit is None:
                continue
            for key, r in fit.residuals.items():
                res.setdefault(key, []).append(r)
        floors = cfg["isolation"].get("sigma_floor", {})
        for key, values in res.items():
            floor = floors.get("anchor" if key == hy.ANCHOR else ("flow" if "流量" in key else "pressure"), 0.0)
            sigma[key] = max(float(np.sqrt(np.mean(np.square(values)))), floor)
    return sigma


def build_baseline(paths: Iterable[Path], source: str = "") -> Tuple[Dict, List[str]]:
    """返回 (基准, 跳过的文件说明)。只用找到稳定段、且主油路有流量的文件。"""
    from pump_test_bench.app.diagnosis import turbine_check
    from pump_test_bench.app.diagnosis.engine import load_sims
    cfg = load_config()
    sims = load_sims()
    signals = SignalSet.from_config(cfg)
    S, R = signals.column(SUPPLY_FLOW), signals.column(RETURN_FLOW)
    tcfg = cfg.get("turbine") or {}
    keep = {S, R, tcfg.get("mass_column")} | {m.get("temperature_column") for m in (tcfg.get("meters") or {}).values()}
    for mcfg, _ in sims:
        if mcfg["id"] == tcfg.get("model"):
            keep |= set(input_columns(mcfg))
    cv: Dict[str, List[float]] = {}
    pair, density_points, samples, segments = [], [], [], []
    skipped = []

    for path in paths:
        try:
            _, df = read_table(path)
            result = analyze(df, cfg, baseline=None, sims=sims)
        except Exception as exc:  # 单个文件有问题不影响整体
            skipped.append(f"{path.name}：{exc}")
            continue
        loop = result["loops"][0]
        if not loop["active"] or not result["segment"].found:
            skipped.append(f"{path.name}：没有流量或没有稳定段")
            continue
        status, flow, temp = result["status"], loop.get("consensus"), loop.get("temperature")
        for col, st in status.items():
            if st.cv is not None:
                cv.setdefault(col, []).append(st.cv)
        if result["observations"]:
            samples.append(result["observations"])
        if flow and temp is not None and status[S].usable and status[R].usable:
            pair.append(((status[S].mean - status[R].mean) / flow, flow, temp))
            seg = result["segment"]
            segments.append((df.iloc[seg.start:seg.end][[c for c in keep if c and c in df.columns]].copy(), flow, temp))
            mass_col = tcfg.get("mass_column")
            if mass_col in df.columns:
                mass = ck.mean_of(df.iloc[seg.start:seg.end][mass_col])
                if mass:
                    # 健康状态下，质量流量 ÷ 体积流量 就是实际密度
                    density_points.append((temp, mass / flow * 1000.0))

    used = len(segments)
    if used < MIN_FILES:
        raise ValueError(f"可用的健康数据文件只有 {used} 个，至少需要 {MIN_FILES} 个")
    flows, temps = [s[1] for s in segments], [s[2] for s in segments]
    ranges = {"flow": [min(flows), max(flows)], "temperature": [min(temps), max(temps)]}
    baseline: Dict = {
        "version": 3,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": source,
        "files": used,
        "ranges": ranges,
        "signals": {col: {"cv": float(np.median(v))} for col, v in cv.items()},
        "pair": _fit(pair, ranges),
    }
    if samples:
        baseline["isolation"] = {"sigma": _isolation_sigma(samples, cfg), "files": len(samples)}
    if len(density_points) >= MIN_FILES:
        t = np.array([p[0] for p in density_points])
        rho = np.array([p[1] for p in density_points])
        if np.ptp(t) >= 5:
            slope, intercept = np.polyfit(t - 15, rho, 1)
        else:  # 温度范围太窄，拟合斜率不可靠：沿用配置的斜率
            slope = cfg["fuel"]["slope"]
            intercept = float(np.mean(rho - slope * (t - 15)))
        resid = rho - (intercept + slope * (t - 15))
        baseline["density"] = {"rho15": float(intercept), "slope": float(slope), "resid_std": float(np.std(resid)),
                               "t_min": float(t.min()), "t_max": float(t.max())}
    # 涡轮流量计二级诊断的固有偏差：用本基准的密度模型计算，与诊断时一致
    density_fn = lambda temp: density(cfg, baseline, temp, None)[0]  # noqa: E731
    turbine = {}
    for meter in (tcfg.get("meters") or {}):
        pts = []
        for seg, flow, temp in segments:
            tc = turbine_check.raw_residual(seg, cfg, meter, sims, density_fn)
            if tc.available:
                pts.append((tc.raw, ck.mean_of(seg[meter]), temp))
        if len(pts) >= MIN_FILES:
            turbine[meter] = _fit(pts, ranges)
    if turbine:
        baseline["turbine"] = turbine
    return baseline, skipped


def build_from_directory(source: Path) -> Tuple[Dict, List[str]]:
    return build_baseline(_files(source), source=str(source))
