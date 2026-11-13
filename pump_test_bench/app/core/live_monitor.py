"""实时监控：定时扫描数据目录，增量读取正在写入的文件，按时间窗聚合成特征帧。

为什么用定时扫描而不是文件系统通知：试验台通过网络共享（SMB）写文件，共享盘上的
变化通知可能漏发、乱序，定时比较“文件大小 + 修改时间”更可靠，代价只是每秒扫一次目录。

工作方式：
- 每 scan_interval 秒扫描一次目录（含子目录），找出大小或修改时间变化的数据文件；
- 最近在变化的那个文件就是“当前文件”，用 TailReader 只读新增的完整行，
  按时间列每 window 秒聚合成一帧 {t, time, rows, stats: {列名: {avg, min, max}}}，
  放进环形缓冲区，前端按序号增量取；
- 文件停止变化 settle_seconds 秒后视为写完，发布一条“文件完成”事件；开启自动诊断时
  同时调用 on_complete(相对路径, 目录)，由文件服务排队诊断；
- 监控目录与自动诊断开关写入状态文件，服务重启后自动恢复。

帧和事件都带递增序号，多个页面各自记住读到的序号，互不影响。
"""
import json
import logging
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Deque, Dict, List, Optional, Tuple

from pump_test_bench.app.core.table_parser import TEXT_SUFFIXES, Layout, TailReader, is_number, parse_time

logger = logging.getLogger(__name__)

MAX_SCAN_DEPTH = 4
MAX_SCAN_FILES = 5000
FALLBACK_ROW_RATE = 100.0  # 没有时间列时按 100 行/秒估算


def _fmt_time(seconds: float) -> str:
    s = int(seconds) % 86400
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


class FrameAggregator:
    """把数据行按时间窗聚合为特征帧。时间列缺失或无法解析时按行号估算时间。"""

    def __init__(self, layout: Layout, window: float = 1.0) -> None:
        self.columns = layout.columns
        self.window = window
        self.time_idx = layout.columns.index(layout.time_column) if layout.time_column else None
        self._key: Optional[int] = None
        self._acc: Dict[int, List[float]] = {}
        self._rows = 0
        self._row_counter = 0
        self._last_raw: Optional[float] = None
        self._offset = 0.0

    def _time_of(self, row: List[str]) -> float:
        self._row_counter += 1
        raw = parse_time(row[self.time_idx]) if self.time_idx is not None else None
        if raw is None:
            return self._row_counter / FALLBACK_ROW_RATE
        if self._last_raw is not None and raw < self._last_raw - 30:
            # 时间回绕：“时:分:秒”过午夜加一天，“分:秒”格式过整点加一小时
            self._offset += 86400 if self._last_raw >= 3600 else 3600
        self._last_raw = raw
        return raw + self._offset

    def add(self, rows: List[List[str]]) -> List[Dict]:
        frames = []
        for row in rows:
            key = math.floor(self._time_of(row) / self.window)
            if self._key is not None and key != self._key and self._rows:
                frames.append(self._emit())
            self._key = key
            self._rows += 1
            for i, value in enumerate(row):
                if i == self.time_idx or not value or not is_number(value):
                    continue
                v = float(value)
                acc = self._acc.get(i)
                if acc is None:
                    self._acc[i] = [v, v, v, 1]
                else:
                    acc[0] += v
                    acc[1] = min(acc[1], v)
                    acc[2] = max(acc[2], v)
                    acc[3] += 1
        return frames

    def flush(self) -> Optional[Dict]:
        return self._emit() if self._rows else None

    def _emit(self) -> Dict:
        t = self._key * self.window
        stats = {
            self.columns[i]: {"avg": round(s / n, 6), "min": round(lo, 6), "max": round(hi, 6)}
            for i, (s, lo, hi, n) in self._acc.items()
        }
        frame = {"t": t, "time": _fmt_time(t), "rows": self._rows, "stats": stats}
        self._acc = {}
        self._rows = 0
        return frame


@dataclass
class _Current:
    rel: str
    reader: TailReader
    aggregator: Optional[FrameAggregator] = None
    finished: bool = False
    rows: int = 0
    last_row_wall: float = 0.0


@dataclass
class LiveMonitor:
    scan_interval: float = 1.0
    settle_seconds: float = 3.0
    active_seconds: float = 5.0
    window: float = 1.0
    max_frames: int = 3600
    max_events: int = 1000
    state_file: Optional[Path] = None
    suffixes: Tuple[str, ...] = TEXT_SUFFIXES
    auto_diagnose: bool = True
    on_complete: Optional[Callable[[str, Path], None]] = None

    directory: Optional[Path] = field(default=None, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: Optional[threading.Thread] = field(default=None, init=False, repr=False)
    _snapshot: Dict[str, Tuple[int, float]] = field(default_factory=dict, init=False, repr=False)
    _baseline: set = field(default_factory=set, init=False, repr=False)
    _changed_at: Dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _current: Optional[_Current] = field(default=None, init=False, repr=False)
    _frames: Deque[Dict] = field(default=None, init=False, repr=False)
    _events: Deque[Dict] = field(default=None, init=False, repr=False)
    _frame_seq: int = field(default=0, init=False)
    _event_seq: int = field(default=0, init=False)
    _last_error: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self._frames = deque(maxlen=self.max_frames)
        self._events = deque(maxlen=self.max_events)

    # ------------------------------------------------------------------ 控制
    def watch(self, directory: Path, start_thread: bool = True, auto_diagnose: Optional[bool] = None) -> None:
        """切换监控目录。已有文件只记录为基线，正在写入的文件（最近有修改）立即开始读取。"""
        with self._lock:
            if auto_diagnose is not None:
                self.auto_diagnose = bool(auto_diagnose)
            self.directory = directory
            self._snapshot = self._list_files()
            self._baseline = set(self._snapshot)
            self._changed_at = {}
            self._current = None
            self._frames.clear()
            now_wall = time.time()
            active = [(mtime, rel) for rel, (_, mtime) in self._snapshot.items()
                      if now_wall - mtime <= self.active_seconds]
            if active:
                rel = max(active)[1]
                self._switch_to(rel)
                self._changed_at[rel] = time.monotonic()
            self._save_state()
        logger.info("开始监控目录：%s", directory)
        if start_thread:
            self._ensure_thread()

    def restore(self, resolve: Callable[[str], Path]) -> None:
        """服务启动时恢复上次的监控目录；目录失效则忽略。"""
        if not self.state_file or not self.state_file.is_file():
            return
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
            if state.get("path"):
                self.watch(resolve(state["path"]), auto_diagnose=state.get("auto_diagnose", True))
        except Exception as exc:  # 目录被删除、不再允许访问等
            logger.warning("无法恢复监控目录：%s", exc)

    def set_auto_diagnose(self, enabled: bool) -> None:
        with self._lock:
            self.auto_diagnose = bool(enabled)
            self._save_state()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _ensure_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="live-monitor", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.scan_interval):
            try:
                self.scan()
                self._last_error = ""
            except Exception as exc:  # 共享盘断开等：记录后继续，下一轮重试
                if str(exc) != self._last_error:
                    logger.exception("扫描数据目录失败")
                self._last_error = str(exc)

    def _save_state(self) -> None:
        if not self.state_file:
            return
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps({"path": str(self.directory), "auto_diagnose": self.auto_diagnose},
                                                  ensure_ascii=False), encoding="utf-8")
        except OSError:
            logger.warning("保存监控目录失败：%s", self.state_file)

    # ------------------------------------------------------------------ 扫描
    def _list_files(self) -> Dict[str, Tuple[int, float]]:
        result: Dict[str, Tuple[int, float]] = {}
        if not self.directory:
            return result
        root = str(self.directory)
        for dirpath, dirnames, filenames in os.walk(root):
            depth = os.path.relpath(dirpath, root).count(os.sep) + (dirpath != root)
            dirnames[:] = [d for d in dirnames if not d.startswith(".")] if depth < MAX_SCAN_DEPTH else []
            for name in filenames:
                if not name.lower().endswith(self.suffixes) or name.startswith((".", "~$")):
                    continue
                full = os.path.join(dirpath, name)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                result[os.path.relpath(full, root).replace(os.sep, "/")] = (st.st_size, st.st_mtime)
                if len(result) >= MAX_SCAN_FILES:
                    return result
        return result

    def scan(self, now: Optional[float] = None) -> None:
        """扫描一次（后台线程每秒调用；测试中可直接调用并传入单调时钟时间）。"""
        now = time.monotonic() if now is None else now
        with self._lock:
            if not self.directory:
                return
            files = self._list_files()
            changed = [rel for rel, sig in files.items() if self._snapshot.get(rel) != sig]
            for rel in changed:
                self._changed_at[rel] = now
            for rel in set(self._changed_at) - set(files):  # 文件被删除
                del self._changed_at[rel]
            self._snapshot = files

            # 正在变化的文件里修改时间最新的作为当前文件
            if changed:
                newest = max(changed, key=lambda r: files[r][1])
                cur = self._current
                if cur is None or (newest != cur.rel and (cur.finished or files[newest][1] >= files.get(cur.rel, (0, 0))[1])):
                    self._switch_to(newest)
                elif newest == cur.rel:
                    cur.finished = False
            self._read_current(now)
            self._publish_completed(now)

    def _switch_to(self, rel: str) -> None:
        if self._current and not self._current.finished:
            self._finish_current()
        self._current = _Current(rel=rel, reader=TailReader(self.directory / rel))
        logger.info("实时读取文件：%s", rel)

    def _read_current(self, now: float) -> None:
        cur = self._current
        if cur is None or cur.finished:
            return
        self._push(cur, cur.reader.read_new())
        changed_at = self._changed_at.get(cur.rel)
        if changed_at is None or now - changed_at >= self.settle_seconds:
            self._finish_current()

    def _finish_current(self) -> None:
        cur = self._current
        self._push(cur, cur.reader.read_new(final=True))
        if cur.aggregator:
            frame = cur.aggregator.flush()
            if frame:
                self._append_frame(cur, frame)
        cur.finished = True

    def _push(self, cur: _Current, rows: List[List[str]]) -> None:
        if not rows:
            return
        if cur.aggregator is None:
            cur.aggregator = FrameAggregator(cur.reader.layout, self.window)
        cur.rows += len(rows)
        cur.last_row_wall = time.time()
        for frame in cur.aggregator.add(rows):
            self._append_frame(cur, frame)

    def _append_frame(self, cur: _Current, frame: Dict) -> None:
        self._frame_seq += 1
        frame["seq"] = self._frame_seq
        frame["file"] = cur.rel
        self._frames.append(frame)

    def _publish_completed(self, now: float) -> None:
        for rel, at in list(self._changed_at.items()):
            if now - at < self.settle_seconds:
                continue
            del self._changed_at[rel]
            self._event_seq += 1
            self._events.append({
                "seq": self._event_seq,
                "type": "modified" if rel in self._baseline else "created",
                "file_name": rel,
                "directory": str(self.directory),
                "time": int(time.time() * 1000),
            })
            self._baseline.add(rel)
            if self.auto_diagnose and self.on_complete:
                try:
                    self.on_complete(rel, self.directory)
                except Exception:
                    logger.exception("提交自动诊断失败：%s", rel)

    # ------------------------------------------------------------------ 查询
    def status(self) -> Dict:
        with self._lock:
            cur = self._current
            live = bool(cur and not cur.finished and time.time() - cur.last_row_wall <= self.active_seconds)
            layout = cur.reader.layout if cur else None
            return {
                "path": str(self.directory) if self.directory else None,
                "state": "off" if not self.directory else ("live" if live else "waiting"),
                "file": cur.rel if cur else None,
                "file_rows": cur.rows if cur else 0,
                "columns": len(layout.columns) if layout else 0,
                "header_source": layout.header_source if layout else None,
                "skipped_rows": (cur.reader.stats.short_rows + cur.reader.stats.bad_rows) if cur else 0,
                "updated_at": int(cur.last_row_wall * 1000) if cur and cur.last_row_wall else None,
                "latest_seq": self._frame_seq,
                "auto_diagnose": self.auto_diagnose,
                "error": self._last_error or None,
            }

    def frames_since(self, since: int, limit: int = 300) -> Dict:
        """序号 since 之后的帧。since 早于缓冲区（或为 0）时只返回最近 limit 帧。"""
        with self._lock:
            frames = [f for f in self._frames if f["seq"] > since]
            if len(frames) > limit:
                frames = frames[-limit:]
            status = self.status()
            return {"latest_seq": self._frame_seq, "state": status["state"], "file": status["file"],
                    "path": status["path"], "auto_diagnose": status["auto_diagnose"], "frames": frames}

    def events_since(self, since: int) -> Dict:
        with self._lock:
            return {
                "latest_seq": self._event_seq,
                "directory": str(self.directory) if self.directory else None,
                "events": [e for e in self._events if e["seq"] > since],
            }
