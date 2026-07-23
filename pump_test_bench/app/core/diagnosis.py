# -*- coding: utf-8 -*-
import os
import sys
import pandas as pd

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(parent_dir)


class Diagnosis:
    COL_MASS_FLOW = '质量流量'
    COL_DENSITY = '介质密度'
    COL_MASS_FLOW_1 = '回油质量流量1'
    COL_MASS_FLOW_2 = '回油质量流量2'
    COL_FLOW_1 = '回油流量1-1'
    COL_FLOW_2 = '回油流量1-2'

    FLOW_METER_THRESHOLD = 0.15
    MASS_FLOW_UNIT_CONVERSION = 3600.0

    def __init__(self, file_name, conf_file):
        self.file_name = file_name

    # ------------------------------------------------------------------ #
    #  仿真转速模型公式                                                         #
    # ------------------------------------------------------------------ #
    @staticmethod
    def calc_y(x1, x2):
        """
        仿真转速模型: Y = 2696.17 + 15468.63 * X1 - 3.42 * X2
        X1: 质量流量（kg/s）
        X2: 介质密度（kg/m³）
        Y:  仿真转速（rad/s）
        """
        return 2696.17 + 15468.63 * x1 - 3.42 * x2

    @staticmethod
    def calc_flow_from_speed(y, density):
        """
        根据转速计算理论流量
        转速-流量公式: q = 0.304921 * f + 0.210230
        其中 f 为频率（Hz），和转速 y（rad/s）的关系为 y = f * 6 / (2π)
        所以 f = y * 2π / 6
        q 为输出流量（L/h）
        
        返回: 理论体积流量（L/h）
        """
        import math
        f = y * 2 * math.pi / 6
        q = 0.304921 * f + 0.210230
        return q

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
        读取 Excel 或 TXT 文件，遍历所有 sheet，找到含 X1 列的第一个 sheet。
        X2（介质密度）列不存在时使用默认值 DEFAULT_DENSITY。
        返回 (x1_series, x2_series, sheet_name, x1_col, x2_col)
        """
        if self.file_name.lower().endswith('.txt'):
            return self._read_data_from_txt()
        
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
                x1_converted = valid[x1_col] / self.MASS_FLOW_UNIT_CONVERSION
                return (
                    x1_converted.reset_index(drop=True),
                    valid[x2_col].reset_index(drop=True),
                    sheet, x1_col, x2_col,
                )
            else:
                x1 = df[x1_col].dropna() / self.MASS_FLOW_UNIT_CONVERSION
                x2 = pd.Series([self.DEFAULT_DENSITY] * len(x1))
                x2_col = f'{self.COL_DENSITY}（默认{self.DEFAULT_DENSITY}）'
                return x1.reset_index(drop=True), x2, sheet, x1_col, x2_col

        raise ValueError(
            f"文件 '{os.path.basename(self.file_name)}' 中未找到含 '{self.COL_MASS_FLOW}' 的 sheet"
        )
    
    def _read_data_from_txt(self):
        """
        读取 TXT 文件（制表符分隔，第1行为列名，第2-3行为空，第4行开始为数据）。
        返回 (x1_series, x2_series, sheet_name, x1_col, x2_col)
        """
        encoding = None
        column_names = []
        
        for enc in ['utf-8', 'gbk']:
            try:
                with open(self.file_name, 'r', encoding=enc) as f:
                    header_line = f.readline().strip()
                    if header_line:
                        column_names = header_line.split('\t')
                        encoding = enc
                        break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if not column_names:
            raise ValueError(f"无法读取文件 '{os.path.basename(self.file_name)}' 的表头")
        
        try:
            df = pd.read_csv(
                self.file_name,
                sep='\t',
                skiprows=[0, 1, 2],
                header=None,
                names=column_names,
                index_col=False,
                skip_blank_lines=True,
                encoding=encoding or 'utf-8',
                on_bad_lines='skip',
                dtype=str
            )
        except Exception as e:
            raise ValueError(f"读取txt文件失败: {e}")
        
        expected_cols = len(column_names)
        actual_cols = len(df.columns)
        
        if actual_cols != expected_cols:
            if actual_cols > expected_cols:
                df = df.iloc[:, :expected_cols]
            else:
                while len(df.columns) < expected_cols:
                    df[f'_extra_{len(df.columns)}'] = ''
                df = df[column_names]
        
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        print(f"[诊断] TXT文件列名: {[col for col in df.columns if '质量流量' in col or '密度' in col]}")
        
        x1_col = self._find_col(df, self.COL_MASS_FLOW)
        if not x1_col:
            raise ValueError(
                f"文件 '{os.path.basename(self.file_name)}' 中未找到含 '{self.COL_MASS_FLOW}' 的列"
            )
        
        x2_col = self._find_col(df, self.COL_DENSITY)
        if x2_col:
            valid = df[[x1_col, x2_col]].dropna()
            x1_converted = valid[x1_col] / self.MASS_FLOW_UNIT_CONVERSION
            return (
                x1_converted.reset_index(drop=True),
                valid[x2_col].reset_index(drop=True),
                'data', x1_col, x2_col,
            )
        else:
            x1 = df[x1_col].dropna() / self.MASS_FLOW_UNIT_CONVERSION
            x2 = pd.Series([self.DEFAULT_DENSITY] * len(x1))
            x2_col = f'{self.COL_DENSITY}（默认{self.DEFAULT_DENSITY}）'
            return x1.reset_index(drop=True), x2, 'data', x1_col, x2_col

    # ------------------------------------------------------------------ #
    #  诊断主流程                                                           #
    # ------------------------------------------------------------------ #
    def diagnosis_process(self, x1=None, x2=None, density=None):
        """
        执行故障诊断，返回 indicators / diagnosis / repair_advice。

        :param x1: 质量流量（单值）。为 None 时从文件读取。
        :param x2: 介质密度（单值）。为 None 时从文件读取。
        :param density: 介质密度（从前端传入，用于流量计诊断）。
        """
        flow_meter_results = self._diagnose_flow_meters(density)
        
        indicators = []
        for fm_result in flow_meter_results:
            indicators.extend(fm_result['indicators'])

        fault_parts = []
        analysis_parts = []
        
        if flow_meter_results:
            repair_advice = '【流量计诊断结果】\n'
            for fm_result in flow_meter_results:
                repair_advice += fm_result['repair_advice'] + '\n'
                if fm_result['status'] == '异常':
                    fault_parts.append(fm_result['name'])
                    analysis_parts.append(fm_result['analysis'])
        else:
            repair_advice = '未检测到流量计数据，无法进行诊断。\n'
        
        if fault_parts:
            diagnosis = {
                'fault_name': '涡轮流量计状态异常',
                'location': '、'.join(fault_parts),
                'analysis': '\n'.join(analysis_parts),
            }
            repair_advice += '\n建议：对异常流量计进行校准或更换。'
        else:
            diagnosis = {
                'fault_name': '涡轮流量计状态正常',
                'location': '所有流量计',
                'analysis': '所有流量计状态正常，理论流量与实际流量偏差在允许范围内。',
            }

        return {
            'indicators': indicators,
            'diagnosis': diagnosis,
            'repair_advice': repair_advice,
        }

    def _read_flow_meter_data(self):
        """
        从文件中读取流量计相关数据
        返回: (mass_flow_1_series, mass_flow_2_series, flow_1_series, flow_2_series, df)
        """
        if self.file_name.lower().endswith('.txt'):
            return self._read_flow_meter_data_from_txt()
        
        xl = pd.ExcelFile(self.file_name, engine='openpyxl')
        for sheet in xl.sheet_names:
            df = xl.parse(sheet, dtype=object)
            for col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            mass_flow_1_col = self._find_col(df, self.COL_MASS_FLOW_1)
            mass_flow_2_col = self._find_col(df, self.COL_MASS_FLOW_2)
            flow_1_col = self._find_col(df, self.COL_FLOW_1)
            flow_2_col = self._find_col(df, self.COL_FLOW_2)
            
            if mass_flow_1_col or mass_flow_2_col:
                return (
                    (df[mass_flow_1_col].dropna() / self.MASS_FLOW_UNIT_CONVERSION).reset_index(drop=True) if mass_flow_1_col else None,
                    (df[mass_flow_2_col].dropna() / self.MASS_FLOW_UNIT_CONVERSION).reset_index(drop=True) if mass_flow_2_col else None,
                    df[flow_1_col].dropna().reset_index(drop=True) if flow_1_col else None,
                    df[flow_2_col].dropna().reset_index(drop=True) if flow_2_col else None,
                    df
                )
        
        return None, None, None, None, None

    def _read_flow_meter_data_from_txt(self):
        """
        从TXT文件中读取流量计相关数据
        """
        encoding = None
        column_names = []
        
        for enc in ['utf-8', 'gbk']:
            try:
                with open(self.file_name, 'r', encoding=enc) as f:
                    header_line = f.readline().strip()
                    if header_line:
                        column_names = header_line.split('\t')
                        encoding = enc
                        break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if not column_names:
            return None, None, None, None, None
        
        try:
            df = pd.read_csv(
                self.file_name,
                sep='\t',
                skiprows=[0, 1, 2],
                header=None,
                names=column_names,
                index_col=False,
                skip_blank_lines=True,
                encoding=encoding or 'utf-8',
                on_bad_lines='skip',
                dtype=str
            )
        except Exception:
            return None, None, None, None, None
        
        expected_cols = len(column_names)
        actual_cols = len(df.columns)
        
        if actual_cols != expected_cols:
            if actual_cols > expected_cols:
                df = df.iloc[:, :expected_cols]
            else:
                while len(df.columns) < expected_cols:
                    df[f'_extra_{len(df.columns)}'] = ''
                df = df[column_names]
        
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        mass_flow_1_col = self._find_col(df, self.COL_MASS_FLOW_1)
        mass_flow_2_col = self._find_col(df, self.COL_MASS_FLOW_2)
        flow_1_col = self._find_col(df, self.COL_FLOW_1)
        flow_2_col = self._find_col(df, self.COL_FLOW_2)
        
        return (
            (df[mass_flow_1_col].dropna() / self.MASS_FLOW_UNIT_CONVERSION).reset_index(drop=True) if mass_flow_1_col else None,
            (df[mass_flow_2_col].dropna() / self.MASS_FLOW_UNIT_CONVERSION).reset_index(drop=True) if mass_flow_2_col else None,
            df[flow_1_col].dropna().reset_index(drop=True) if flow_1_col else None,
            df[flow_2_col].dropna().reset_index(drop=True) if flow_2_col else None,
            df
        )

    def _diagnose_flow_meters(self, density=None):
        """
        诊断两个流量计的状态
        
        :param density: 介质密度（kg/m³），从前端传入
        :return: 流量计诊断结果列表
        """
        import math
        
        results = []
        
        mass_flow_1, mass_flow_2, flow_1, flow_2, df = self._read_flow_meter_data()
        
        if density is None:
            density = self.DEFAULT_DENSITY
        
        if mass_flow_1 is not None and len(mass_flow_1) > 0:
            result = self._diagnose_single_flow_meter(
                mass_flow_series=mass_flow_2,
                actual_flow_series=flow_1,
                density=density,
                meter_name='回路1流量计',
                mass_flow_col_name=self.COL_MASS_FLOW_2,
                flow_col_name=self.COL_FLOW_1
            )
            results.append(result)

        if mass_flow_1 is not None and len(mass_flow_1) > 0:
            result = self._diagnose_single_flow_meter(
                mass_flow_series=mass_flow_2,
                actual_flow_series=flow_2,
                density=density,
                meter_name='回路2流量计',
                mass_flow_col_name=self.COL_MASS_FLOW_2,
                flow_col_name=self.COL_FLOW_2
            )
            results.append(result)
        # if mass_flow_2 is not None and len(mass_flow_2) > 0:
        #     result = self._diagnose_single_flow_meter(
        #         mass_flow_series=mass_flow_2,
        #         actual_flow_series=flow_2,
        #         density=density,
        #         # meter_name='流量计2',
        #         meter_name='流量计',
        #         mass_flow_col_name=self.COL_MASS_FLOW_2,
        #         flow_col_name=self.COL_FLOW_2
        #     )
        #     results.append(result)
        
        return results

    def _diagnose_single_flow_meter(self, mass_flow_series, actual_flow_series, density, 
                                     meter_name, mass_flow_col_name, flow_col_name):
        """
        诊断单个流量计
        
        :param mass_flow_series: 质量流量数据序列（kg/s）
        :param actual_flow_series: 实际流量数据序列（L/h）
        :param density: 介质密度（kg/m³）
        :param meter_name: 流量计名称
        :param mass_flow_col_name: 质量流量列名
        :param flow_col_name: 流量列名
        :return: 诊断结果字典
        """
        import math
        
        mass_flow_mean = float(mass_flow_series.mean())
        
        y = self.calc_y(mass_flow_mean, density)
        
        theoretical_flow = self.calc_flow_from_speed(y, density)
        
        indicators = [
            {
                'name': f'{meter_name} 质量流量均值',
                'reference': '输入值',
                'value': f'{mass_flow_mean:.6f} kg/s'
            },
            {
                'name': f'{meter_name} 仿真转速',
                'reference': '计算值',
                'value': f'{y:.2f} rad/s'
            },
            {
                'name': f'{meter_name} 理论流量',
                'reference': '计算值',
                'value': f'{theoretical_flow:.2f} L/h'
            },
        ]
        
        if actual_flow_series is not None and len(actual_flow_series) > 0:
            actual_flow_mean = float(actual_flow_series.mean())
            
            if abs(actual_flow_mean) > 1e-6:
                relative_deviation = abs(theoretical_flow - actual_flow_mean) / abs(actual_flow_mean)
            else:
                relative_deviation = abs(theoretical_flow - actual_flow_mean)
            
            is_abnormal = relative_deviation > self.FLOW_METER_THRESHOLD
            
            indicators.append({
                'name': f'{meter_name} 实际流量均值',
                'reference': '测量值',
                'value': f'{actual_flow_mean:.2f} L/h'
            })
            indicators.append({
                'name': f'{meter_name} 流量偏差',
                'reference': f'阈值 {self.FLOW_METER_THRESHOLD*100:.1f}%',
                'value': f'{relative_deviation*100:.2f}%{" ⚠️超限" if is_abnormal else ""}'
            })
            
            status = '异常' if is_abnormal else '正常'
            analysis = (
                f'{meter_name}：质量流量均值={mass_flow_mean:.6f} kg/s，'
                f'仿真转速={y:.2f} rad/s，'
                f'理论流量={theoretical_flow:.2f} L/h，'
                f'实际流量={actual_flow_mean:.2f} L/h，'
                f'相对偏差={relative_deviation*100:.2f}%，'
                f'阈值={self.FLOW_METER_THRESHOLD*100:.1f}%，'
                f'判定为{status}。'
            )
            repair_advice = (
                f'  · {meter_name}：理论流量={theoretical_flow:.2f} L/h，'
                f'实际流量={actual_flow_mean:.2f} L/h，'
                f'偏差={relative_deviation*100:.2f}%'
                f'{" ⚠️异常" if is_abnormal else " ✓正常"}\n'
            )
        else:
            is_abnormal = False
            status = '无法诊断（缺少实际流量数据）'
            analysis = (
                f'{meter_name}：质量流量均值={mass_flow_mean:.6f} kg/s，'
                f'仿真转速={y:.2f} rad/s，'
                f'理论流量={theoretical_flow:.2f} L/h，'
                f'但缺少实际流量数据，无法进行对比诊断。'
            )
            repair_advice = (
                f'  · {meter_name}：理论流量={theoretical_flow:.2f} L/h，'
                f'缺少实际流量数据（L/h）\n'
            )
        
        return {
            'name': meter_name,
            'status': status,
            'is_abnormal': is_abnormal,
            'analysis': analysis,
            'repair_advice': repair_advice,
            'indicators': indicators
        }
