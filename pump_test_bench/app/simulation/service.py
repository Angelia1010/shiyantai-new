"""仿真模型的服务层（供任务服务的 /simulation/* 接口使用）：模型列表与状态、后台建立模型、预览拟合、工况试算、
派生测点设置。只做编排，算法在 surrogate / builders / calibration / table 中。"""
import logging
import threading
import time
from typing import Dict, List, Optional

from pump_test_bench.app.simulation.builders import ROLES, list_builders
from pump_test_bench.app.simulation.calibration import MIN_FILES, build_reference, collect_samples
from pump_test_bench.app.simulation.check import thresholds
from pump_test_bench.app.simulation.config import (
    KINDS, SURROGATE, builtin_ids, delete_user_model, deleted_builtins, is_surrogate, list_models, load_model_cfg,
    save_user_model, set_builtin_hidden, validate_model
)
from pump_test_bench.app.simulation.models import ENGINE_LABELS as GRID_ENGINE_LABELS
from pump_test_bench.app.simulation.table import delete_user_table, is_stale, load_table, predict, save_table, table_path

logger = logging.getLogger(__name__)
ENGINE_LABELS = {SURROGATE: "数据代理模型", **GRID_ENGINE_LABELS}

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
    """建立模型时可选的引擎：模型自己的方式（仿真软件的配置补全后才可用）。"""
    kind = mcfg["engine"]["type"]
    ready = kind == SURROGATE or "待填写" not in str(mcfg.get(kind, {}))
    return [{"type": kind, "label": ENGINE_LABELS.get(kind, kind), "ready": ready,
             "note": "" if ready else f"请先在“编辑配置”中补全 {ENGINE_LABELS.get(kind, kind)} 的设置"}]


def _formula_summary(table: Dict) -> Dict:
    out = {}
    for name, f in (table.get("formulas") or {}).items():
        out[name] = {k: f.get(k) for k in ("method", "expression", "coefficients", "display", "info", "fitted_from_data",
                                           "assessment")}
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
            warn, alarm = thresholds(mcfg.get("thresholds", {}), kinds.get(c["output"], "flow"), c.get("std"), setting,
                                     c.get("mode", "relative"))
            columns.append({"column": col, "output": c["output"], "mode": c.get("mode", "relative"),
                            "unit": units.get(c["output"], ""), "bias": c["bias"], "std": c["std"], "warn": warn,
                            "alarm": alarm, "n": c.get("n"), "warning": c.get("warning")})
        info = {"created": table.get("created"), "model": table.get("model", {}), "source": table.get("source", ""),
                "kind": table.get("kind", "grid"), "is_default": bool(table.get("_default")),
                "stale": is_stale(table, mcfg), "inputs": table["inputs"], "outputs": table["outputs"],
                "roles": table.get("roles"), "formulas": _formula_summary(table),
                "calibration": {"files": calib.get("files"), "method": calib.get("method"), "columns": columns,
                                "failed_outputs": calib.get("failed_outputs") or {}}}
    methods = sorted({o.get("method", "autofit") for o in mcfg["outputs"]}) if is_surrogate(mcfg) else []
    return {
        "id": mcfg["id"], "name": mcfg["name"], "description": mcfg.get("description", ""),
        "source": mcfg.get("_source", "builtin"),
        "config": {k: v for k, v in mcfg.items() if not k.startswith("_")},
        "components": mcfg.get("components", []), "engine": mcfg["engine"]["type"], "engines": _engines(mcfg),
        "methods": methods,
        "inputs": [{k: i.get(k) for k in ("name", "column", "columns", "derived", "temperature_column", "unit", "grid")}
                   for i in mcfg["inputs"]],
        "outputs": [{k: o.get(k) for k in ("name", "unit", "kind", "columns", "single")} for o in mcfg["outputs"]],
        "rules": mcfg.get("rules", {}), "media": mcfg.get("media"), "table": info,
        "setting": profile.get(mcfg["id"], {}),
    }


def status() -> Dict:
    from pump_test_bench.app.diagnosis.settings import MODES, profile
    prof = profile()
    return {"models": [model_status(m, prof) for m in list_models()], "deleted_builtins": deleted_builtins(),
            "job": job_status(), "modes": MODES, "kinds": KINDS, "engine_labels": ENGINE_LABELS,
            "builders": list_builders(), "roles": ROLES}


def save_model(data: Dict, model_id: Optional[str] = None) -> Dict:
    """新建（model_id 为空）或修改模型配置。改了输入、输出后旧基准表作废，需要重建。"""
    existing = {m["id"] for m in list_models()}
    if model_id is None and str(data.get("id", "")).strip() in {m["id"] for m in deleted_builtins()}:
        raise ValueError(f"模型编号 {data.get('id')} 属于已删除的内置模型，请换一个编号，或先恢复该内置模型")
    if model_id is None and str(data.get("id", "")).strip() in existing:
        raise ValueError(f"模型编号 {data.get('id')} 已存在，请换一个")
    if model_id is not None and model_id not in existing:
        raise ValueError(f"没有这个仿真模型：{model_id}")
    from pump_test_bench.app.diagnosis.settings import profile
    cfg = validate_model(data, model_id)
    if model_id is None:
        cfg.setdefault("order", 10 + len(existing))
    save_user_model(cfg)
    return model_status(load_model_cfg(cfg["id"]), profile())


def delete_model(model_id: str, restore: bool = False) -> Dict:
    """删除模型（连同重建的基准表）。内置模型删除后从列表中隐藏，可在页面上恢复；
    restore=True 时只放弃对内置模型配置的修改，恢复为内置配置。"""
    cfg = load_model_cfg(model_id)
    is_builtin = model_id in builtin_ids()
    if restore:
        if cfg.get("_source") != "override":
            raise ValueError("该模型没有修改过的配置可以恢复")
        delete_user_model(model_id)
        return {"removed": model_id, "restored": True}
    delete_user_model(model_id)
    delete_user_table(model_id)
    if is_builtin:
        set_builtin_hidden(model_id, True)
    return {"removed": model_id, "restored": False}


def restore_builtin(model_id: str) -> Dict:
    """恢复已删除的内置模型（使用内置配置与默认基准表）。"""
    if model_id not in [m["id"] for m in deleted_builtins()]:
        raise ValueError(f"没有已删除的内置模型：{model_id}")
    set_builtin_hidden(model_id, False)
    return {"restored": model_id}


def known_columns() -> List[str]:
    """可选的测点列（试验台导出文件的表头）。"""
    from pump_test_bench.app.core.known_headers import HEADER_V2
    from pump_test_bench.app.core.table_parser import normalize_column
    cols = [normalize_column(h)[0] for h in HEADER_V2 if h.strip()]
    return [c for c in dict.fromkeys(cols) if c and c != "时间"]


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


def preview(data: Dict, path_text: str, outputs: Optional[List[str]] = None) -> Dict:
    """不保存：按提交的配置用某个正常数据目录拟合并评估（编辑页的“验证公式”“试拟合”）。"""
    cfg = validate_model(dict(data, id=data.get("id") or "preview"), data.get("id") or "preview")
    if not is_surrogate(cfg):
        raise ValueError("只有数据代理模型可以预览拟合")
    from pump_test_bench.app.simulation.surrogate import fit_model
    _, files = resolve_source(path_text)
    samples = collect_samples(files, cfg)
    if len(samples) < MIN_FILES:
        need = "；".join(c.get("note") or c["column"] for c in cfg.get("active_if") or [])
        raise ValueError(f"可用的正常数据只有 {len(samples)} 个文件（需要有稳定段、变量齐全"
                         + (f"、且{need}" if need else "") + f"），至少需要 {MIN_FILES} 个")
    fitted = fit_model(samples, cfg, outputs)
    result = {}
    for name, r in fitted["outputs"].items():
        result[name] = {k: v for k, v in r.items() if not k.startswith("_") and k != "refit"}
    return {"files": len(samples), "groups": sorted({str(g) for g in fitted["data"]["groups"]}),
            "roles": fitted["roles"], "ranges": fitted["ranges"], "outputs": result,
            "excluded": cfg.get("exclude_files", [])}


def derived_settings() -> List[Dict]:
    from pump_test_bench.app.signals import derived_specs
    return [{"name": k, **v} for k, v in derived_specs().items()]


def save_derived(items: List[Dict]) -> List[Dict]:
    from pump_test_bench.app.signals import save_derived_override
    save_derived_override(items)
    return derived_settings()


def resolve_source(path_text: Optional[str]):
    from pump_test_bench.app.diagnosis.baseline import _files
    from shared.paths import resolve_data_dir
    directory = resolve_data_dir(path_text)
    files = _files(directory)
    if not files:
        raise ValueError(f"目录中没有数据文件：{directory}")
    return directory, files
