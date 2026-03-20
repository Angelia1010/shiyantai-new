# -*- coding: utf-8 -*-
from scipy import signal
import numpy as np
import pandas as pd
import os
import sys

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.append(parent_dir)
from core.diagonis_data_process import FaultDataProcessor
from core.analysis.rule.rule_feature import RuleFeature
from core.analysis.rule.control_valve_wear_detector import ControlValveWearDetector
from core.analysis.rule.plunger_wear_detector import PlungerWearDetector
from core.analysis.rule.rail_wear_detector import RailWearDetector


class HydraulicSystemMonitor:
    """液压系统综合监控器"""
    def __init__(self,window_size=1000, step_size=500):
        self.feature_calculator = RuleFeature()
        self.detectors = [
            PlungerWearDetector(self.feature_calculator),
            RailWearDetector(self.feature_calculator),
            ControlValveWearDetector(self.feature_calculator)
        ]
        self.window_size = window_size  # 窗口大小(样本数)
        self.step_size = step_size      # 滑动步长(样本数)

    def monitor(self, data_dict):
        """执行所有故障检测"""
        results = []

       # 检查数据长度是否足够
        min_length = min(len(data_dict[col]) for col in data_dict.columns)  # 各列的长度最小值
        if min_length < self.window_size:
            raise ValueError(f"数据长度不足，至少需要{self.window_size}个样本")
        
        # 计算窗口数量
        num_windows = (min_length - self.window_size) // self.step_size + 1
        
        # 滑动窗口处理
        for i in range(num_windows):
            start_idx = i * self.step_size
            end_idx = start_idx + self.window_size
            
            # 提取当前窗口数据
            window_data = {
                name: values[start_idx:end_idx] 
                for name, values in data_dict.items()
            }
            
            # 窗口时间戳（假设数据是按时间顺序排列的）
            window_time = f"窗口{i+1}({start_idx}-{end_idx})"
            
            # 执行所有检测器的诊断
            window_results = {
                'window_time': window_time,
                'diagnoses': []
            }
            for detector in self.detectors:
                diagnosis = detector.detect(window_data)
                window_results['diagnoses'].append(diagnosis)
            
            results.append(window_results)
        
        
        return results


# 使用示例
if __name__ == "__main__":
    # 初始化监控系统
    monitor = HydraulicSystemMonitor()
    
    # 设置数据目录路径
    #data_dir = os.path.join(parent_dir, "test_data", "2025.04.14-b")
    #data_dir = os.path.join(parent_dir, "test_data", "20241224-a")
    print(parent_dir)
    data_dir = os.path.join(parent_dir,"test_data", "2025.04.17-c")
    print(f"数据目录检查: {'存在' if os.path.exists(data_dir) else '不存在'} - {data_dir}")
    
    # 数据文件路径
    #data_file = os.path.join(data_dir, "250414151544控制活门磨损0414-1_.tdms")
    #data_file = os.path.join(data_dir, "250414152815控制活门磨损0414-2_.tdms")
    #data_file = os.path.join(data_dir, "250414154044控制活门磨损0414-3_.tdms")
    #data_file = os.path.join(data_dir, "250414154044控制活门磨损0414-3_.tdms")

    data_file = os.path.join(data_dir, "250417134030滑轨磨损 _1.tdms")
    #data_file = os.path.join(data_dir, "250417135300 滑轨磨损_2.tdms")
    #data_file = os.path.join(data_dir, "250417140245滑轨磨损_3.tdms")

    #data_file = os.path.join(data_dir, "2412241402492020001（24A试验载荷谱-随动活塞磨损试验-调载荷谱1）_.tdms")
    processor = FaultDataProcessor(data_file)
    raw_data, columns = processor.get_fault_data(group_channel_list=[])
    print(columns)
    
    if isinstance(raw_data, np.ndarray):
        data_df = pd.DataFrame(raw_data, 
                             index=pd.date_range(start=pd.Timestamp.now(), 
                                               periods=len(raw_data), 
                                               freq='10ms'),
                             columns=columns)
    else:
        data_df = raw_data
   # 给定的列名和对应的采样频率（按顺序）
    column_names = [
        '主油箱压力PT1_MPa', '供油压力PT2_MPa', '控制口压力PT3_MPa', '排油口压力PT4_MPa', 
        '出油口压力PT5_MPa', '回油压力PT6_MPa', '滑油压力PT7_MPa', '增速箱滑油压力PT8_MPa',
        '轴箱滑油压力PT9_MPa', '适配器滑油压力PT10_MPa', '高压气压力APT1_MPa', 
        '低压气压力APT2_MPa', '振动X_m/s2', '振动Y_m/s2', '振动Z_m/s2', '排油流量FM1_L/h',
        '回油流量FM2_L/h', '主油箱液位LT1_mm', '滑油油箱液位LT2_mm', '主油箱温度RTD1_℃',
        '供油温度RTD2_℃', '控制口温度RTD3_℃', '排油口温度RTD4_℃', '出油口温度RTD5_℃',
        '滑油箱温度RTD6_℃', '适配器滑油温度RTD7_℃', '轴箱前温度RTD8_℃', '轴箱后温度RTD9_℃',
        '适配器温度RTD10_℃', '电机温度RTD11_℃', '实验间温度RTD16_℃', '配电柜温度RTD17_℃',
        '加热器出口温度RTD18_℃', '转速_RPM', '转矩_N.M', '排油质量流量_Kg/h', 
        '回油质量流量_Kg/h'
    ]

    # 对应的采样频率（按顺序）
    columns_fs = [
        100, 1000, 2000, 100, 1000, 100, 100, 100, 100, 100,
        100, 100, 1000, 1000, 1000, 100,100 ,10,10, 10, 10, 10,
        10, 10, 10, 10, 10, 10, 10, 10, 10, 10,
        10, 10, 10, 100,100
    ]

    target_fs = 100  # 目标采样频率

    # 检查数据
    '''
    print(len(column_names))
    print(len(columns_fs))
    print(data_df.shape[1])
    fixed_columns = ["振动X_m/s2","振动Y_m/s2"]
    fixed_data = data_df[fixed_columns] if all(col in data_df.columns for col in fixed_columns) else None

    if fixed_data is not None:
        print(fixed_data.head(100))  # 正确调用DataFrame的head()
    
    assert len(column_names) == len(columns_fs) == data_df.shape[1], "列名、采样频率和数据列数不匹配"
    '''
    # 确保输入数据正确
    assert len(column_names) == len(columns_fs) == data_df.shape[1], "列名、采样频率和数据列数不匹配"
    
    # 创建时间索引（假设原始数据是等间隔采样的）
    original_length = len(data_df)
    original_duration = original_length / max(columns_fs)  # 以最高频率计算总时长
    original_time = np.linspace(0, original_duration, original_length)
    
    # 创建目标时间轴
    target_length = int(original_duration * target_fs)
    target_time = np.linspace(0, original_duration, target_length)
    
    # 初始化结果DataFrame
    resampled_data = pd.DataFrame(index=target_time)
    
    # 逐列处理
    for col_name, original_fs in zip(column_names, columns_fs):
        col_data = data_df[col_name].values
        
        if original_fs == target_fs:
            # 如果频率相同，直接使用线性插值到新时间轴
            resampled_data[col_name] = np.interp(target_time, original_time, col_data)
        elif original_fs > target_fs:
            # 降采样 - 先抗混叠滤波，然后插值
            # 计算降采样因子
            factor = int(original_fs / target_fs)
            # 使用decimate进行降采样（包含抗混叠滤波）
            resampled_col = signal.decimate(col_data, factor, ftype='fir')
            # 插值到目标时间轴
            resampled_time = np.linspace(0, original_duration, len(resampled_col))
            resampled_data[col_name] = np.interp(target_time, resampled_time, resampled_col)
        else:
            # 上采样 - 使用插值
            resampled_data[col_name] = np.interp(target_time, original_time, col_data)
    
    # 处理可能的NaN值
    resampled_data = resampled_data.interpolate(method='linear')
    
    # 处理完整数据集
    print(f"\n开始处理数据，总行数: {len(resampled_data)}")
    # 执行监控
    results = monitor.monitor(resampled_data)
    
    
    # 打印结果（按综合评分降序排序）
    for i, window_result in enumerate(results):
        print(f"\n=== {window_result['window_time']} 诊断结果 ===")
        
        # 按 score 降序排序诊断结果
        sorted_diagnoses = sorted(window_result['diagnoses'], key=lambda x: x['score'], reverse=True)
        
        # 只输出得分最高的结果（如果存在多个相同最高分，则输出第一个）
        if sorted_diagnoses:
            top_diagnosis = sorted_diagnoses[0]
            print(f"\n[最高优先级] 故障类型: {top_diagnosis['fault_name']}")
            print(f"综合评分: {top_diagnosis['score']:.2f}")
            print(f"严重等级: {top_diagnosis['severity']}")
            print(f"建议措施: {top_diagnosis['action']}")
            print("触发告警:")
            for alert in top_diagnosis['alerts']:
                print(f" - {alert}")
            
            # 如果有其他相同最高分的结果，可以额外标注（可选）
            if len(sorted_diagnoses) > 1 and sorted_diagnoses[0]['score'] == sorted_diagnoses[1]['score']:
                print("\n注意：存在多个相同最高分的诊断结果，请人工复核！")
    '''
    # 第一步：收集所有窗口的诊断结果
    all_diagnoses = []
    for window_result in results:
        for diagnosis in window_result['diagnoses']:
            # 确保每个诊断结果都包含时间窗口信息
            diagnosis_with_window = diagnosis.copy()  # 避免修改原始数据
            diagnosis_with_window['window_time'] = window_result['window_time']
            all_diagnoses.append(diagnosis_with_window)

    # 第二步：全局排序（按score降序，score相同则按severity降序）
    all_diagnoses_sorted = sorted(
        all_diagnoses,
        key=lambda x: (-x['score'], x['severity']),  # 使用负号实现降序
        reverse=False  # 必须设为False，因为key中已经用了负号
    )

    # 调试用：打印排序后的完整列表
    print("\n=== 所有诊断结果排序后 ===")
    for idx, diagnosis in enumerate(all_diagnoses_sorted, 1):
        print(f"{idx}. {diagnosis['fault_name']} (评分: {diagnosis['score']:.2f}, 窗口: {diagnosis['window_time']})")

    # 第三步：输出全局最高分结果
    if all_diagnoses_sorted:
        top_diagnosis = all_diagnoses_sorted[0]
        print("\n=== 全局最高分诊断结果 ===")
        print(f"时间窗口: {top_diagnosis['window_time']}")
        print(f"\n[最高优先级] 故障类型: {top_diagnosis['fault_name']}")
        print(f"综合评分: {top_diagnosis['score']:.2f}")
        print(f"严重等级: {top_diagnosis['severity']}")
        print(f"建议措施: {top_diagnosis['action']}")
        print("触发告警:")
        for alert in top_diagnosis['alerts']:
            print(f" - {alert}")

        # 检查同分情况（浮点数精度处理）
        same_top_scores = [
            d for d in all_diagnoses_sorted 
            if abs(d['score'] - top_diagnosis['score']) < 0.001
        ]
        
        if len(same_top_scores) > 1:
            print(f"\n⚠️ 注意：存在 {len(same_top_scores)} 个全局最高分（{top_diagnosis['score']:.2f}）故障:")
            for idx, diagnosis in enumerate(same_top_scores[1:], start=1):
                print(f"{idx}. {diagnosis['fault_name']} (窗口: {diagnosis['window_time']}, 严重度: {diagnosis['severity']})")
    else:
        print("\n无有效诊断结果")
    ''' 