"""安装包用的配置与服务管理工具（由安装程序调用，也可以手动运行）。

用法（在安装目录下，用自带的 Python）：
    python\\python.exe installer_tools.py configure --home <数据目录> --port 8080 [--lan] [--llm] [--amesim --ame <AMESim 目录>]
                                         [--password-file <文件>]
    python\\python.exe installer_tools.py install-task      注册开机自动运行（Windows 计划任务，系统账户，后台运行）
    python\\python.exe installer_tools.py start | stop | restart | status
    python\\python.exe installer_tools.py wait-ready [--timeout 90]
    python\\python.exe installer_tools.py uninstall [--purge]   停止并删除计划任务、防火墙规则；--purge 同时删除数据目录

目录约定（安装目录 = 本文件所在目录）：
    python\\        自带的 Python 运行环境
    app\\           程序（shared、pump_test_bench、AMESim_server）
    web\\           前端页面
    <数据目录>\\     .env、数据库、日志、用户建的模型等（默认 C:\\ProgramData\\BenchCheck），升级、重装时保留
数据目录写在安装目录下的 home.txt 中，其他命令据此找到它。
"""
import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

APP_DIR = Path(__file__).resolve().parent
TASK_NAME = "BenchCheck"
FIREWALL_RULE = "BenchCheck 标准台校验系统"
IS_WINDOWS = os.name == "nt"


# --------------------------------------------------------------------------- 工具
def home_dir(explicit: Optional[str] = None) -> Path:
    if explicit:
        return Path(explicit)
    f = APP_DIR / "home.txt"
    if f.is_file():
        return Path(f.read_text(encoding="utf-8").strip())
    return Path(os.environ.get("ProgramData", str(APP_DIR))) / "BenchCheck"


def python_exe() -> Path:
    p = APP_DIR / "python" / "python.exe"
    return p if p.is_file() else Path(sys.executable)


def read_env(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def run(cmd: List[str], check: bool = False) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} 失败：{(r.stderr or r.stdout).strip()}")
    return r


def port_of(home: Path) -> int:
    return int(read_env(home / ".env").get("GATEWAY_PORT", "8080"))


# --------------------------------------------------------------------------- 配置
ENV_HEADER = """# 标准台校验系统配置（安装程序生成）。修改后运行“重启服务”生效。
# 可配置项说明见安装目录 app\\.env.example。
"""


def configure(args) -> None:
    home = home_dir(args.home)
    for sub in ("data", "logs", "amesim_models"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    (APP_DIR / "home.txt").write_text(str(home), encoding="utf-8")
    env_path = home / ".env"
    env = read_env(env_path)  # 升级时保留原有配置（密钥、密码与手工修改的项）

    password = None
    if args.password_file:
        pf = Path(args.password_file)
        if pf.is_file():
            password = pf.read_text(encoding="utf-8-sig").strip()
            try:
                pf.unlink()  # 密码文件用完即删
            except OSError:
                pass
    if password:
        env["ADMIN_PASSWORD"] = password
    if not env.get("ADMIN_PASSWORD"):
        raise SystemExit("没有设置登录密码")
    env.setdefault("SECRET_KEY", secrets.token_hex(32))
    env.setdefault("ADMIN_USERNAME", "admin")

    app = APP_DIR / "app"
    env.update({
        "BIND_HOST": "127.0.0.1",  # 后端服务只在本机，对外只有统一入口
        "GATEWAY_PORT": str(args.port),
        "GATEWAY_HOST": "0.0.0.0" if args.lan else "127.0.0.1",
        "WEB_ROOT": str(APP_DIR / "web"),
        "DB_PATH": str(home / "data" / "tasks.db"),
        "LOG_DIR": str(home / "logs"),
        "AMESIM_MODEL_DIR": str(home / "amesim_models"),
        "ENABLE_LLM": "1" if args.llm else "0",
        "ENABLE_AMESIM": "1" if args.amesim else "0",
    })
    env.setdefault("DATA_ROOTS", str(app / "pump_test_bench" / "samples"))
    if args.ame:
        env["AME"] = args.ame
    # 内置的 AMESim 示例模型（如有）拷到数据目录，已有的不覆盖
    src = app / "AMESim_server" / "model"
    if src.is_dir():
        for f in src.iterdir():
            dst = home / "amesim_models" / f.name
            if f.is_file() and not dst.exists():
                shutil.copy2(f, dst)

    lines = [ENV_HEADER] + [f"{k}={v}" for k, v in env.items()]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if IS_WINDOWS:  # 只有管理员和系统账户能读（含密码与密钥）
        run(["icacls", str(env_path), "/inheritance:r", "/grant:r", "*S-1-5-32-544:F", "*S-1-5-18:F"])
    firewall(args.lan, args.port)
    print(f"已写入配置：{env_path}")


def firewall(enable: bool, port: int) -> None:
    if not IS_WINDOWS:
        return
    run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={FIREWALL_RULE}"])
    if enable:
        run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={FIREWALL_RULE}", "dir=in", "action=allow",
             "protocol=TCP", f"localport={port}"], check=True)


# --------------------------------------------------------------------------- 计划任务（开机自动运行）
TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>标准台校验系统：开机后在后台运行全部服务（{app}）</Description>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
      <Delay>PT20S</Delay>
    </BootTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>5</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{python}</Command>
      <Arguments>-m pump_test_bench.app.services.supervisor --env "{env}"</Arguments>
      <WorkingDirectory>{workdir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def install_task(args) -> None:
    home = home_dir(args.home)
    xml = TASK_XML.format(app=_xml_escape(str(APP_DIR)), python=_xml_escape(str(python_exe())),
                          env=_xml_escape(str(home / ".env")), workdir=_xml_escape(str(APP_DIR / "app")))
    path = home / "task.xml"
    path.write_text(xml, encoding="utf-16")
    if not IS_WINDOWS:
        print(f"（非 Windows，只生成了 {path}）")
        return
    run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(path), "/F"], check=True)
    path.unlink()
    print("已注册开机自动运行")


def start(args) -> None:
    if IS_WINDOWS:
        run(["schtasks", "/Run", "/TN", TASK_NAME], check=True)
    else:  # 开发环境：前台以外启动
        subprocess.Popen([str(python_exe()), "-m", "pump_test_bench.app.services.supervisor", "--env",
                          str(home_dir(args.home) / ".env")], cwd=str(APP_DIR / "app"))
    print("已启动")


def stop(args) -> None:
    home = home_dir(args.home)
    if IS_WINDOWS:
        run(["schtasks", "/End", "/TN", TASK_NAME])
    pid_file = home / "data" / "supervisor.pid"
    if pid_file.is_file():  # 作业对象会带走子进程；这里再保证一次
        pid = pid_file.read_text(encoding="ascii").strip()
        if IS_WINDOWS:
            run(["taskkill", "/PID", pid, "/T", "/F"])
        else:
            run(["kill", pid])
        try:
            pid_file.unlink()
        except OSError:
            pass
    print("已停止")


def wait_ready(args) -> int:
    url = f"http://127.0.0.1:{port_of(home_dir(args.home))}/api/task/health"
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    print("系统已就绪")
                    return 0
        except Exception:
            pass
        time.sleep(2)
    print(f"等待超时：{url} 未响应，请查看日志目录 {home_dir(args.home) / 'logs'}")
    return 1


def status(args) -> int:
    home = home_dir(args.home)
    info = {"安装目录": str(APP_DIR), "数据目录": str(home), "端口": port_of(home)}
    if IS_WINDOWS:
        r = run(["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"])
        info["计划任务"] = "已注册" if r.returncode == 0 else "未注册"
    url = f"http://127.0.0.1:{info['端口']}/api/task/health"
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            info["服务"] = "运行中" if r.status == 200 else f"异常（{r.status}）"
    except Exception:
        info["服务"] = "未运行"
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0 if info["服务"] == "运行中" else 1


def uninstall(args) -> None:
    home = home_dir(args.home)
    stop(args)
    if IS_WINDOWS:
        run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
        run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={FIREWALL_RULE}"])
    if args.purge and home.is_dir():
        shutil.rmtree(home, ignore_errors=True)
        print(f"已删除数据目录：{home}")
    try:
        (APP_DIR / "home.txt").unlink()
    except OSError:
        pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="标准台校验系统：安装配置与服务管理")
    p.add_argument("--home", help="数据目录（默认读 home.txt，或 C:\\ProgramData\\BenchCheck）")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("configure")
    c.add_argument("--port", type=int, default=8080)
    c.add_argument("--lan", action="store_true", help="允许局域网内其他电脑访问")
    c.add_argument("--llm", action="store_true", help="启用智能助手（需要 Ollama 与模型）")
    c.add_argument("--amesim", action="store_true", help="启用 AMESim 服务（需要本机安装 AMESim）")
    c.add_argument("--ame", help="AMESim 安装目录")
    c.add_argument("--password-file", help="含登录密码的文本文件（读取后删除）")
    sub.add_parser("install-task")
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("restart")
    w = sub.add_parser("wait-ready")
    w.add_argument("--timeout", type=int, default=90)
    sub.add_parser("status")
    u = sub.add_parser("uninstall")
    u.add_argument("--purge", action="store_true")
    args = p.parse_args(argv)
    if args.cmd == "configure":
        configure(args)
    elif args.cmd == "install-task":
        install_task(args)
    elif args.cmd == "start":
        start(args)
    elif args.cmd == "stop":
        stop(args)
    elif args.cmd == "restart":
        stop(args)
        time.sleep(2)
        start(args)
    elif args.cmd == "wait-ready":
        return wait_ready(args)
    elif args.cmd == "status":
        return status(args)
    elif args.cmd == "uninstall":
        uninstall(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
