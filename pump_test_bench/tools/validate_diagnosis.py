"""诊断效果验证：在健康数据上注入典型故障，统计检出率与误报率。

用法（在仓库根目录执行）：
    python -m pump_test_bench.tools.validate_diagnosis 健康数据目录 [--no-baseline] [--limit 20]

输出每个场景：判为“异常”的比例、判为“预警或异常”的比例、定位到正确对象的比例。
“无故障”一行就是误报率。
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

from pump_test_bench.app.core.data_reader import read_table
from pump_test_bench.app.diagnosis import faults
from pump_test_bench.app.diagnosis.baseline import _files, load_baseline
from pump_test_bench.app.diagnosis.config import load_config
from pump_test_bench.app.diagnosis.engine import diagnose_frame


def _expected_target(name: str) -> str:
    return name.split(" ")[0]


def run(files, baseline, cfg):
    stats = defaultdict(lambda: {"n": 0, "abnormal": 0, "flagged": 0, "located": 0})
    scenarios = {"无故障": lambda d: d, **faults.scenarios(cfg)}
    for path in files:
        try:
            _, df = read_table(path)
        except ValueError:  # 空文件、说明文件等
            continue
        for name, inject in scenarios.items():
            body = diagnose_frame(inject(df), baseline=baseline, cfg=cfg)
            s = stats[name]
            s["n"] += 1
            s["abnormal"] += body["result"] == "abnormal"
            s["flagged"] += body["result"] in ("warning", "abnormal")
            decisive = [f for f in body["findings"] if f["severity"] in ("warning", "abnormal")]
            target = _expected_target(name)
            if name == "无故障":
                s["located"] += not decisive
            elif "泄漏" in name:
                s["located"] += any(f["category"] == "balance" for f in decisive) and \
                    not any(f["category"] == "redundancy" for f in decisive)
            else:
                s["located"] += bool(decisive) and all(f["target"] == target for f in decisive
                                                       if f["category"] != "simulation")
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="诊断效果验证（故障注入）")
    parser.add_argument("source", type=Path)
    parser.add_argument("--no-baseline", action="store_true", help="不使用健康基准")
    parser.add_argument("--limit", type=int, default=0, help="最多使用的文件数")
    args = parser.parse_args(argv)

    files = _files(args.source)[: args.limit or None]
    baseline = None if args.no_baseline else load_baseline()
    stats = run(files, baseline, load_config())
    print(f"文件 {len(files)} 个，{'不使用' if baseline is None else '使用'}健康基准\n")
    print(f"{'场景':22s}{'判异常':>8s}{'预警或异常':>10s}{'定位正确':>10s}")
    for name, s in stats.items():
        n = s["n"]
        print(f"{name:22s}{s['abnormal'] / n:>8.0%}{s['flagged'] / n:>10.0%}{s['located'] / n:>10.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
