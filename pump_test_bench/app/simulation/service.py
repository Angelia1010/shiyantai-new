"""仿真模型的服务层（供任务服务的 /simulation/* 接口使用）：状态汇总、后台重建基准表、工况试算。"""
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from pump_test_bench.app.simulation.calibration import build_reference
from pump_test_bench.app.simulation.check import _thresholds
from pump_test_bench.app.simulation.config import load_sim_config
from pump_test_bench.app.simulation.table import DEFAULT_TABLE, load_table, predict, save_table, table_path

logger = logging.getLogger(__name__)
MODEL_LABELS = {"surrogate": "数据代理模型（由正常数据拟合）", "amesim": "AMESim 模型"}

_job_lock = threading.Lock()
_job: Dict = {"state": "idle"}


def job_status() -> Dict:
    with _job_lock:
        return dict(_job)


def _set_job(**kw) -> None:
    with _job_lock:
        _job.update(kw)


def start_build(paths, model: str, source: str, operator: str) -> Dict:
    """后台建立基准表；同一时间只允许一个任务。"""
    with _job_lock:
        if _job.get("state") == "running":
            raise RuntimeError("已有基准表正在建立，请等待完成")
        _job.clear()
        _job.update({"state": "running", "model": model, "source": source, "operator": operator,
                     "stage": "准备", "done": 0, "total": 0, "started": int(time.time() * 1000), "error": None})

    def progress(stage, done, total):
        _set_job(stage=stage, done=done, total=total)

    def work():
        try:
            table = build_reference(list(paths), load_sim_config(), model, progress, source=source)
            save_table(table)
            _set_job(state="done", stage="完成", finished=int(time.time() * 1000))
            logger.info("用户 %s 重建仿真基准表（%s，%s）", operator, model, source)
        except Exception as exc:  # 失败原因返回给前端
            logger.exception("建立仿真基准表失败")
            _set_job(state="failed", error=str(exc), finished=int(time.time() * 1000))

    threading.Thread(target=work, name="simulation-table", daemon=True).start()
    return job_status()


def status() -> Dict:
    cfg = load_sim_config()
    table = load_table()
    info = None
    if table:
        kinds = {o["name"]: o["kind"] for o in cfg["outputs"]}
        calib = table.get("calibration") or {}
        columns = []
        for col, c in calib.get("columns", {}).items():
            warn, alarm = _thresholds(cfg["thresholds"], kinds.get(c["output"], "flow"), c.get("std"))
            columns.append({"column": col, "output": c["output"], "bias": c["bias"], "std": c["std"],
                            "warn": warn, "alarm": alarm, "n": c.get("n")})
        path = Path(table.get("_path", ""))
        info = {"created": table.get("created"), "model": table.get("model", {}), "source": table.get("source", ""),
                "is_default": path == DEFAULT_TABLE, "inputs": table["inputs"], "outputs": table["outputs"],
                "calibration": {"files": calib.get("files"), "method": calib.get("method"), "columns": columns}}
    return {
        "config": {"model": cfg.get("model", {}).get("type", "surrogate"), "model_labels": MODEL_LABELS,
                   "inputs": [{k: i.get(k) for k in ("name", "column", "unit", "grid")} for i in cfg["inputs"]],
                   "outputs": [{k: o.get(k) for k in ("name", "unit", "kind", "columns")} for o in cfg["outputs"]],
                   "amesim_ready": "待填写" not in str(cfg.get("amesim", {}))},
        "table": info,
        "job": job_status(),
    }


def try_predict(condition: Dict) -> Dict:
    table = load_table()
    if not table:
        raise ValueError("还没有仿真基准表，请先建立")
    cond = {}
    for spec in table["inputs"]:
        try:
            cond[spec["name"]] = float(condition[spec["name"]])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"请填写{spec['name']}（{spec.get('unit', '')}）") from None
    pred, outside = predict(table, cond)
    units = {o["name"]: o.get("unit", "") for o in table["outputs"]}
    return {"condition": cond, "outside": outside,
            "expected": [{"name": k, "value": v, "unit": units.get(k, "")} for k, v in pred.items()]}


def reset_table() -> bool:
    """删除数据目录下的基准表，恢复使用随代码提供的默认表。"""
    path = table_path()
    if path.exists():
        path.unlink()
        return True
    return False


def resolve_source(path_text: Optional[str]):
    from pump_test_bench.app.diagnosis.baseline import _files
    from shared.paths import resolve_data_dir
    directory = resolve_data_dir(path_text)
    files = _files(directory)
    if not files:
        raise ValueError(f"目录中没有数据文件：{directory}")
    return directory, files
