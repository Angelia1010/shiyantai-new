"""仿真基准表：模型在工况网格上的结果，在线诊断时多线性插值。

保存在 ``<DB_PATH 所在目录>/simulation_table.json``；没有时用随代码提供的
``config/simulation_table_default.json``（由 2026-11 正常数据的代理模型生成）。
"""
import itertools
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from pump_test_bench.app.simulation.models import SimulationModel

logger = logging.getLogger(__name__)
DEFAULT_TABLE = Path(__file__).resolve().parents[2] / "config" / "simulation_table_default.json"
_lock = threading.Lock()
_cache: Dict[str, Tuple[float, Dict]] = {}


def table_path() -> Path:
    from shared.config import get_settings
    return get_settings().db_path.parent / "simulation_table.json"


def build_table(model: SimulationModel, cfg: Dict, progress: Optional[Callable[[int, int], None]] = None) -> Dict:
    grids = [spec["grid"] for spec in cfg["inputs"]]
    names = [spec["name"] for spec in cfg["inputs"]]
    points = list(itertools.product(*grids))
    values: Dict[str, List[Optional[float]]] = {o["name"]: [] for o in cfg["outputs"]}
    try:
        for k, point in enumerate(points):
            result = model.run(dict(zip(names, point)))
            for out in values:
                values[out].append(result.get(out))
            if progress:
                progress(k + 1, len(points))
    finally:
        if hasattr(model, "close"):
            model.close()
    model_info = model.describe()
    if hasattr(model, "to_dict"):
        model_info["surrogate"] = model.to_dict()
    return {
        "version": 1,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": model_info,
        "inputs": [{"name": s["name"], "unit": s.get("unit", ""), "column": s["column"], "grid": s["grid"]}
                   for s in cfg["inputs"]],
        "outputs": [{k: o[k] for k in ("name", "unit", "kind", "columns") if k in o} for o in cfg["outputs"]],
        "values": values,
    }


def predict(table: Dict, condition: Dict[str, float]) -> Tuple[Dict[str, float], List[str]]:
    """多线性插值。返回 (预期值 {输出: 值}, 超出网格的输入说明)；超出网格时按边界取值。"""
    grids = [np.asarray(i["grid"], dtype=float) for i in table["inputs"]]
    shape = [len(g) for g in grids]
    outside, corners = [], []
    for spec, g in zip(table["inputs"], grids):
        x = condition.get(spec["name"])
        if x is None:
            raise ValueError(f"缺少输入：{spec['name']}")
        margin = 0.05 * (g[-1] - g[0])  # 略超出网格（如实测 3008 rpm 对网格 3000）按边界取值，不算超范围
        if x < g[0] - margin or x > g[-1] + margin:
            outside.append(f"{spec['name']} {x:.4g}{spec.get('unit', '')}（表内 {g[0]:g}–{g[-1]:g}）")
        x = min(max(x, g[0]), g[-1])
        j = int(np.clip(np.searchsorted(g, x) - 1, 0, len(g) - 2)) if len(g) > 1 else 0
        w = 0.0 if len(g) == 1 else (x - g[j]) / (g[j + 1] - g[j])
        corners.append([(j, 1 - w)] + ([(j + 1, w)] if len(g) > 1 else []))
    out = {}
    for name, flat in table["values"].items():
        arr = np.array([np.nan if v is None else v for v in flat], dtype=float).reshape(shape)
        total = 0.0
        for combo in itertools.product(*corners):
            weight = float(np.prod([w for _, w in combo]))
            if weight:
                total += weight * arr[tuple(i for i, _ in combo)]
        if not np.isnan(total):
            out[name] = float(total)
    return out, outside


def sensitivity(table: Dict, condition: Dict[str, float], output: str, ref_output: str,
                input_name: str, step: float = 0.05) -> Optional[float]:
    """输出对参考输出的弹性 d ln(output) / d ln(ref_output)，沿某个输入方向（如电传转速）数值求导。"""
    lo, hi = dict(condition), dict(condition)
    lo[input_name] *= 1 - step
    hi[input_name] *= 1 + step
    a, _ = predict(table, lo)
    b, _ = predict(table, hi)
    try:
        dy = np.log(b[output]) - np.log(a[output])
        dx = np.log(b[ref_output]) - np.log(a[ref_output])
    except (KeyError, ValueError, FloatingPointError):
        return None
    return float(dy / dx) if abs(dx) > 1e-9 and np.isfinite(dy) else None


def save_table(table: Dict, path: Optional[Path] = None) -> Path:
    path = path or table_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def load_table() -> Optional[Dict]:
    """数据目录下的基准表优先，其次随代码提供的默认表；都没有返回 None。"""
    candidates = []
    try:
        candidates.append(table_path())
    except Exception:  # 没有服务配置（如离线工具）时只用默认表
        pass
    candidates.append(DEFAULT_TABLE)
    for path in candidates:
        if not path.exists():
            continue
        mtime = path.stat().st_mtime
        with _lock:
            cached = _cache.get(str(path))
            if cached and cached[0] == mtime:
                return cached[1]
        try:
            table = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            logger.warning("仿真基准表格式错误，忽略：%s", path)
            continue
        table["_path"] = str(path)
        with _lock:
            _cache[str(path)] = (mtime, table)
        return table
    return None
