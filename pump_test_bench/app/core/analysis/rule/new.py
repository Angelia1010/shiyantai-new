# -*- coding: utf-8 -*-
from scipy import signal
import pywt
import yaml
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import os
import sys
from tqdm import tqdm
from collections import deque, defaultdict
from scipy import stats
from scipy.fft import fft
from dataclasses import dataclass
from typing import List, Dict, Deque, Tuple, Optional

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.append(parent_dir)
from abc import ABC, abstractmethod
from core.diagonis_data_process import FaultDataProcessor

class HydraulicFeatureExtractor:
    """液压系统特征提取器"""
    
    def __init__(self, column_mapping=None):
        self.column_mapping = column_mapping or self.default_column_mapping()
        self.feature_cache = defaultdict(list)
        self.window_size = 100  # 1分钟数据(假设1Hz采样)
        self.reverse_mapping = {v: k for k, v in self.column_mapping.items()}
    @staticmethod
    def default_column_mapping():
        return {
            "主油箱压力PT1_MPa": "PT1",
            "供油压力PT2_MPa": "PT2",
            "控制口压力PT3_MPa": "PT3",
            "排油口压力PT4_MPa": "PT4",
            "出油口压力PT5_MPa": "PT5",
            "回油压力PT6_MPa": "PT6",
            "滑油压力PT7_MPa": "PT7",
            "增速箱滑油压力PT8_MPa": "PT8",
            "轴箱滑油压力PT9_MPa": "PT9",
            "适配器滑油压力PT10_MPa": "PT10",
            "高压气压力APT1_MPa": "APT1",
            "低压气压力APT2_MPa": "APT2",
            "振动X_m/s2": "X",
            "振动Y_m/s2": "Y",
            "振动Z_m/s2": "Z",
            "排油流量FM1_L/h": "FM1",
            "回油流量FM2_L/h": "FM2",
            "主油箱液位LT1_mm": "LT1",
            "滑油油箱液位LT2_mm": "LT2",
            "主油箱温度RTD1_℃": "RTD1",
            "供油温度RTD2_℃": "RTD2",
            "控制口温度RTD3_℃": "RTD3",
            "排油口温度RTD4_℃": "RTD4",
            "出油口温度RTD5_℃": "RTD5",
            "滑油箱温度RTD6_℃": "RTD6",
            "适配器滑油温度RTD7_℃": "RTD7",
            "轴箱前温度RTD8_℃": "RTD8",
            "轴箱后温度RTD9_℃": "RTD9",
            "适配器温度RTD10_℃": "RTD10",
            "电机温度RTD11_℃": "RTD11",
            "实验间温度RTD16_℃": "RTD16",
            "配电柜温度RTD17_℃": "RTD17",
            "加热器出口温度RTD18_℃": "RTD18",
            "转速_RPM": "speed",
            "转矩_N.M": "torque",
            "排油质量流量_Kg/h": "drain_mass_flow",
            "回油质量流量_Kg/h": "return_mass_flow"
        }
    
    def get_key_by_value(self, value: str) -> str:
        """
        根据value获取原始列名(key)
        
        参数:
            value: 标准化后的信号名 (如"PT1")
        
        返回:
            原始列名 (如"主油箱压力PT1_MPa")
        
        示例:
            >>> extractor.get_key_by_value("PT1")
            '主油箱压力PT1_MPa'
        """
        return self.reverse_mapping.get(value, value)  # 如果找不到返回原值

    def _get_signal_name(self, col_name):
        """获取标准化信号名称"""
        return self.column_mapping.get(col_name, col_name)
    
    def calculate_pressure_features(self, pressure_data: np.ndarray) -> dict:
        """计算压力信号特征集"""
        return {
            'mean': np.mean(pressure_data),
            'std': np.std(pressure_data),
            'rms': np.sqrt(np.mean(np.square(pressure_data))),
            'peak2peak': np.ptp(pressure_data),
            'skewness': stats.skew(pressure_data),
            'kurtosis': stats.kurtosis(pressure_data),
            'pulse_factor': np.max(np.abs(pressure_data)) / np.mean(np.abs(pressure_data)),
            'crest_factor': np.max(np.abs(pressure_data)) / np.sqrt(np.mean(np.square(pressure_data)))
        }
    
    def calculate_flow_features(self, flow_data: np.ndarray) -> dict:
        """计算流量信号特征集"""
        diff = np.diff(flow_data)
        return {
            'mean': np.mean(flow_data),
            'std': np.std(flow_data),
            'trend': np.polyfit(range(len(flow_data)), flow_data, 1)[0],
            'fluctuation': np.mean(np.abs(diff)),
            'max_gradient': np.max(np.abs(diff))
        }
    
    def calculate_vibration_features(self, vib_data: np.ndarray, sample_rate=100) -> dict:
        """计算振动信号特征集"""
        n = len(vib_data)
        vib_data = vib_data - np.mean(vib_data)  # 去除直流分量
        yf = fft(vib_data)
        xf = np.linspace(0, sample_rate/2, n//2)
        spectrum = np.abs(yf[:n//2])
        
        return {
            'rms': np.sqrt(np.mean(np.square(vib_data))),
            'peak2peak': np.ptp(vib_data),
            'kurtosis': stats.kurtosis(vib_data),
            'main_freq': xf[np.argmax(spectrum[1:]) + 1],  # 跳过0Hz
            'spectral_centroid': np.sum(xf * spectrum) / np.sum(spectrum),
            'harmonic_ratio': np.max(spectrum) / np.sum(spectrum)
        }
    
    def calculate_temperature_features(self, temp_data: np.ndarray) -> dict:
        """计算温度信号特征集"""
        grad = np.gradient(temp_data)
        return {
            'mean': np.mean(temp_data),
            'gradient_mean': np.mean(grad),
            'gradient_max': np.max(np.abs(grad)),
            'stability': 1.0 / np.std(temp_data) if np.std(temp_data) > 0 else 0
        }
    
    def extract_guide_rail_features(self, raw_data: dict) -> dict:
        """提取滑轨磨损专用特征"""
        features = {}
        
        # 振动信号包络分析
        x_column = self.get_key_by_value("X")
        y_column = self.get_key_by_value("Y")
        if x_column in raw_data and y_column in raw_data:
            x_env = np.abs(signal.hilbert(raw_data[x_column]))
            y_env = np.abs(signal.hilbert(raw_data[y_column]))
            
            features.update({
                'vib_X_envelope_mean': np.mean(x_env),
                'vib_Y_envelope_std': np.std(y_env),
                'vib_XY_ratio': np.mean(x_env) / (np.mean(y_env) + 1e-6)
            })
        
        PT2_column = self.get_key_by_value("PT2")
        FM2_column = self.get_key_by_value("FM2")
        # 压力-流量耦合特征
        if PT2_column in raw_data and FM2_column in raw_data:
            cross_corr = np.correlate(
                (raw_data[PT2_column] - np.mean(raw_data[PT2_column])),
                (raw_data[FM2_column] - np.mean(raw_data[FM2_column])),
                mode='full'
            )
            features['PT2_FM2_correlation'] = np.max(cross_corr)
        
        # 温度梯度特征
        RTD6_column = self.get_key_by_value("RTD6")
        if RTD6_column in raw_data:
            grad = np.gradient(raw_data[RTD6_column])
            features.update({
                'RTD6_gradient_max': np.max(np.abs(grad)),
                'RTD6_gradient_std': np.std(grad)
            })
        
        return features
    
    def extract_all_features(self, raw_data: dict) -> dict:
        """从原始数据提取所有特征"""
        features = {}
        
        # 压力信号特征
        for pt in ['PT1', 'PT2', 'PT3', 'PT4', 'PT5', 'PT6', 'PT7', 'PT8', 'PT9', 'PT10']:
            
            column = self.get_key_by_value(pt)
            #print("self.calculate_pressure_features(raw_data[pt]).items()")
            #print(self.calculate_pressure_features(raw_data[column]).items())
            features.update({
                f"{pt}_{k}": v for k, v in 
                self.calculate_pressure_features(raw_data[column]).items()
            })
        
        # 流量信号特征
        for fm in ['FM1', 'FM2', 'drain_mass_flow', 'return_mass_flow']:
            column = self.get_key_by_value(fm)
            features.update({
                f"{fm}_{k}": v for k, v in 
                self.calculate_flow_features(raw_data[column]).items()
            })
        
        # 振动信号特征
        for axis in ['X', 'Y', 'Z']:
            column = self.get_key_by_value(axis)
            features.update({
                f"vib_{axis}_{k}": v for k, v in 
                self.calculate_vibration_features(raw_data[column]).items()
            })
        
        # 温度信号特征
        for rtd in ['RTD1', 'RTD2','RTD3', 'RTD4','RTD5','RTD6','RTD7','RTD8','RTD9','RTD10','RTD11','RTD16','RTD17','RTD18']:
            column = self.get_key_by_value(rtd)
            features.update({
                f"{rtd}_{k}": v for k, v in 
                self.calculate_temperature_features(raw_data[column]).items()
            })
        
        # 转速和转矩特征
        speed_column = self.get_key_by_value("speed")
        if speed_column:
            features.update({
                'speed_mean': np.mean(raw_data[speed_column]),
                'speed_fluctuation': np.std(raw_data[speed_column]) / np.mean(raw_data[speed_column])
            })
        torque_colum = self.get_key_by_value("torque")
        if torque_colum:
            features.update({
                'torque_mean': np.mean(raw_data[torque_colum]),
                'torque_ripple': np.ptp(raw_data[torque_colum]) / np.mean(raw_data[torque_colum])
            })
        
        # 添加滑轨磨损专用特征
        features.update(self.extract_guide_rail_features(raw_data))
        
        # 缓存特征用于趋势分析
        for feat, val in features.items():
            self.feature_cache[feat].append(val)
            if len(self.feature_cache[feat]) > self.window_size:
                self.feature_cache[feat].pop(0)
        
        return features
    
    def get_trend_analysis(self, feature_name: str) -> dict:
        """获取特征趋势分析"""
        history = self.feature_cache.get(feature_name, [])
        if len(history) < 3:
            return {'status': 'INSUFFICIENT_DATA'}
        
        x = np.arange(len(history))
        y = np.array(history)
        slope = np.polyfit(x, y, 1)[0]
        
        trend_status = "STABLE"
        if slope > 0.1 * np.mean(y):
            trend_status = "RAPID_INCREASING"
        elif slope > 0.05 * np.mean(y):
            trend_status = "GRADUAL_INCREASING"
        elif slope < -0.1 * np.mean(y):
            trend_status = "RAPID_DECREASING"
        elif slope < -0.05 * np.mean(y):
            trend_status = "GRADUAL_DECREASING"
        
        return {
            'status': trend_status,
            'slope': slope,
            'current': y[-1],
            'mean': np.mean(y),
            'std': np.std(y)
        }


@dataclass
class DiagnosticRule:
    """诊断规则定义"""
    rule_id: str          # 规则ID (如"PW-001")
    signal: str           # 监测信号 (如"PT3_mean")
    operator: str         # 比较运算符 (">", "<", ">=", "<=", "==", "!=")
    threshold: float      # 阈值
    weight: float         # 权重 (0-1)
    severity: int        # 严重等级 (1-3)
    description: str     # 规则描述
    recommendation: str  # 处理建议


@dataclass
class RuleEvaluationResult:
    """规则评估结果（增强版）"""
    rule_id: str
    is_triggered: bool
    current_value: float
    baseline: float
    deviation: float
    threshold: float
    weight: float
    severity: int
    normal_range: Tuple[Optional[float], Optional[float]]  # 正常范围
    recommendation: str = ""  # 新增建议字段
    trend: str = "stable"     # 新增趋势字段


class RuleBasedDiagnosticEngine:
    """增强版基于规则的诊断引擎"""
    
    def __init__(self, window_size: int = 60):
        """
        Args:
            window_size: 滑动窗口大小（用于计算动态基线）
        """
        self.window_size = window_size
        self.data_window = {
            'timestamp': deque(maxlen=window_size),
            **{sig: deque(maxlen=window_size) for sig in self.required_signals()}
        }
        self.rules = self.define_rules()
        self._initialize_baseline_ranges()
    
    def _initialize_baseline_ranges(self):
        """初始化各信号的正常范围基线"""
        self.baseline_ranges = {
            # 压力信号
            'PT2_mean': (0.8, None),    # 主供油压力
            'PT2_std': (0, 0.06),
            'PT3_mean': (2.5, 5.5),     # 控制口压力
            'PT4_peak2peak': (0, 0.1),
            
            # 振动信号
            'vib_X_peak2peak': (0.65, 6.15),
            'vib_Y_peak2peak': (None, 8.0),  # Y方向振动上限
            'vib_Z_rms': (None, 4.0),
            
            # 温度信号
            'RTD6_mean': (30, 80),      # 滑油温度
            'RTD3_gradient': (-0.5, 0.5),
            
            # 流量信号
            'FM2_mean': (360, 4800),
            'FM2_fluctuation': (None, 30)
        }
    
    @classmethod
    def required_signals(cls) -> List[str]:
        """需要监测的信号列表（由子类实现）"""
        raise NotImplementedError
        
    @classmethod
    def define_rules(cls) -> List['DiagnosticRule']:
        """定义诊断规则集（由子类实现）"""
        raise NotImplementedError
    
    def update_data_window(self, features: Dict[str, float]):
        """更新数据窗口（带数据有效性检查）"""
        valid_features = {
            k: v for k, v in features.items() 
            if k in self.required_signals() and not np.isnan(v)
        }
        
        self.data_window['timestamp'].append(datetime.now())
        for sig in self.required_signals():
            self.data_window[sig].append(valid_features.get(sig, 0.0))
    
    def evaluate(self, features: Dict[str, float]) -> List[RuleEvaluationResult]:
        """增强版规则评估"""
        self.update_data_window(features)
        results = []
        
        for rule in self.rules:
            # 获取当前值和计算基线
            current = features.get(rule.signal, np.nan)
            if np.isnan(current):
                continue
                
            baseline = self._calculate_baseline(rule.signal)
            normal_range = self.baseline_ranges.get(rule.signal, (None, None))
            
            # 评估条件（考虑正常范围）
            triggered, condition_met = self._check_condition(
                current=current,
                baseline=baseline,
                operator=rule.operator,
                threshold=rule.threshold,
                normal_range=normal_range
            )
            
            # 计算趋势和置信度
            trend = self._get_trend_status(rule.signal)
            confidence = self._calculate_confidence(
                current, baseline, normal_range, trend
            )
            
            # 构建结果对象
            results.append(RuleEvaluationResult(
                rule_id=rule.rule_id,
                is_triggered=triggered,
                current_value=current,
                baseline=baseline,
                deviation=current - baseline,
                threshold=rule.threshold,
                weight=rule.weight,
                severity=rule.severity,
                normal_range=normal_range,
                recommendation=rule.recommendation
            ))
        
        return sorted(results, key=lambda x: x.weight * x.severity, reverse=True)
    
    def _calculate_baseline(self, signal: str) -> float:
        """智能基线计算（优先使用预设范围）"""
        # 如果有预设范围且窗口数据不足
        if signal in self.baseline_ranges and len(self.data_window[signal]) < 10:
            lower, upper = self.baseline_ranges[signal]
            if lower is not None and upper is not None:
                return (lower + upper) / 2
            elif lower is not None:
                return lower * 1.1
            elif upper is not None:
                return upper * 0.9
        
        # 使用滑动窗口统计量
        print("77777777777777777")
        print(signal)
        print(self.data_window)
        if len(self.data_window[signal]) == 0:
            return 0.0
        
        # 对振动信号使用RMS值作为基线
        if signal.startswith('vib_'):
            return np.sqrt(np.mean(np.square(self.data_window[signal])))
            
        return np.median(self.data_window[signal])  # 使用中位数更抗噪
    
    def _check_condition(self, current: float, baseline: float, 
                       operator: str, threshold: float,
                       normal_range: Tuple[Optional[float], Optional[float]]) -> Tuple[bool, bool]:
        """
        增强条件检查
        返回: (是否触发告警, 是否满足条件)
        """
        lower_bound, upper_bound = normal_range
        condition_met = False
        
        # 检查是否超出正常范围（优先级最高）
        if upper_bound is not None and current > upper_bound:
            condition_met = operator in [">", ">=", "!="]
        elif lower_bound is not None and current < lower_bound:
            condition_met = operator in ["<", "<=", "!="]
        else:
            # 常规条件检查
            if operator == ">":
                condition_met = current > (baseline + threshold)
            elif operator == "<":
                condition_met = current < (baseline - threshold)
            elif operator == ">=":
                condition_met = current >= (baseline + threshold)
            elif operator == "<=":
                condition_met = current <= (baseline - threshold)
            elif operator == "==":
                condition_met = abs(current - baseline) <= threshold
            elif operator == "!=":
                condition_met = abs(current - baseline) > threshold
        
        # 是否触发告警（考虑严重程度）
        is_triggered = condition_met and (abs(current - baseline) > threshold * 0.3)
        return is_triggered, condition_met
    
    def _get_trend_status(self, signal: str) -> str:
        """获取信号趋势状态"""
        history = list(self.data_window[signal])
        if len(history) < 3:
            return "insufficient_data"
        
        x = np.arange(len(history))
        y = np.array(history)
        slope = np.polyfit(x, y, 1)[0]
        
        if slope > 0.1 * np.std(y):
            return "increasing"
        elif slope < -0.1 * np.std(y):
            return "decreasing"
        return "stable"
    
    def _calculate_confidence(self, current: float, baseline: float, 
                           normal_range: Tuple[Optional[float], Optional[float]], 
                           trend: str) -> float:
        """计算诊断置信度"""
        lower, upper = normal_range
        in_normal_range = True
        
        # 检查是否在正常范围内
        if upper is not None and current > upper:
            in_normal_range = False
        if lower is not None and current < lower:
            in_normal_range = False
        
        # 基础置信度
        confidence = 0.7 if in_normal_range else 0.9
        
        # 趋势影响
        if trend == "increasing" and current > baseline:
            confidence *= 1.1
        elif trend == "decreasing" and current < baseline:
            confidence *= 1.1
            
        return min(max(confidence, 0.1), 1.0)
    
    def get_system_health_score(self, results: List[RuleEvaluationResult]) -> float:
        """计算系统健康评分 (0-1)"""
        if not results:
            return 1.0
            
        triggered = [r for r in results if r.is_triggered]
        total_weight = sum(r.weight * r.severity for r in triggered)
        max_possible = sum(r.weight * r.severity for r in self.rules)
        
        return 1.0 - (total_weight / max_possible) if max_possible > 0 else 1.0

class EnhancedPistonWearRules(RuleBasedDiagnosticEngine):
    """增强版活塞磨损诊断规则"""
    
    @classmethod
    def required_signals(cls) -> List[str]:
        return [
            'PT3_mean', 'PT3_std', 'PT3_rms', 'PT3_skewness', 'PT3_kurtosis',
            'PT4_mean', 'PT4_std', 'PT4_pulse_factor',
            'PT5_std', 'PT5_crest_factor',
            'FM2_mean', 'FM2_fluctuation',
            'vib_X_rms', 'vib_X_peak2peak', 'vib_X_main_freq','vib_X_spectral_centroid',
            'RTD3_mean', 'RTD3_gradient_mean'
        ]
    
    @classmethod
    def define_rules(cls) -> List[DiagnosticRule]:
        return [
            # 控制口压力规则
            DiagnosticRule(
                "PW-101", "PT3_mean", ">", 0.2, 0.15, 2,
                "控制压力均值升高超过0.2MPa",
                "检查活塞密封环磨损情况"
            ),
            DiagnosticRule(
                "PW-102", "PT3_kurtosis", ">", 0.5, 0.12, 2,
                "压力尖峰特征增强(峰度>0.5)",
                "检查活塞运动平稳性"
            ),
            
            # 排油口压力规则
            DiagnosticRule(
                "PW-201", "PT4_pulse_factor", "<", 0.1, 0.18, 2,
                "排油脉冲因子降低(<0.1)",
                "检查活塞-缸体配合间隙"
            ),
            
            # 振动监测规则
            DiagnosticRule(
                "PW-301", "vib_X_spectral_centroid", ">", 10, 0.40, 3,
                "主振频移超过10Hz",
                "检查活塞杆对中性和轴承磨损"
            ),
            
            # 温度监测规则
            DiagnosticRule(
                "PW-401", "RTD3_gradient_mean", ">", 0.5, 0.10, 1,
                "控制口温度梯度异常(>0.5℃/s)",
                "检查活塞摩擦热积累"
            )
        ]

class ValveWearRules(RuleBasedDiagnosticEngine):
    """控制活门磨损诊断规则"""
    
    @classmethod
    def required_signals(cls) -> List[str]:
        return [
            'PT2_std', 'PT3_mean', 'PT4_peak2peak',
            'FM2_mean', 'vib_Y_peak2peak',
            'vib_X_spectral_centroid'
        ]
    
    @classmethod
    def define_rules(cls) -> List[DiagnosticRule]:
        return [
            DiagnosticRule(
                rule_id="VW-002",
                signal="PT3_mean",
                operator="<",
                threshold=0.3,
                weight=0.15,
                severity=2,
                description="控制口压力降低0.3MPa",
                recommendation="检查阀内泄漏"
            ),
            DiagnosticRule(
                "VW-001", "PT2_std", ">", 0.02, 0.15, 2,
                "供油压力波动增加0.05MPa",
                "检查控制活门磨损"
            ),
            DiagnosticRule(
                rule_id="VW-003",
                signal="PT4_peak2peak",
                operator=">",
                threshold=0.1,
                weight=0.25,
                severity=2,
                description="排油口压力脉动增加0.1MPa",
                recommendation="检查阀运动卡滞"
            ),
            DiagnosticRule(
                rule_id="VW-004",
                signal="FM2_mean",
                operator=">",
                threshold=50,
                weight=0.15,
                severity=1,
                description="回油流量增加50L/h",
                recommendation="检查阀密封性"
            ),
            DiagnosticRule(
                rule_id="VW-005",
                signal="vib_Y_peak2peak",
                operator=">",
                threshold=2.0,
                weight=0.20,
                severity=2,
                description="径向振动增加2.0m/s²",
                recommendation="检查阀组件紧固状态"
            )
        ]
    
class GuideRailWearRules(RuleBasedDiagnosticEngine):
    """滑轨磨损诊断规则集"""
    
    @classmethod
    def required_signals(cls) -> List[str]:
        return [
            'PT2_std',          # 供油压力波动
            'PT3_peak2peak',    # 控制口压力脉动
            'PT4_pulse_factor', # 排油口脉冲特性
            'vib_X_main_freq',  # X向振动主频
            'vib_Y_peak2peak', # Y向振动峰值
            'RTD6_mean',        # 滑油温度
            'FM2_fluctuation',   # 回油流量波动,
            'vib_X_spectral_centroid' # X向频谱重心
        ]
    
    @classmethod
    def define_rules(cls) -> List[DiagnosticRule]:
        '''
        DiagnosticRule(
            "GR-001",         # rule_id: 规则唯一标识符
            "PT2_std",        # signal: 监测的信号特征
            ">",              # operator: 比较运算符
            0.05,             # threshold: 阈值
            0.20,             # weight: 规则权重
            2,                # severity: 严重等级
            "供油压力波动增加0.05MPa",      # description: 规则描述
            "检查滑轨表面磨损情况"          # recommendation: 处理建议
        )
        '''
        return [
            # 压力相关规则
            DiagnosticRule(
                "GR-001", "PT2_std", ">", 0.01, 0.20, 2,
                "供油压力波动增加0.05MPa",
                "检查滑轨表面磨损情况"
            ),
            DiagnosticRule(
                "GR-002", "PT3_peak2peak", ">", 0.5, 0.25, 2,
                "控制口压力脉动增加0.5MPa",
                "检查滑轨-活塞配合间隙"
            ),
            
            # 振动相关规则
            DiagnosticRule(
                "GR-101", "vib_X_main_freq", ">", 0.9, 0.30, 3,
                "X向主振频移超过10Hz",
                "紧急检查滑轨结构完整性"
            ),
            DiagnosticRule(
                "GR-102", "vib_Y_peak2peak", ">", 2.0, 0.4, 2,
                "Y向振动峰值增加2.0m/s²",
                "检查滑轨安装螺栓紧固状态"
            ),
            
            # 温度相关规则
            DiagnosticRule(
                "GR-201", "RTD6_mean", ">", 5, 0.10, 1,
                "滑油温度升高5℃",
                "检查滑轨润滑状况"
            ),
            
            # 流量相关规则
            DiagnosticRule(
                "GR-301", "FM2_fluctuation", ">", 30, 0.15, 2,
                "回油流量波动增加30L/h",
                "检查滑轨密封件状态"
            )
        ]

class HydraulicSystemMonitor:
    """完整的液压系统监测"""
    
    def __init__(self):
        self.feature_extractor = HydraulicFeatureExtractor()
        self.diagnostic_engines = {
            'piston_wear': EnhancedPistonWearRules(),
            'guide_rail_wear': GuideRailWearRules(),
            'valve_wear': ValveWearRules()
            
        }
    
    def process_cycle(self, raw_data: dict) -> dict:
        """处理一个数据周期"""
        # 1. 特征提取
        features = self.feature_extractor.extract_all_features(raw_data)
        print("999999999999999999999999999")
        print(features)
        # 2. 执行诊断
        results = {}
        for name, engine in self.diagnostic_engines.items():
            # 执行规则评估
            rule_results = engine.evaluate(features)
            triggered = [r for r in rule_results if r.is_triggered]
            
            # 计算综合指标
            total_score = sum(r.weight for r in triggered)
            max_severity = max([r.severity for r in triggered], default=0)
            
            # 获取趋势分析
            '''
            trends = {
                sig: engine.get_trend_analysis(sig)
                for sig in engine.required_signals()
            }
            '''
            results[name] = {
                'timestamp': datetime.now().isoformat(),
                'triggered_rules': triggered,
                'total_score': total_score,
                'max_severity': max_severity,
                'trend_analysis': {}
            }
        
        return {
            'features': features,
            'diagnostics': results
        }
    
    def monitor(self, data: pd.DataFrame, window_size: int = 1000) -> list:
        """处理完整数据集"""
        results = []
        for i in tqdm(range(0, len(data), window_size)):
            window_data = data.iloc[i:i+window_size]
            raw_data = {col: window_data[col].values for col in window_data.columns}
            result = self.process_cycle(raw_data)
            results.append(result)
        return results

# 使用示例
if __name__ == "__main__":
    # 初始化监控系统
    monitor = HydraulicSystemMonitor()
    
    # 设置数据目录路径
    print(parent_dir)
    data_dir = os.path.join(parent_dir, "test_data", "2025.04.14-b")
    #data_dir = os.path.join(parent_dir, "test_data", "2025.04.17-c")
    #print(f"数据目录检查: {'存在' if os.path.exists(data_dir) else '不存在'} - {data_dir}")
    
    # 数据文件路径
    #data_file = os.path.join(data_dir, "250417140245滑轨磨损_3.tdms")
    data_file = os.path.join(data_dir, "250414151544控制活门磨损0414-1_.tdms")
    #data_file = os.path.join(data_dir, "250414152815控制活门磨损0414-2_.tdms")
    #data_file = os.path.join(data_dir, "250414154044控制活门磨损0414-3_.tdms")
    #data_file = os.path.join(data_dir, "250414154044控制活门磨损0414-3_.tdms")
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
    data_df.index = pd.to_datetime(data_df.index)
    
    # 处理完整数据集
    print(f"\n开始处理数据，总行数: {len(data_df)}")
    
    # 执行监控
    results = monitor.monitor(data_df)
    
    # 收集所有窗口的所有诊断结果
    all_diagnoses = []
    for window_result in results:
        diagnoses = window_result['diagnostics']
        all_diagnoses.extend([(name, diag) for name, diag in diagnoses.items()])

    # 全局按 total_score 降序排序
    sorted_all = sorted(
        all_diagnoses,
        key=lambda x: x[1]['total_score'],
        reverse=True
    )

    # 只输出全局得分最高的诊断结果
    if sorted_all and sorted_all[0][1]['total_score'] > 0:
        name, diag = sorted_all[0]
        print("\n全局最高评分故障诊断结果:")
        print(f"故障类型: {name}")
        print(f"综合评分: {diag['total_score']:.2f}")
        print(f"最高严重等级: {diag['max_severity']}")
    else:
        print("\n未检测到明显的故障类型（所有评分 ≤ 0）")