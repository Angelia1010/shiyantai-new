"""建立仿真基准表并用正常数据标定。

用法（仓库根目录）：
    python -m pump_test_bench.tools.build_simulation_table 健康数据目录                 # 按 simulation.json 的模型类型，保存到数据目录
    python -m pump_test_bench.tools.build_simulation_table 健康数据目录 --model amesim  # 用 AMESim（需先启动 AMESim 服务）
    python -m pump_test_bench.tools.build_simulation_table 健康数据目录 --out 文件.json

也可以在前端“仿真模型”页面操作。
"""
import argparse
import sys
from pathlib import Path

from pump_test_bench.app.diagnosis.baseline import _files
from pump_test_bench.app.simulation.calibration import build_reference
from pump_test_bench.app.simulation.config import load_sim_config
from pump_test_bench.app.simulation.table import save_table


def print_summary(table) -> None:
    calib = table.get("calibration", {})
    print(f"\n模型：{table['model']['label']}；网格 "
          + " × ".join(f"{i['name']}{len(i['grid'])}" for i in table["inputs"])
          + f"；标定文件 {calib.get('files')} 个（{calib.get('method', '')}）")
    print(f"{'测点':<14}{'所属输出':<10}{'固有偏差':>10}{'离散σ':>10}")
    for col, c in calib.get("columns", {}).items():
        print(f"{col:<14}{c['output']:<10}{c['bias'] * 100:>9.2f}%{c['std'] * 100:>9.2f}%")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="建立仿真基准表")
    parser.add_argument("source", type=Path, help="正常（健康）数据文件或目录")
    parser.add_argument("--model", choices=("surrogate", "amesim"), help="模型类型，默认按 simulation.json")
    parser.add_argument("--out", type=Path, help="保存位置，默认数据目录下的 simulation_table.json")
    args = parser.parse_args(argv)

    def progress(stage, done, total):
        print(f"\r{stage} {done}/{total}", end="", flush=True)

    table = build_reference(_files(args.source), load_sim_config(), args.model, progress, source=str(args.source))
    print_summary(table)
    path = save_table(table, args.out)
    print(f"\n已保存：{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
