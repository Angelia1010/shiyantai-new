"""模拟试验台实时产出数据：按时间把数据文件一行一行写入一个目录（边测边写），用来测试系统的实时显示与自动诊断。

本脚本只负责“产出数据”，不登录系统、不检查结果。实时曲线、自动诊断结论在系统页面上查看，
可对照本脚本输出的 数据清单.csv（每个文件注入了什么故障、预期结论是什么）。

数据来源：
- 默认：在正常数据上注入故障（与 generate_fault_data 相同的故障与预期结论），另加 2 个正常文件；
- --source 目录：回放自己准备的数据文件。

用法（在仓库根目录）：
    python -m pump_test_bench.tools.simulate_live_data                      # 正常 2 个 + 典型故障 7 个
    python -m pump_test_bench.tools.simulate_live_data --cases all          # 全部故障用例（约 50 个）
    python -m pump_test_bench.tools.simulate_live_data --cases F01,F11      # 指定故障编号
    python -m pump_test_bench.tools.simulate_live_data --source D:\\我的数据  # 回放自己的数据
常用参数：--to 写入的目录（默认 当前目录下 live_test_data\\<时间>\\data）、--speed 倍速（默认 1 = 真实速度）、
--gap 文件之间停顿秒数（默认 15，留时间给系统诊断）、--loop 循环、--no-wait 不等回车直接开始。
"""
import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from pump_test_bench.tools.replay_data import _source_files, replay_file

REPO_ROOT = Path(__file__).resolve().parents[2]
QUICK_CODES = ("F01", "F05", "F06", "F11", "F14", "F16", "F17")
RESULT_TEXT = {"normal": "正常", "warning": "预警", "abnormal": "异常", "inconclusive": "无法判定"}


def build_cases(args, work: Path) -> List[Dict]:
    """[{src, name, fault, expect, expect_text}]"""
    if args.source:
        files = _source_files(args.source)
        if not files:
            raise SystemExit(f"没有找到数据文件：{args.source}")
        return [{"src": f, "name": f.name, "fault": "（自备数据）", "expect": "", "expect_text": ""} for f in files]
    healthy = args.healthy
    if not healthy.is_dir():
        raise SystemExit(f"没有找到正常数据目录：{healthy}（用 --healthy 指定，或用 --source 回放自己的数据）")
    from pump_test_bench.tools.generate_fault_data import CONDITIONS, generate
    print("在正常数据上注入故障，生成数据文件…")
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
            raise SystemExit(f"没有这些故障编号：{args.cases}（可用 F01–F23，见 generate_fault_data.py）")
    cases = []
    for key in ("B", "C"):  # 正常数据：不应报警
        folder, name, label = CONDITIONS[key]
        cases.append({"src": healthy / folder / name, "name": f"N_正常_{label}.txt", "fault": "正常数据",
                      "expect": "normal", "expect_text": "正常"})
    for r in rows:
        cases.append({"src": work / "cases" / r["文件"], "name": f"{r['故障编号']}_{Path(r['文件']).name}".replace(" ", ""),
                      "fault": f"{r['故障']}（{r['程度']}）", "expect": r["预期结论"], "expect_text": r["预期诊断"]})
    return cases


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="模拟试验台实时产出数据（边测边写）")
    p.add_argument("--to", type=Path, help="写入的目录（系统监控的目录），默认 当前目录下 live_test_data\\<时间>\\data")
    p.add_argument("--cases", default="quick", help="quick（默认）/ all / 故障编号列表如 F01,F11")
    p.add_argument("--source", type=Path, help="回放自己的数据文件或目录（不注入故障）")
    p.add_argument("--healthy", type=Path, default=REPO_ROOT / "标准台性能录取数据" / "标准台性能录取数据",
                   help="正常数据目录（注入故障用）")
    p.add_argument("--speed", type=float, default=1.0, help="写入倍速，默认 1（真实速度，每个文件 30–40 秒）")
    p.add_argument("--gap", type=float, default=15.0, help="两个文件之间停顿的秒数，默认 15")
    p.add_argument("--loop", action="store_true", help="写完一轮后从头再来")
    p.add_argument("--no-wait", action="store_true", help="不等回车，直接开始写入")
    args = p.parse_args(argv)
    if args.speed <= 0:
        raise SystemExit("--speed 必须大于 0")

    run = Path.cwd() / "live_test_data" / datetime.now().strftime("%Y%m%d-%H%M%S")
    target = (args.to or run / "data").resolve()
    work = target.parent if not args.to else run
    target.mkdir(parents=True, exist_ok=True)
    cases = build_cases(args, work)

    # 数据清单放在写入目录之外（避免被当作数据文件）
    manifest = target.parent / f"{target.name}_数据清单.csv"
    with open(manifest, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["序号", "文件", "数据", "预期结论", "预期诊断"])
        for i, c in enumerate(cases, 1):
            w.writerow([i, f"{i:02d}_{c['name']}", c["fault"], RESULT_TEXT.get(c["expect"], "—"), c["expect_text"]])

    print(f"\n共 {len(cases)} 个数据文件，{args.speed:g} 倍速，文件间隔 {args.gap:g} 秒{'，循环' if args.loop else ''}")
    print(f"写入目录：{target}")
    print(f"数据清单：{manifest}（每个文件的故障与预期结论）")
    print("\n请在系统“工作台 → 数据目录”中填写上面的写入目录，并打开“自动诊断”，")
    print("然后在工作台看实时曲线、在“诊断记录”看每个文件写完后的诊断结论。")
    if not args.no_wait:
        input("\n设置好后按回车开始写入（Ctrl+C 停止）…")

    try:
        rnd = 0
        while True:
            rnd += 1
            for i, c in enumerate(cases, 1):
                name = f"{i:02d}_{c['name']}" if rnd == 1 else f"{i:02d}_第{rnd}轮_{c['name']}"
                print(f"\n[{i}/{len(cases)}] {c['fault']}　预期：{RESULT_TEXT.get(c['expect'], '—')}"
                      + (f"（{c['expect_text']}）" if c["expect_text"] and c["expect"] != "normal" else ""))
                replay_file(c["src"], target / name, args.speed)
                if i < len(cases) or args.loop:
                    print(f"  等待 {args.gap:g} 秒（系统判定文件写完并诊断）…")
                    time.sleep(args.gap)
            if not args.loop:
                break
    except KeyboardInterrupt:
        print("\n已停止")
    print(f"\n写入结束。写入目录：{target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
