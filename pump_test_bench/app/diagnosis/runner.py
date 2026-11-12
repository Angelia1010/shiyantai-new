"""执行一次诊断并保存报告（任务服务的接口和文件服务的自动诊断共用）。"""
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

from pump_test_bench.app.core.report import build_report, render_docx
from pump_test_bench.app.db import tasks as repo
from pump_test_bench.app.diagnosis import settings as diag_settings
from pump_test_bench.app.diagnosis.config import load_config
from pump_test_bench.app.diagnosis.engine import diagnose_file
from pump_test_bench.app.diagnosis.history import DEFAULTS as HISTORY_DEFAULTS, analyze_history

logger = logging.getLogger(__name__)


def run_task_diagnosis(task: Dict, path: Path, operator: str, density: Optional[float] = None) -> Dict:
    """诊断任务对应的文件，保存报告并返回；失败时把任务标记为 Failed 再抛出。

    density：当前燃油 20 ℃ 密度（kg/m³）；不传时用前端“诊断设置”里保存的值，仍没有则用健康基准的密度模型。
    """
    try:
        if density is None:
            density = diag_settings.fuel_density_20()
        body = diagnose_file(path, density=density)
        _attach_history(task, body)
        report = build_report(task, body, operator=operator)
        repo.save_report(task["task_id"], report, render_docx(report))
        return report
    except ValueError as exc:
        repo.mark_failed(task["task_id"], str(exc))
        raise
    except Exception:
        logger.exception("诊断任务 %s 失败", task["task_id"])
        repo.mark_failed(task["task_id"], "诊断过程出现内部错误，请查看服务日志")
        raise


# 历史分为两类分别统计：试验台实时数据（自动诊断、实时诊断）与手动选择的文件（可能是旧数据或故障注入数据）
_LIVE_MODES = ("auto", "realtime")


def same_source(mode: str):
    return _LIVE_MODES if mode in _LIVE_MODES else (mode,)


def past_reports(task: Dict, days: float) -> List[Dict]:
    """同类来源、时间窗内的历次报告（同一文件多次诊断只取最近一次），按时间从早到晚。"""
    since = int((time.time() - days * 86400) * 1000)
    modes = same_source(task.get("mode", ""))
    latest: Dict[str, Dict] = {}
    for item in repo.list_reports(since=since, limit=300, exclude=task["task_id"]):
        if item["mode"] in modes and item["file_name"] != task.get("file_name"):
            latest[item["file_name"]] = item
    return [i["report"] for i in sorted(latest.values(), key=lambda i: i["updated_at"])]


def _attach_history(task: Dict, body: Dict) -> None:
    """长期漂移、质量流量计零点/标定拆分。只作补充，失败不影响本次诊断。"""
    try:
        cfg = load_config()
        days = {**HISTORY_DEFAULTS, **cfg.get("history", {})}["window_days"]
        hist = analyze_history(body, past_reports(task, days), cfg)
    except Exception:
        logger.exception("历史趋势分析失败（不影响本次诊断）")
        return
    if not hist:
        return
    body["history"] = hist
    notes = [f["detail"] for f in hist["findings"]]
    split = hist.get("mass_split")
    if split:
        for cause in body.get("causes", []):
            if cause.get("target") == split.get("column") or "零点或标定" in cause.get("name", ""):
                cause["explanation"] += "。" + split["text"]
                cause["name"] = cause["name"].replace("零点或标定漂移", split["kind"])
        body["summary"] = body.get("summary", "").replace("零点或标定漂移", split["kind"])
        diag = body.get("diagnosis") or {}
        if diag.get("fault_name"):
            diag["fault_name"] = diag["fault_name"].replace("零点或标定漂移", split["kind"])
        notes.append(split["text"])
    if notes:
        body["repair_advice"] = (body.get("repair_advice", "") + "\n历史趋势（不影响本次结论）：" + "；".join(notes)).strip()
