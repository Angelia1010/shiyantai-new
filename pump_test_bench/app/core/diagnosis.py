# -*- coding: utf-8 -*-
import os
import sys
import pandas as pd

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(parent_dir)


class Diagnosis:
    # 列名关键字（Excel 列名包含此关键字即匹配）
    COL_MASS_FLOW = '质量流量'   # X1
    COL_DENSITY = '介质密度'     # X2

    def __init__(self, file_name, conf_file):
        self.file_name = file_name

    # ------------------------------------------------------------------ #
    #  诊断模型公式                                                         #
    # ------------------------------------------------------------------ #
    @staticmethod
    def calc_y(x1, x2):
        """
        诊断模型: Y = 2696.17 + 15468.63 * X1 - 3.42 * X2
        X1: 质量流量
        X2: 介质密度
        Y:  诊断输出
        """
        return 2696.17 + 15468.63 * x1 - 3.42 * x2

    # ------------------------------------------------------------------ #
    #  数据读取                                                             #
    # ------------------------------------------------------------------ #
    def _find_col(self, df, keyword):
        """在 DataFrame 列名中模糊匹配关键字，返回第一个匹配的列名"""
        for col in df.columns:
            if keyword in str(col):
                return col
        return None

    # 找不到介质密度列时使用的默认值（航空燃油典型密度 kg/m³）
    DEFAULT_DENSITY = 820.0

    def _read_data_from_excel(self):
        """
        读取 Excel 文件，遍历所有 sheet，找到含 X1 列的第一个 sheet。
        X2（介质密度）列不存在时使用默认值 DEFAULT_DENSITY。
        返回 (x1_series, x2_series, sheet_name, x1_col, x2_col)
        """
        xl = pd.ExcelFile(self.file_name, engine='openpyxl')
        for sheet in xl.sheet_names:
            df = xl.parse(sheet, dtype=object)
            for col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            x1_col = self._find_col(df, self.COL_MASS_FLOW)
            if not x1_col:
                continue

            x2_col = self._find_col(df, self.COL_DENSITY)
            if x2_col:
                valid = df[[x1_col, x2_col]].dropna()
                return (
                    valid[x1_col].reset_index(drop=True),
                    valid[x2_col].reset_index(drop=True),
                    sheet, x1_col, x2_col,
                )
            else:
                # 无介质密度列，用默认值填充
                x1 = df[x1_col].dropna().reset_index(drop=True)
                x2 = pd.Series([self.DEFAULT_DENSITY] * len(x1))
                x2_col = f'{self.COL_DENSITY}（默认{self.DEFAULT_DENSITY}）'
                return x1, x2, sheet, x1_col, x2_col

        raise ValueError(
            f"文件 '{os.path.basename(self.file_name)}' 中未找到含 '{self.COL_MASS_FLOW}' 的 sheet"
        )

    # ------------------------------------------------------------------ #
    #  诊断主流程                                                           #
    # ------------------------------------------------------------------ #
    def diagnosis_process(self, x1=None, x2=None):
        """
        执行故障诊断，返回 indicators / diagnosis / repair_advice。

        :param x1: 质量流量（单值）。为 None 时从文件读取。
        :param x2: 介质密度（单值）。为 None 时从文件读取。
        """
        if x1 is not None and x2 is not None:
            # 直接传参模式
            x1_series = pd.Series([float(x1)])
            x2_series = pd.Series([float(x2)])
            data_source = f"直接输入 (X1={x1}, X2={x2})"
        else:
            # 文件读取模式
            x1_series, x2_series, sheet, x1_col, x2_col = self._read_data_from_excel()
            data_source = (
                f"文件 '{os.path.basename(self.file_name)}' "
                f"sheet '{sheet}'，列 '{x1_col}' / '{x2_col}'"
            )

        # ---------- 计算 Y ----------
        y_series = self.calc_y(x1_series, x2_series)

        x1_mean = float(x1_series.mean())
        x2_mean = float(x2_series.mean())
        y_mean  = float(y_series.mean())
        y_std   = float(y_series.std(ddof=1)) if len(y_series) > 1 else 0.0
        y_min   = float(y_series.min())
        y_max   = float(y_series.max())
        n       = len(y_series)

        # ---------- 异常指标 ----------
        indicators = [
            {
                'name': '质量流量 X1（均值）',
                'reference': '设计工况值',
                'value': f'{x1_mean:.6f}'
            },
            {
                'name': '介质密度 X2（均值）',
                'reference': '设计工况值',
                'value': f'{x2_mean:.4f}'
            },
            {
                'name': '诊断输出 Y（均值）',
                'reference': '基准诊断值',
                'value': f'{y_mean:.2f}'
            },
            {
                'name': '诊断输出 Y（标准差）',
                'reference': '波动上限',
                'value': f'{y_std:.2f}'
            },
            {
                'name': '诊断输出 Y（范围）',
                'reference': '正常区间',
                'value': f'{y_min:.2f} ~ {y_max:.2f}'
            },
            {
                'name': '有效数据点',
                'reference': '—',
                'value': str(n)
            },
        ]

        # ---------- 诊断结论 ----------
        diagnosis = {
            'fault_name': '诊断模型评估',
            'location': f'Y 均值 = {y_mean:.2f}（σ = {y_std:.2f}）',
            'analysis': (
                f'基于诊断公式 Y = 2696.17 + 15468.63×X1 − 3.42×X2，'
                f'数据来源：{data_source}。'
                f'共 {n} 个有效样本，X1 均值 = {x1_mean:.6f}，'
                f'X2 均值 = {x2_mean:.4f}，'
                f'诊断输出 Y 均值 = {y_mean:.2f}，标准差 = {y_std:.2f}，'
                f'范围 [{y_min:.2f}, {y_max:.2f}]。'
            ),
        }

        repair_advice = (
            f'诊断模型计算结果如下：\n'
            f'  · 质量流量 (X1) 均值：{x1_mean:.6f}\n'
            f'  · 介质密度 (X2) 均值：{x2_mean:.4f}\n'
            f'  · 诊断输出 (Y)  均值：{y_mean:.2f}，标准差：{y_std:.2f}\n'
            f'  · Y 范围：{y_min:.2f} ~ {y_max:.2f}（共 {n} 个样本）\n\n'
            f'建议将 Y 均值与历史基准值对比，若偏差超过阈值，需检查泵体流量特性及介质状态。'
        )

        return {
            'indicators': indicators,
            'diagnosis': diagnosis,
            'repair_advice': repair_advice,
        }
