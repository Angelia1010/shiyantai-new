# -*- coding: utf-8 -*-
from scipy import signal
import pywt
import yaml
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import pywt
import os
import sys
from tqdm import tqdm
from collections import deque

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.append(parent_dir)
from abc import ABC, abstractmethod
from core.diagonis_data_process import FaultDataProcessor
from core.analysis.rule.rule_feature import FaultDetector
from core.analysis.rule.log_feature import log_features_to_csv

class ControlValveWearDetector(FaultDetector):
    """控制活门磨损故障检测（带特征缓存和趋势分析）"""
    def __init__(self, feature_calculator, window_size=15):
        super().__init__(feature_calculator)
        self.name = "控制活门磨损"
        self.description = "液压控制活门磨损故障"
        self.severity_levels = [
            {'level': 1, 'threshold': 0.1, 'action': "检查活门密封面"},
            {'level': 2, 'threshold': 0.5, 'action': "校准活门行程"},
            {'level': 3, 'threshold': 0.75, 'action': "更换控制活门"}
        ]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") 
        self.feature_log_file = f"./log/control_valve_wear_detector_{timestamp}.csv"
        self._feature_log_header_written = False
        
        # 特征缓存
        self.feature_cache = {
            'valve_pressure_ratio': deque(maxlen=window_size),
            'valve_leakage_rate': deque(maxlen=window_size),
            'valve_temp_gradient': deque(maxlen=window_size),
            'control_flow_ratio':deque(maxlen=window_size),
            'valve_pressure_delay':deque(maxlen=window_size),
            'valve_step_response_delay':deque(maxlen=window_size),
            'timestamps': deque(maxlen=window_size)
        }
        self.window_size = window_size
        self.leakage_baseline = None
        self.leakage_std = None

    def _log_features(self, features):
        """
        记录特征到文件
        """
        if self.feature_log_file:
            log_features_to_csv(
                features=features,
                filepath=self.feature_log_file,
                feature_names=['valve_pressure_ratio', 'valve_leakage_rate', 'valve_temp_gradient','control_flow_ratio','valve_pressure_delay','valve_step_response_delay'],
                mode='a' if self._feature_log_header_written else 'w'
            )
            self._feature_log_header_written = True

    def _check_condition(self, rule_name, value):
        """实现具体的条件检查逻辑"""
        if rule_name == "valve_pressure_ratio":
            return value < 3
        elif rule_name == "valve_leakage_rate":
            #基于历史均值和标准差判定
            #historical_leakage_rates = 1000 #要统计
            #baseline = np.mean(historical_leakage_rates)  # 历史均值
            #dynamic_threshold = baseline + 3 * np.std(historical_leakage_rates)  # 3σ原则
            #q90 = np.quantile(np.abs(value), 0.9)  # 90%分位数
            #return abs(q90 - baseline) > dynamic_threshold
            return value > 40000
        elif rule_name == "valve_temp_gradient":
            return value > 120
        elif rule_name == "valve_wear_features":
            res,score = self._analyze_valve_wear_feature(value)
            if score > 0:
                return True
        elif rule_name == "control_flow_ratio":
            value > 1
        elif rule_name == "valve_pressure_delay":
            value > 10
        elif rule_name == "valve_step_response_delay":
            value > 1.5
        else:
            raise ValueError(f"未知的规则名称: {rule_name}")
    
    def detect(self, data_dict):
        # 计算当前特征
        features = {
            'valve_pressure_ratio': self.feature_calculator.valve_pressure_ratio(data_dict),
            'valve_leakage_rate': self.feature_calculator.valve_leakage_rate(data_dict),
            'valve_temp_gradient': self.feature_calculator.valve_temp_gradient(data_dict),
            'control_flow_ratio':self.feature_calculator.control_flow_ratio(data_dict),
            'valve_pressure_delay':self.feature_calculator.valve_pressure_delay(data_dict),
            'valve_step_response_delay':self.feature_calculator.valve_step_response_delay(data_dict)
        }
        
        # 记录特征到缓存
        timestamp = datetime.now()
        self.feature_cache['valve_pressure_ratio'].append(features['valve_pressure_ratio'])
        self.feature_cache['valve_leakage_rate'].append(features['valve_leakage_rate'])
        self.feature_cache['valve_temp_gradient'].append(features['valve_temp_gradient'])
        self.feature_cache['control_flow_ratio'].append(features['valve_temp_gradient'])
        self.feature_cache['valve_pressure_delay'].append(features['valve_pressure_delay'])
        self.feature_cache['valve_step_response_delay'].append(features['valve_step_response_delay'])
        self.feature_cache['timestamps'].append(timestamp)
        
        # 记录特征到文件
        self._log_features(features)
        
        # 初始评分
        score = 0
        alerts = []
        triggered_rules = []  # 新增：记录触发的规则
        rules = [
            {'name': 'valve_pressure_ratio', 'weight': 0.1, 'alert': "压力比异常"},
            {'name': 'valve_leakage_rate', 'weight': 0.1, 'alert': "泄漏率超标"},
            {'name': 'valve_temp_gradient', 'weight': 0.1, 'alert': "温度梯度超限"},
            {'name':'control_flow_ratio','weight':0.1,'alert':"FM1/FM2比值异常"},
            {'name':'valve_pressure_delay','weight':0.1,'alert':"PT3响应延迟超过转速自适应阈值​​"},
            {'name':'valve_step_response_delay','weight':0.1,'alert':"PT3（控制口压力）响应时间变长​​"}
        ]
        
        # 1. 检查当前特征
        for rule in rules:
            if self._check_condition(rule['name'], features[rule['name']]):
                score += rule['weight']
                alerts.append(rule['alert'])
                info = {}
                info["name"] = rule['name']
                info["value"] = features[rule['name']]
                triggered_rules.append(info)  # 记录触发的规则名称
    
        # 确定严重等级
        severity = next((level for level in sorted(self.severity_levels, 
                        key=lambda x: x['level'], reverse=True) 
                        if score >= level['threshold']), 
                       {'level': 0, 'action': "无异常"})
        
        return {
            'fault_name': self.name,
            'score': score,
            'severity': severity['level'],
            'action': severity['action'],
            'alerts': alerts,
            'features': features,
            'trend_analysis': len(self.feature_cache['timestamps']) >= self.window_size // 2,
            'leakage_baseline': self.leakage_baseline,
            'leakage_std': self.leakage_std,
            'triggered_rules': triggered_rules  # 新增：返回触发的规则名称列表
        }