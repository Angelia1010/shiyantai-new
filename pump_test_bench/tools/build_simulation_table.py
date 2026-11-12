"""建立仿真基准表并用正常数据标定（每个模型一张表）。

用法（仓库根目录）：
    python -m pump_test_bench.tools.build_simulation_table 健康数据目录                    # 所有模型，保存到数据目录
    python -m pump_test_bench.tools.build_simulation_table 健康数据目录 --model bench      # 只建一个模型
    python -m pump_test_bench.tools.build_simulation_table 健康数据目录 --engine amesim    # 用 AMESim
    python -m pump_test_bench.tools.build_simulation_table 健康数据目录 --default          # 写入随代码提供的默认表

也可以在前端“仿真模型”页面操作。
"""
import argparse
import sys
from pathlib import Path

from pump_test_bench.app.diagnosis.baseline import _files
from pump_test_bench.app.simulation.calibration import build_reference
from pump_test_bench.app.simulation.config import list_models, load_model_cfg
from pump_test_bench.app.simulation.table import default_table_path, save_table


def print_summary(table) -> None:
    calib = table.get("calibration", {})
    print(f"\n{table['model_name']}：{table['model']['label']}；网格 "
          + " × ".join(f"{i['name']}{len(i['grid'])}" for i in table["inputs"])
          + f"；标定文件 {calib.get('files')} 个（{calib.get('method', '')}）")
    print(f"{'测点':<14}{'所属输出':<10}{'固有偏差':>10}{'离散σ':>10}")
    units = {o["name"]: o.get("unit", "") for o in table["outputs"]}
    for col, c in calib.get("columns", {}).items():
        unit = units.get(c["output"], "") if c.get("mode") == "absolute" else "%"
        k = 100 if unit == "%" else 1
        print(f"{col:<14}{c['output']:<14}{c['bias'] * k:>10.3f} {unit:<5}{c['std'] * k:>9.3f} {unit}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="建立仿真基准表")
    parser.add_argument("source", type=Path, help="正常（健康）数据文件或目录")
    parser.add_argument("--model", help="模型 id（默认全部）：" + "、".join(m["id"] for m in list_models()))
    parser.add_argument("--engine", choices=("surrogate", "amesim"), help="引擎，默认按模型配置")
    parser.add_argument("--default", action="store_true", help="写入 config/simulation_tables/（随代码提供的默认表）")
    args = parser.parse_args(argv)

    models = [load_model_cfg(args.model)] if args.model else list_models()
    files = _files(args.source)
    for mcfg in models:
        def progress(stage, done, total, name=mcfg["name"]):
            print(f"\r{name} {stage} {done}/{total}      ", end="", flush=True)

        try:
            table = build_reference(files, mcfg, args.engine, progress, source=str(args.source))
        except ValueError as exc:
            print(f"\n{mcfg['name']}：未建立 —— {exc}")
            continue
        print_summary(table)
        path = save_table(table, default_table_path(mcfg["id"]) if args.default else None)
        print(f"已保存：{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
