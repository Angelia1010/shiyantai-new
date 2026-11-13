"""诊断任务的存储（SQLite）。

每次操作都打开独立的短连接，因此可在多线程的 Web 服务中安全使用；
数据库启用 WAL，读写互不阻塞。

任务状态：
- ``Created``   已创建，等待诊断
- ``Completed`` 诊断完成，已生成报告
- ``Failed``    诊断失败，``error`` 字段记录原因
"""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from shared.config import get_settings

STATUS_CREATED = "Created"
STATUS_COMPLETED = "Completed"
STATUS_FAILED = "Failed"
STATUSES = (STATUS_CREATED, STATUS_COMPLETED, STATUS_FAILED)
MODES = ("realtime", "file", "auto")  # auto：文件写完后由文件服务自动诊断

_SCHEMA = """
CREATE TABLE IF NOT EXISTS diagnosis_tasks (
    task_id     TEXT PRIMARY KEY,
    mode        TEXT NOT NULL,
    path        TEXT NOT NULL,
    file_name   TEXT NOT NULL,
    status      TEXT NOT NULL,
    result      TEXT,
    error       TEXT,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL,
    report_json TEXT,
    report_docx BLOB
);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON diagnosis_tasks (created_at DESC);
"""

_LIST_COLUMNS = "task_id, mode, path, file_name, status, result, error, created_at, updated_at"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _db_path() -> Path:
    return get_settings().db_path


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        _migrate_legacy(conn)


LEGACY_DB_NAME = "your_database_file.db"
_LEGACY_TABLE = "fault_diagnosis_tasks_2"


def _has_table(conn: sqlite3.Connection, schema: str, table: str) -> bool:
    sql = f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=?"
    return conn.execute(sql, (table,)).fetchone() is not None


def _migrate_legacy(conn: sqlite3.Connection) -> None:
    """把旧版 fault_diagnosis_tasks_2 表的数据迁移到新表，仅在新表为空时执行一次。

    旧表可能在当前数据库里，也可能在同目录的旧数据库文件 your_database_file.db 里。
    """
    if conn.execute("SELECT COUNT(*) FROM diagnosis_tasks").fetchone()[0]:
        return
    schema = None
    if _has_table(conn, "main", _LEGACY_TABLE):
        schema = "main"
    else:
        legacy_file = _db_path().parent / LEGACY_DB_NAME
        if legacy_file.is_file() and legacy_file.resolve() != _db_path().resolve():
            conn.execute("ATTACH DATABASE ? AS legacy", (str(legacy_file),))
            if _has_table(conn, "legacy", _LEGACY_TABLE):
                schema = "legacy"
    if schema is None:
        return
    for row in conn.execute(f"SELECT task_id, type, files, status, path, report_data, report_json "
                            f"FROM {schema}.{_LEGACY_TABLE}").fetchall():
        task_id = str(row["task_id"])
        created = int(task_id[:13]) if task_id[:13].isdigit() and len(task_id) >= 13 else _now_ms()
        report = json.loads(row["report_json"]) if row["report_json"] else None
        result = _legacy_result(report)
        conn.execute(
            "INSERT OR IGNORE INTO diagnosis_tasks (task_id, mode, path, file_name, status, result, "
            "created_at, updated_at, report_json, report_docx) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                task_id,
                "file" if row["type"] == "1" else "realtime",
                row["path"] or "",
                row["files"] or "",
                STATUS_COMPLETED if row["status"] == "Completed" else STATUS_CREATED,
                result,
                created,
                created,
                json.dumps(report, ensure_ascii=False) if report else None,
                row["report_data"],
            ),
        )


def _legacy_result(report: Optional[Dict]) -> Optional[str]:
    if not report:
        return None
    fault = (report.get("diagnosis") or {}).get("fault_name", "")
    if fault == "待精确诊断":
        return None
    return "normal" if not fault or "正常" in fault else "abnormal"


def _row_to_task(row: sqlite3.Row) -> Dict:
    return {key: row[key] for key in row.keys() if key not in ("report_json", "report_docx")}


def new_task_id() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]


def create_task(path: str, file_name: str, mode: str) -> Dict:
    if mode not in MODES:
        raise ValueError(f"mode 只能是 {', '.join(MODES)}")
    now = _now_ms()
    task_id = new_task_id()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO diagnosis_tasks (task_id, mode, path, file_name, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (task_id, mode, path, file_name, STATUS_CREATED, now, now),
        )
    return get_task(task_id)


def get_task(task_id: str) -> Optional[Dict]:
    with _connect() as conn:
        row = conn.execute(f"SELECT {_LIST_COLUMNS} FROM diagnosis_tasks WHERE task_id=?", (task_id,)).fetchone()
    return _row_to_task(row) if row else None


def list_tasks(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    mode: Optional[str] = None,
) -> Dict:
    if page < 1:
        raise ValueError("page 从 1 开始")
    if not 1 <= page_size <= 500:
        raise ValueError("page_size 必须在 1 到 500 之间")
    where, params = [], []
    if keyword:
        where.append("(task_id LIKE ? OR file_name LIKE ?)")
        params += [f"%{keyword}%", f"%{keyword}%"]
    if status:
        if status not in STATUSES:
            raise ValueError(f"status 只能是 {', '.join(STATUSES)}")
        where.append("status = ?")
        params.append(status)
    if mode:
        where.append("mode = ?")
        params.append(mode)
    if start_time is not None:
        where.append("created_at >= ?")
        params.append(start_time)
    if end_time is not None:
        where.append("created_at < ?")
        params.append(end_time)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with _connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM diagnosis_tasks {clause}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT {_LIST_COLUMNS} FROM diagnosis_tasks {clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size],
        ).fetchall()
    return {"items": [_row_to_task(r) for r in rows], "total": total, "page": page, "page_size": page_size}


def delete_tasks(task_ids: List[str]) -> int:
    if not task_ids:
        return 0
    placeholders = ",".join("?" for _ in task_ids)
    with _connect() as conn:
        cur = conn.execute(f"DELETE FROM diagnosis_tasks WHERE task_id IN ({placeholders})", list(task_ids))
        return cur.rowcount


def save_report(task_id: str, report: Dict, docx: bytes) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE diagnosis_tasks SET status=?, result=?, error=NULL, report_json=?, report_docx=?, updated_at=? "
            "WHERE task_id=?",
            (STATUS_COMPLETED, report["result"], json.dumps(report, ensure_ascii=False), docx, _now_ms(), task_id),
        )


def mark_failed(task_id: str, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE diagnosis_tasks SET status=?, error=?, updated_at=? WHERE task_id=?",
            (STATUS_FAILED, error[:2000], _now_ms(), task_id),
        )


def get_report(task_id: str) -> Optional[Dict]:
    with _connect() as conn:
        row = conn.execute("SELECT report_json FROM diagnosis_tasks WHERE task_id=?", (task_id,)).fetchone()
    return json.loads(row["report_json"]) if row and row["report_json"] else None


def get_report_docx(task_id: str) -> Optional[bytes]:
    with _connect() as conn:
        row = conn.execute("SELECT report_docx FROM diagnosis_tasks WHERE task_id=?", (task_id,)).fetchone()
    return bytes(row["report_docx"]) if row and row["report_docx"] else None


def list_reports(since: Optional[int] = None, limit: int = 500, exclude: Optional[str] = None) -> List[Dict]:
    """已完成任务的报告，按诊断时间从早到晚：[{task_id, file_name, mode, updated_at, report}]（趋势分析用）。"""
    where, params = ["status = ?", "report_json IS NOT NULL"], [STATUS_COMPLETED]
    if since is not None:
        where.append("updated_at >= ?")
        params.append(since)
    if exclude:
        where.append("task_id != ?")
        params.append(exclude)
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT task_id, file_name, mode, updated_at, report_json FROM diagnosis_tasks "
            f"WHERE {' AND '.join(where)} ORDER BY updated_at DESC LIMIT ?", params + [limit]).fetchall()
    out = []
    for row in reversed(rows):
        try:
            report = json.loads(row["report_json"])
        except ValueError:
            continue
        out.append({"task_id": row["task_id"], "file_name": row["file_name"], "mode": row["mode"],
                    "updated_at": row["updated_at"], "report": report})
    return out
