# -*- coding: utf-8 -*-
"""
诊断函数测试脚本
公式：Y = 2696.17 + 15468.63 * X1 - 3.42 * X2
X1: 质量流量 (kg/s)
X2: 介质密度 (kg/m³)
"""

import os
import sys
import pandas as pd
import numpy as np

# 路径设置
parent_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.append(parent_dir)
from app.core.diagnosis import Diagnosis

# ============================================================
# 打印工具
# ============================================================
SEP = "=" * 60

def print_section(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

def print_result(result):
    print("\n【异常指标】")
    for ind in result["indicators"]:
        print(f"  {ind['name']:<20} | 参考: {ind['reference']:<12} | 实测: {ind['value']}")
    d = result["diagnosis"]
    print(f"\n【诊断结论】")
    print(f"  类型    : {d['fault_name']}")
    print(f"  定位    : {d['location']}")
    print(f"  分析    : {d['analysis']}")
    print(f"\n【维修建议】")
    for line in result["repair_advice"].splitlines():
        print(f"  {line}")

# ============================================================
# 构造测试 Excel 文件
# ============================================================
def build_test_excel(path):
    """
    构造包含 '质量流量' 和 '介质密度' 列的测试 Excel。
    数据分三个 sheet：正常工况 / 高流量工况 / 低密度工况。
    质量流量参考实测数据约 0.12~0.13 kg/s（由真实文件回油质量流量折算）。
    介质密度取航空燃油典型范围 775~840 kg/m³。
    """
    np.random.seed(42)
    n = 50  # 每个 sheet 50 条数据

    def make_df(x1_mean, x1_std, x2_mean, x2_std):
        x1 = np.random.normal(x1_mean, x1_std, n).clip(min=0.01)
        x2 = np.random.normal(x2_mean, x2_std, n).clip(min=700)
        return pd.DataFrame({"质量流量(kg/s)": x1, "介质密度(kg/m³)": x2})

    sheets = {
        "正常工况":   make_df(x1_mean=0.126, x1_std=0.003, x2_mean=810, x2_std=5),
        "高流量工况": make_df(x1_mean=0.155, x1_std=0.004, x2_mean=810, x2_std=5),
        "低密度工况": make_df(x1_mean=0.126, x1_std=0.003, x2_mean=775, x2_std=5),
    }

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"  测试文件已生成：{path}")
    for sheet_name, df in sheets.items():
        x1 = df["质量流量(kg/s)"]
        x2 = df["介质密度(kg/m³)"]
        print(f"  [{sheet_name}] X1: {x1.mean():.4f}±{x1.std():.4f}  "
              f"X2: {x2.mean():.2f}±{x2.std():.2f}  n={len(df)}")

# ============================================================
# 测试 1：公式验证（手算对照）
# ============================================================
def test_formula():
    print_section("测试 1：公式手算验证")
    cases = [
        (0.126, 810,  "正常工况参考点"),
        (0.155, 810,  "高流量"),
        (0.126, 775,  "低密度"),
        (0.0,   810,  "零流量（边界）"),
    ]
    print(f"  {'说明':<16} {'X1':>8} {'X2':>8} {'Y（手算）':>14} {'Y（函数）':>14} {'误差':>8}")
    print("  " + "-" * 72)
    for x1, x2, label in cases:
        y_manual = 2696.17 + 15468.63 * x1 - 3.42 * x2
        y_func   = Diagnosis.calc_y(x1, x2)
        err = abs(y_manual - y_func)
        status = "✓" if err < 1e-6 else "✗"
        print(f"  {label:<16} {x1:>8.4f} {x2:>8.2f} {y_manual:>14.4f} {y_func:>14.4f} {status}")

# ============================================================
# 测试 2：直接传参模式
# ============================================================
def test_direct_params():
    print_section("测试 2：直接传参模式（单点诊断）")

    scenarios = [
        (0.126, 810,  "正常工况"),
        (0.155, 810,  "高流量工况"),
        (0.095, 810,  "低流量工况"),
        (0.126, 775,  "低密度工况"),
        (0.126, 840,  "高密度工况"),
    ]

    diag = Diagnosis(file_name=None, conf_file=None)
    for x1, x2, label in scenarios:
        print(f"\n  ▶ {label}  X1={x1}  X2={x2}")
        result = diag.diagnosis_process(x1=x1, x2=x2)
        y_val = next(i["value"] for i in result["indicators"] if "均值" in i["name"] and "Y" in i["name"])
        print(f"    诊断输出 Y = {y_val}")
        print(f"    维修建议首行: {result['repair_advice'].splitlines()[0]}")

# ============================================================
# 测试 3：文件读取模式（完整输出）
# ============================================================
def test_file_mode(excel_path):
    """
    Diagnosis 会自动遍历 sheet 找第一个同时含 X1/X2 列的 sheet 进行诊断。
    本测试验证文件读取完整流程，并展示完整的诊断报告输出。
    若需对每个 sheet 分别诊断，见测试 4。
    """
    print_section("测试 3：文件读取模式（完整诊断报告）")

    diag = Diagnosis(file_name=excel_path, conf_file=None)
    result = diag.diagnosis_process()
    print_result(result)

# ============================================================
# 测试 4：Y 值对比（三种工况横向对比）
# ============================================================
def test_comparison(excel_path):
    print_section("测试 4：三种工况 Y 值横向对比")

    xl = pd.ExcelFile(excel_path, engine="openpyxl")
    print(f"\n  {'工况':<12} {'X1均值':>10} {'X2均值':>10} {'Y均值':>12} {'Y标准差':>10} {'Y范围'}")
    print("  " + "-" * 72)

    for sheet in xl.sheet_names:
        df = xl.parse(sheet)
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        x1_col = next((c for c in df.columns if "质量流量" in c), None)
        x2_col = next((c for c in df.columns if "介质密度" in c), None)
        valid = df[[x1_col, x2_col]].dropna()
        x1 = valid[x1_col]
        x2 = valid[x2_col]
        y  = Diagnosis.calc_y(x1, x2)
        print(f"  {sheet:<12} {x1.mean():>10.4f} {x2.mean():>10.2f} "
              f"{y.mean():>12.2f} {y.std():>10.2f} "
              f"[{y.min():.2f}, {y.max():.2f}]")

# ============================================================
# 测试 5：异常输入处理
# ============================================================
def test_edge_cases():
    print_section("测试 5：异常输入处理")
    diag = Diagnosis(file_name="不存在的文件.xlsx", conf_file=None)

    # 5-1 文件不存在但有直传参数 → 应正常运行
    print("\n  ▶ 5-1 文件不存在但直接传入 x1/x2")
    try:
        result = diag.diagnosis_process(x1=0.126, x2=810)
        y_val = next(i["value"] for i in result["indicators"] if "Y" in i["name"] and "均值" in i["name"])
        print(f"    ✓ 正常计算，Y = {y_val}")
    except Exception as e:
        print(f"    ✗ 意外异常: {e}")

    # 5-2 文件不存在且无传参 → 应抛出异常
    print("\n  ▶ 5-2 文件不存在且不传 x1/x2")
    try:
        diag.diagnosis_process()
        print("    ✗ 未抛出异常（预期应报错）")
    except Exception as e:
        print(f"    ✓ 正确抛出异常: {e}")

    # 5-3 仅传 x1 不传 x2 → 应走文件模式（报文件不存在）
    print("\n  ▶ 5-3 仅传 x1 不传 x2")
    try:
        diag.diagnosis_process(x1=0.126)
        print("    ✗ 未抛出异常（预期应报错）")
    except Exception as e:
        print(f"    ✓ 正确抛出异常: {e}")

# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    EXCEL_PATH = os.path.join(parent_dir, "app", "test_data", "test_diagnosis_data.xlsx")

    print(f"\n{'#' * 60}")
    print(f"  故障诊断测试  |  Y = 2696.17 + 15468.63·X1 - 3.42·X2")
    print(f"{'#' * 60}")

    # 生成测试数据文件
    print_section("准备测试数据")
    build_test_excel(EXCEL_PATH)

    # 逐项测试
    test_formula()
    test_direct_params()
    test_file_mode(EXCEL_PATH)
    test_comparison(EXCEL_PATH)
    test_edge_cases()

    print(f"\n{'#' * 60}")
    print(f"  全部测试完成")
    print(f"{'#' * 60}\n")
