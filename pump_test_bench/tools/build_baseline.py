"""用健康数据建立诊断基准。

用法（在仓库根目录执行）：
    python -m pump_test_bench.tools.build_baseline 健康数据目录或文件 [--save] [--out 文件]

    不加 --save 只打印统计结果；--save 保存到 <DB_PATH 所在目录>/baseline.json（诊断立即使用）；
    --out 保存到指定文件（如更新随代码提供的 pump_test_bench/config/baseline_default.json）。
数据必须是设备正常状态下采集的，否则会把故障当成“正常偏差”。
"""
import argparse
import sys
from pathlib import Path

from pump_test_bench.app.diagnosis.baseline import build_from_directory, save_baseline


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="用健康数据建立诊断基准")
    parser.add_argument("source", type=Path)
    parser.add_argument("--save", action="store_true", help="保存为当前使用的基准")
    parser.add_argument("--out", type=Path, help="保存到指定文件")
    args = parser.parse_args(argv)

    baseline, skipped = build_from_directory(args.source)
    print(f"使用 {baseline['files']} 个文件，跳过 {len(skipped)} 个")
    for s in skipped:
        print("  跳过", s)
    print("\n流量计固有偏差（相对其余表中位数）：")
    for col, m in baseline["meters"].items():
        cv = f"{m['cv'] * 100:.3f}%" if m.get("cv") is not None else "-"
        print(f"  {col:10s} 偏差 {m['bias'] * 100:+.2f}%  标准差 {m['std'] * 100:.2f}%  短时波动 {cv}")
    for name, b in baseline.get("balance", {}).items():
        print(f"供回油平衡（{name}）：{b['bias'] * 100:+.2f}% ± {b['std'] * 100:.2f}%")
    if "density" in baseline:
        d = baseline["density"]
        print(f"密度模型：ρ = {d['rho15']:.1f} {d['slope']:+.3f}·(T−15) kg/m³，残差 {d['resid_std']:.2f}，"
              f"温度范围 {d['t_min']:.1f}–{d['t_max']:.1f}℃")
    if args.save or args.out:
        path = save_baseline(baseline, args.out)
        print(f"\n已保存：{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
