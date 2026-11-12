"""实时故障诊断端到端测试：模拟试验台边测边写数据文件，检查系统能否实时显示、自动诊断并给出正确结论。

测试的是“真实链路”：数据文件按时间一行一行写入被监控的目录 → 文件服务实时读取（工作台显示）→
文件写完后自动诊断 → 保存报告。脚本通过网页同样的接口检查每一步，不直接调用诊断代码。

用例来源：
- 默认：用正常数据现场注入故障（同 generate_fault_data），每个用例都有预期结论，另加 2 个正常文件；
- --source 目录：回放自己准备的数据文件（没有预期结论，只记录诊断结果）。

用法（在仓库根目录；系统需已启动）：
    python -m pump_test_bench.tools.live_diagnosis_test                         # 快速：正常 2 个 + 典型故障 7 个
    python -m pump_test_bench.tools.live_diagnosis_test --cases all             # 全部故障用例（约 50 个）
    python -m pump_test_bench.tools.live_diagnosis_test --cases F01,F11,F16     # 指定故障编号
    python -m pump_test_bench.tools.live_diagnosis_test --source D:\\我的数据    # 回放自己的数据
常用参数：--url 系统地址（默认 http://localhost:8080，开发时可用 http://localhost:9528）、
--password 登录密码（不填会提示输入）、--speed 回放倍速（默认 4；1 为真实速度）、
--healthy 正常数据目录（默认 标准台性能录取数据/标准台性能录取数据）。

结果：控制台逐个显示，并在测试目录下保存 实时诊断测试报告.csv / .md。全部符合预期时退出码为 0。
测试结束后恢复原来的监控目录与自动诊断设置。被测系统需在本机（测试目录要能被系统读到）。
"""
import argparse
import csv
import getpass
import json
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from pump_test_bench.tools.replay_data import _source_files, replay_file

REPO_ROOT = Path(__file__).resolve().parents[2]
QUICK_CODES = ("F01", "F05", "F06", "F11", "F14", "F16", "F17")
RESULT_TEXT = {"normal": "正常", "warning": "预警", "abnormal": "异常", "inconclusive": "无法判定"}


# --------------------------------------------------------------------------- 接口
class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.token = ""

    def call(self, method: str, path: str, body: Optional[Dict] = None, timeout: float = 30):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("X-Token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8") or "null")
        except urllib.error.HTTPError as exc:
            try:
                msg = json.loads(exc.read().decode("utf-8")).get("error")
            except Exception:
                msg = exc.reason
            raise RuntimeError(f"{method} {path} 失败（{exc.code}）：{msg}") from None

    def login(self, user: str, password: str) -> None:
        self.token = self.call("POST", "/api/task/auth/login", {"username": user, "password": password})["token"]


# --------------------------------------------------------------------------- 用例
def build_cases(args, work: Path) -> List[Dict]:
    """[{src, name, code, fault, expect, expect_text}]"""
    if args.source:
        files = _source_files(args.source)
        if not files:
            raise SystemExit(f"没有找到数据文件：{args.source}")
        return [{"src": f, "name": f.name, "code": "", "fault": "（自备数据）", "expect": "", "expect_text": ""}
                for f in files]
    healthy = args.healthy
    if not healthy.is_dir():
        raise SystemExit(f"没有找到正常数据目录：{healthy}（用 --healthy 指定，或用 --source 回放自己的数据）")
    from pump_test_bench.tools.generate_fault_data import CONDITIONS, generate
    print("生成故障用例（在正常数据上注入故障）…")
    rows = generate(healthy, work / "cases")
    if args.cases == "quick":
        seen, picked = set(), []
        for r in rows:  # 每个典型故障取第一个工况
            if r["故障编号"] in QUICK_CODES and r["故障编号"] not in seen:
                seen.add(r["故障编号"])
                picked.append(r)
        rows = picked
    elif args.cases != "all":
        codes = {c.strip().upper() for c in args.cases.split(",") if c.strip()}
        rows = [r for r in rows if r["故障编号"] in codes]
        if not rows:
            raise SystemExit(f"没有这些故障编号：{args.cases}（可用 F01–F19，见 generate_fault_data.py）")
    cases = []
    for key in ("B", "C"):  # 正常数据：不应报警
        folder, name, label = CONDITIONS[key]
        cases.append({"src": healthy / folder / name, "name": f"正常_{label}.txt", "code": "N", "fault": "正常数据",
                      "expect": "normal", "expect_text": "正常"})
    for r in rows:
        cases.append({"src": work / "cases" / r["文件"], "name": Path(r["文件"]).name.replace(" ", ""),
                      "code": r["故障编号"], "fault": f"{r['故障']}（{r['程度']}）", "expect": r["预期结论"],
                      "expect_text": r["预期诊断"]})
    return cases


# --------------------------------------------------------------------------- 单个用例
def run_case(api: Api, case: Dict, index: int, watch_dir: Path, speed: float, timeout: float) -> Dict:
    dest_name = f"{index:02d}_{case['code'] or 'X'}_{case['name']}"
    dest = watch_dir / dest_name
    live = {"seen": False, "frames": 0}
    start_seq = api.call("GET", "/api/file/live/status").get("latest_seq") or 0

    done = threading.Event()
    error: List[str] = []

    def writer():
        try:
            replay_file(case["src"], dest, speed, quiet=True)
        except Exception as exc:  # 记录到结果
            error.append(str(exc))
        finally:
            done.set()

    t0 = time.time()
    threading.Thread(target=writer, daemon=True).start()
    while not done.is_set():  # 写入过程中检查“实时数据”
        try:
            st = api.call("GET", "/api/file/live/status", timeout=5)
            if st.get("file") and st["file"].endswith(dest_name) and st.get("state") == "live":
                live["seen"] = True
                live["frames"] = max(live["frames"], (st.get("latest_seq") or 0) - start_seq)
        except Exception:
            pass
        done.wait(1.0)
    t_written = time.time()
    row = {"序号": index, "文件": dest_name, "故障": case["fault"], "预期结论": RESULT_TEXT.get(case["expect"], "—"),
           "预期诊断": case["expect_text"], "写入耗时(s)": f"{t_written - t0:.1f}",
           "实时显示": "是" if live["seen"] else "否", "实时帧数": live["frames"]}
    if error:
        row.update({"判定": "失败", "说明": f"写入文件出错：{error[0]}"})
        return row

    # 等待自动诊断完成
    deadline = t_written + timeout
    task = None
    while time.time() < deadline:
        q = urllib.parse.urlencode({"mode": "auto", "keyword": dest_name, "page_size": 5})
        items = (api.call("GET", f"/api/task/tasks?{q}").get("items") or [])
        task = next((t for t in items if t["file_name"].endswith(dest_name)), None)
        if task and task["status"] in ("Completed", "Failed"):
            break
        time.sleep(1.0)
    row["诊断耗时(s)"] = f"{time.time() - t_written:.1f}"
    if not task or task["status"] not in ("Completed", "Failed"):
        row.update({"判定": "超时", "说明": "文件写完后 %d 秒内没有自动诊断结果（%s）" % (
            timeout, "已创建任务，未完成" if task else "没有创建诊断任务：请确认已开启自动诊断")})
        return row
    if task["status"] == "Failed":
        row.update({"判定": "失败", "说明": task.get("error") or "诊断失败"})
        return row
    report = api.call("GET", f"/api/task/tasks/{task['task_id']}/report")
    result = report.get("result", "")
    causes = "；".join(c.get("name", "") for c in report.get("causes") or []) or report.get("summary", "")
    row.update({"实际结论": RESULT_TEXT.get(result, result), "实际诊断": causes, "任务": task["task_id"]})
    if not case["expect"]:
        row["判定"] = "已诊断"
    elif result == case["expect"]:
        row["判定"] = "通过"
    elif result == "abnormal" and case["expect"] == "warning":
        row["判定"] = "偏严"
    else:
        row["判定"] = "不符"
    return row


def default_work_root() -> Path:
    """仓库目录下的 live_test_runs；不可写时（如安装在 Program Files 下）用 用户目录\\BenchCheck实时诊断测试。"""
    root = REPO_ROOT / "live_test_runs"
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write_test"
        probe.write_text("x", encoding="ascii")
        probe.unlink()
        return root
    except OSError:
        return Path.home() / "BenchCheck实时诊断测试"


# --------------------------------------------------------------------------- 主流程
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="实时故障诊断端到端测试")
    p.add_argument("--url", default="http://localhost:8080", help="系统地址，默认 http://localhost:8080")
    p.add_argument("--user", default="admin")
    p.add_argument("--password", help="登录密码（不填时提示输入）")
    p.add_argument("--cases", default="quick", help="quick（默认）/ all / 故障编号列表如 F01,F11")
    p.add_argument("--source", type=Path, help="回放自己的数据文件或目录（不用注入故障）")
    p.add_argument("--healthy", type=Path, default=REPO_ROOT / "标准台性能录取数据" / "标准台性能录取数据",
                   help="正常数据目录（生成故障用例用）")
    p.add_argument("--speed", type=float, default=4.0, help="回放倍速，默认 4（1 为真实速度）")
    p.add_argument("--timeout", type=float, default=120, help="每个文件写完后等待诊断结果的秒数")
    p.add_argument("--work", type=Path, help="测试目录（默认 仓库下 live_test_runs\\<时间>）")
    p.add_argument("--keep-watch", action="store_true", help="测试后不恢复原来的监控目录")
    args = p.parse_args(argv)

    api = Api(args.url)
    try:
        api.call("GET", "/api/task/health", timeout=5)
    except Exception as exc:
        print(f"[失败] 连不上系统 {args.url}：{exc}\n请先启动系统（安装版：开始菜单“启动服务”；开发：supervisor 或各服务）。")
        return 2
    password = args.password or getpass.getpass(f"登录密码（{args.user}）：")
    try:
        api.login(args.user, password)
    except RuntimeError as exc:
        print(f"[失败] 登录失败：{exc}")
        return 2

    work = (args.work or default_work_root() / datetime.now().strftime("%Y%m%d-%H%M%S")).resolve()
    watch_dir = work / "watch"
    watch_dir.mkdir(parents=True, exist_ok=True)
    cases = build_cases(args, work)
    print(f"共 {len(cases)} 个用例，回放倍速 {args.speed}，测试目录：{work}")

    previous = api.call("GET", "/api/file/watch")
    api.call("POST", "/api/file/watch", {"path": str(watch_dir), "auto_diagnose": True})
    print(f"已把监控目录切换到测试目录并开启自动诊断（原来：{previous.get('path') or '未设置'}）\n")
    time.sleep(2)

    rows: List[Dict] = []
    try:
        for i, case in enumerate(cases, 1):
            print(f"[{i}/{len(cases)}] {case['fault']}  {case['name']}", flush=True)
            row = run_case(api, case, i, watch_dir, args.speed, args.timeout)
            rows.append(row)
            mark = {"通过": "✔", "偏严": "△", "已诊断": "·"}.get(row["判定"], "✘")
            print(f"    {mark} {row['判定']}：实际 {row.get('实际结论', '—')}（预期 {row['预期结论']}）"
                  f"  实时显示 {row['实时显示']}  诊断耗时 {row.get('诊断耗时(s)', '—')}s"
                  + (f"\n      {row.get('实际诊断') or row.get('说明', '')}" if row.get("实际诊断") or row.get("说明") else ""),
                  flush=True)
    except KeyboardInterrupt:
        print("\n已中止")
    finally:
        if not args.keep_watch and previous.get("path"):
            try:
                api.call("POST", "/api/file/watch", {"path": previous["path"],
                                                     "auto_diagnose": bool(previous.get("auto_diagnose"))})
                print(f"\n已恢复原来的监控目录：{previous['path']}")
            except Exception as exc:
                print(f"\n恢复原来的监控目录失败（请在工作台中重新设置）：{exc}")
        elif not args.keep_watch:
            api.call("POST", "/api/file/watch/auto-diagnose", {"enabled": bool(previous.get("auto_diagnose"))})

    if not rows:
        return 1
    fields = ["序号", "文件", "故障", "预期结论", "实际结论", "判定", "预期诊断", "实际诊断", "实时显示", "实时帧数",
              "写入耗时(s)", "诊断耗时(s)", "任务", "说明"]
    with open(work / "实时诊断测试报告.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    count = {k: sum(r["判定"] == k for r in rows) for k in ("通过", "偏严", "不符", "超时", "失败", "已诊断")}
    live_ok = sum(r["实时显示"] == "是" for r in rows)
    lat = [float(r["诊断耗时(s)"]) for r in rows if r.get("诊断耗时(s)") and r["判定"] not in ("超时", "失败")]
    summary = (f"通过 {count['通过']}，偏严 {count['偏严']}，不符 {count['不符']}，超时 {count['超时']}，失败 {count['失败']}"
               + (f"，自备数据已诊断 {count['已诊断']}" if count["已诊断"] else "")
               + f"；实时显示正常 {live_ok}/{len(rows)}"
               + (f"；文件写完到出结果平均 {sum(lat) / len(lat):.1f} 秒" if lat else ""))
    md = [f"# 实时诊断测试报告（{datetime.now():%Y-%m-%d %H:%M}）", "", f"系统：{args.url}，回放倍速 {args.speed}，用例 {len(rows)} 个", "",
          f"**{summary}**", "", "| " + " | ".join(fields[:10]) + " |", "|" + "---|" * 10]
    md += ["| " + " | ".join(str(r.get(f, "")).replace("|", "/") for f in fields[:10]) + " |" for r in rows]
    (work / "实时诊断测试报告.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\n==== {summary} ====")
    print(f"报告：{work / '实时诊断测试报告.csv'}")
    shutil.rmtree(work / "cases", ignore_errors=True)
    bad = count["不符"] + count["超时"] + count["失败"] + (len(rows) - live_ok)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
