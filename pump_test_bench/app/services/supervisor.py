"""一键运行（安装包部署用）：启动并守护全部后端服务，并在本进程中运行统一入口（gateway）。

    python -m pump_test_bench.app.services.supervisor [--env D:\\...\\.env]

- 读取 .env（--env 指定，或环境变量 BENCH_ENV_FILE，或仓库根目录 .env），子进程继承同一份配置；
- 子服务：任务服务、文件服务；ENABLE_LLM=1 时加大模型分析服务；ENABLE_AMESIM=1 且设置了 AME（AMESim 安装目录）时
  用 AMESim 自带的 Python 启动 AMESim 服务；
- 某个服务退出后自动重启（间隔逐步加长，最长 60 秒；运行满 5 分钟后重新计）；
- Windows 上子进程放进“作业对象”：本进程被结束（如停止计划任务）时，子进程随之结束，不会残留；
- 各服务输出写到日志目录的 <服务>.out.log，本进程写 supervisor.log。
"""
import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("supervisor")
IS_WINDOWS = os.name == "nt"


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


class _Job:
    """Windows 作业对象：关闭时结束其中所有进程。"""

    def __init__(self):
        self.handle = None
        if not IS_WINDOWS:
            return
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class BasicLimit(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                         "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class ExtendedLimit(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimit), ("IoInfo", IoCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        self.k32 = k32
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        self.handle = k32.CreateJobObjectW(None, None)
        info = ExtendedLimit()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        k32.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info))  # 9 = Extended

    def add(self, proc: subprocess.Popen) -> None:
        if self.handle:
            self.k32.AssignProcessToJobObject(self.handle, int(proc._handle))  # noqa: SLF001


class Service:
    def __init__(self, name: str, cmd: List[str], cwd: Path, log_dir: Path, env: Dict[str, str]):
        self.name, self.cmd, self.cwd, self.log_dir, self.env = name, cmd, cwd, log_dir, env
        self.proc: Optional[subprocess.Popen] = None
        self.started = 0.0
        self.backoff = 2.0
        self.next_start = 0.0

    def start(self, job: _Job) -> None:
        out = open(self.log_dir / f"{self.name}.out.log", "ab")
        flags = 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW：不弹出命令行窗口
        self.proc = subprocess.Popen(self.cmd, cwd=str(self.cwd), env=self.env, stdout=out, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, creationflags=flags)
        out.close()
        job.add(self.proc)
        self.started = time.time()
        logger.info("已启动 %s（pid %s）", self.name, self.proc.pid)

    def check(self, job: _Job) -> None:
        now = time.time()
        if self.proc is None:
            if now >= self.next_start:
                self.start(job)
            return
        code = self.proc.poll()
        if code is None:
            if now - self.started > 300:
                self.backoff = 2.0
            return
        logger.warning("%s 已退出（代码 %s），%.0f 秒后重启；详见 %s.out.log", self.name, code, self.backoff, self.name)
        self.proc = None
        self.next_start = now + self.backoff
        self.backoff = min(self.backoff * 2, 60.0)

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _ensure_amesim_deps(ame_py: Path, root: Path) -> None:
    """AMESim 自带的 Python 需要 flask、requests；缺少时尝试安装一次（需要联网，失败时在日志中说明）。"""
    check = subprocess.run([str(ame_py), "-c", "import flask, requests"], capture_output=True)
    if check.returncode == 0:
        return
    logger.info("AMESim 的 Python 缺少依赖，尝试安装 AMESim_server/requirements.txt")
    r = subprocess.run([str(ame_py), "-m", "pip", "install", "-r", str(root / "AMESim_server" / "requirements.txt")],
                       capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        logger.warning("安装失败（%s）。请在能联网时以管理员身份运行：\"%s\" -m pip install flask requests",
                       (r.stderr or r.stdout).strip()[-300:], ame_py)


def build_services(root: Path, log_dir: Path) -> List[Service]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    py = sys.executable
    if IS_WINDOWS and py.lower().endswith("pythonw.exe"):  # 子服务用控制台版本，输出才能写进日志
        py = py[:-len("pythonw.exe")] + "python.exe"
    modules = [("task_service", "pump_test_bench.app.services.task_service"),
               ("file_service", "pump_test_bench.app.services.file_service")]
    if _flag("ENABLE_LLM"):
        modules.append(("llm_service", "pump_test_bench.app.services.llm_service"))
    services = [Service(name, [py, "-m", mod], root, log_dir, env) for name, mod in modules]
    ame = os.environ.get("AME", "").strip()
    if _flag("ENABLE_AMESIM"):
        ame_py = Path(ame) / "sys" / "python" / "win64" / "python.exe" if ame else None
        if ame_py and ame_py.is_file():
            _ensure_amesim_deps(ame_py, root)
            services.append(Service("amesim_service", [str(ame_py), "-m", "AMESim_server.src.AmeSimuSessionServer"],
                                    root, log_dir, env))
        else:
            logger.warning("ENABLE_AMESIM=1，但没有找到 AMESim 自带的 Python（AME=%s），不启动 AMESim 服务", ame or "未设置")
    return services


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="启动并守护全部后端服务与统一入口")
    parser.add_argument("--env", help=".env 文件路径（安装包部署时在 ProgramData 下）")
    args = parser.parse_args(argv)
    if args.env:
        os.environ["BENCH_ENV_FILE"] = str(Path(args.env).resolve())

    from shared.config import REPO_ROOT, _load_dotenv, env_file, get_settings
    _load_dotenv(env_file())  # 子进程与入口共用同一份配置
    from shared.logging_setup import setup_logging
    setup_logging("supervisor")
    settings = get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    log_dir = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    pid_file = settings.db_path.parent / "supervisor.pid"
    pid_file.write_text(str(os.getpid()), encoding="ascii")

    job = _Job()
    services = build_services(REPO_ROOT, log_dir)
    stop = threading.Event()

    def on_signal(*_):
        stop.set()
    for sig in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGBREAK", None)):
        if sig is not None:
            signal.signal(sig, on_signal)

    from pump_test_bench.app.services.gateway import make_server, web_root
    server = make_server()
    threading.Thread(target=server.serve_forever, name="gateway", daemon=True).start()
    host, port = server.server_address[:2]
    logger.info("系统已启动：http://%s:%s（页面：%s；配置：%s）", "localhost" if host in ("0.0.0.0", "127.0.0.1") else host,
                port, web_root(), env_file())
    try:
        while not stop.is_set():
            for s in services:
                s.check(job)
            stop.wait(2.0)
    finally:
        logger.info("正在停止…")
        server.shutdown()
        for s in services:
            s.stop()
        try:
            pid_file.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
