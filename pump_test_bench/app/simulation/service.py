"""仿真模型的服务层（供任务服务的 /simulation/* 接口使用）：模型列表与状态、后台重建基准表、工况试算、诊断方案。"""
import logging
import threading
import time
from typing import Dict, List, Optional

from pump_test_bench.app.simulation.calibration import build_reference
from pump_test_bench.app.simulation.check import thresholds
from pump_test_bench.app.simulation.config import list_models, load_model_cfg
from pump_test_bench.app.simulation.table import load_table, predict, save_table, table_path

logger = logging.getLogger(__name__)
ENGINE_LABELS = {"surrogate": "数据代理模型（由正常数据拟合）", "formula": "数学公式", "amesim": "AMESim 模型"}

_job_lock = threading.Lock()
_job: Dict = {"state": "idle"}


def job_status() -> Dict:
    with _job_lock:
        return dict(_job)


def _set_job(**kw) -> None:
    with _job_lock:
        _job.update(kw)


def start_build(model_id: str, paths, engine: str, source: str, operator: str) -> Dict:
    """后台建立某个模型的基准表；同一时间只允许一个任务（AMESim 不能并行）。"""
    mcfg = load_model_cfg(model_id)
    with _job_lock:
        if _job.get("state") == "running":
            raise RuntimeError(f"“{_job.get('model_name')}”的基准表正在建立，请等待完成")
        _job.clear()
        _job.update({"state": "running", "model_id": model_id, "model_name": mcfg["name"], "engine": engine,
                     "source": source, "operator": operator, "stage": "准备", "done": 0, "total": 0,
                     "started": int(time.time() * 1000), "error": None})

    def progress(stage, done, total):
        _set_job(stage=stage, done=done, total=total)

    def work():
        try:
            table = build_reference(list(paths), mcfg, engine, progress, source=source)
            save_table(table)
            _set_job(state="done", stage="完成", finished=int(time.time() * 1000),
                     result={"created": table["created"], "files": table["calibration"]["files"],
                             "model": table["model"]["label"]})
            logger.info("用户 %s 重建仿真基准表：%s（%s，%s）", operator, mcfg["name"], engine, source)
        except Exception as exc:  # 失败原因返回给前端
            logger.exception("建立仿真基准表失败：%s", model_id)
            _set_job(state="failed", error=str(exc), finished=int(time.time() * 1000))

    threading.Thread(target=work, name=f"simulation-{model_id}", daemon=True).start()
    return job_status()


def _engines(mcfg: Dict) -> List[Dict]:
    """该模型可选的引擎：配置的引擎 + 代理模型 + AMESim（amesim 段补全后可用）。"""
    configured = mcfg["engine"]["type"]
    out = []
    for kind in dict.fromkeys([configured, "surrogate", "amesim"]):
        ready = kind != "amesim" or "待填写" not in str(mcfg.get("amesim", {}))
        out.append({"type": kind, "label": ENGINE_LABELS.get(kind, kind), "ready": ready,
                    "note": "" if ready else f"{mcfg['id']}.json 的 amesim 段还有“待填写”项"})
    return out


def model_status(mcfg: Dict, profile: Dict) -> Dict:
    table = load_table(mcfg["id"])
    info = None
    if table:
        kinds = {o["name"]: o["kind"] for o in mcfg["outputs"]}
        units = {o["name"]: o.get("unit", "") for o in mcfg["outputs"]}
        calib = table.get("calibration") or {}
        setting = profile.get(mcfg["id"], {})
        columns = []
        for col, c in calib.get("columns", {}).items():
            warn, alarm = thresholds(mcfg.get("thresholds", {}), kinds.get(c["output"], "flow"), c.get("std"), setting)
            columns.append({"column": col, "output": c["output"], "mode": c.get("mode", "relative"),
                            "unit": units.get(c["output"], ""), "bias": c["bias"], "bias_slope": c.get("bias_slope", 0),
                            "std": c["std"], "warn": warn, "alarm": alarm, "n": c.get("n")})
        info = {"created": table.get("created"), "model": table.get("model", {}), "source": table.get("source", ""),
                "is_default": bool(table.get("_default")), "inputs": table["inputs"], "outputs": table["outputs"],
                "calibration": {"files": calib.get("files"), "method": calib.get("method"), "columns": columns}}
    return {
        "id": mcfg["id"], "name": mcfg["name"], "description": mcfg.get("description", ""),
        "components": mcfg.get("components", []), "engine": mcfg["engine"]["type"], "engines": _engines(mcfg),
        "inputs": [{k: i.get(k) for k in ("name", "column", "columns", "derived", "temperature_column", "unit", "grid")}
                   for i in mcfg["inputs"]],
        "outputs": [{k: o.get(k) for k in ("name", "unit", "kind", "columns", "single")} for o in mcfg["outputs"]],
        "rules": mcfg.get("rules", {}), "media": mcfg.get("media"), "table": info,
        "setting": profile.get(mcfg["id"], {}),
    }


def status() -> Dict:
    from pump_test_bench.app.diagnosis.settings import MODES, profile
    prof = profile()
    return {"models": [model_status(m, prof) for m in list_models()], "job": job_status(), "modes": MODES}


def try_predict(model_id: str, condition: Dict) -> Dict:
    table = load_table(model_id)
    if not table:
        raise ValueError("该模型还没有仿真基准表，请先建立")
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


def reset_table(model_id: str) -> bool:
    """删除数据目录下该模型的基准表，恢复使用随代码提供的默认表。"""
    load_model_cfg(model_id)
    path = table_path(model_id)
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
