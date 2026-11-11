"""执行一次诊断并保存报告（任务服务的接口和文件服务的自动诊断共用）。"""
import logging
from pathlib import Path
from typing import Dict, Optional

from pump_test_bench.app.core.report import build_report, render_docx
from pump_test_bench.app.db import tasks as repo
from pump_test_bench.app.diagnosis.engine import diagnose_file

logger = logging.getLogger(__name__)


def run_task_diagnosis(task: Dict, path: Path, operator: str, density: Optional[float] = None,
                       simulation: Optional[Dict] = None) -> Dict:
    """诊断任务对应的文件，保存报告并返回；失败时把任务标记为 Failed 再抛出。"""
    try:
        body = diagnose_file(path, density=density, simulation=simulation)
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
