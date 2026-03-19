# -*- coding: utf-8 -*-
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

class RailWearDetector(FaultDetector):
    """滑轨磨损故障检测（带特征缓存和趋势分析）"""
    def __init__(self, feature_calculator, window_size=10):
        super().__init__(feature_calculator)
        self.name = "滑轨磨损"
        self.description = "柱塞泵滑轨磨损故障"
        self.severity_levels = [
            {'level': 1, 'threshold': 0.1, 'action': "检查滑轨润滑系统"},
            {'level': 2, 'threshold': 0.5, 'action': "安排滑轨维护"},
            {'level': 3, 'threshold': 0.75, 'action': "紧急停机更换滑轨"}
        ]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") 
        self.feature_log_file = f"./log/rail_wear_detector_{timestamp}.csv"
        self._feature_log_header_written = False
        
        # 特征缓存
        self.feature_cache = {
            'rail_temp_gradient': deque(maxlen=window_size),
            'vibration_energy': deque(maxlen=window_size),
            'timestamps': deque(maxlen=window_size)
        }
        self.window_size = window_size

    def _log_features(self, features):
        """
        记录特征到文件
        """
        if self.feature_log_file:
            log_features_to_csv(
                features=features,
                filepath=self.feature_log_file,
                feature_names=['rail_temp_gradient', 'vibration_energy'],
                mode='a' if self._feature_log_header_written else 'w'
            )
            self._feature_log_header_written = True

    def _check_condition(self, rule_name, value):
        """实现具体的条件检查逻辑"""
        if rule_name == "rail_temp_gradient":
            return value > 0.8
        elif rule_name == "vibration_energy":
            return value > 8000
        else:
            raise ValueError(f"未知的规则名称: {rule_name}")
    
    def detect(self, data_dict):
        # 计算当前特征
        features = {
            'rail_temp_gradient': self.feature_calculator.rail_temp_gradient(data_dict),
            'vibration_energy': self.feature_calculator.vibration_energy(data_dict)
        }
        
        # 记录特征到缓存
        timestamp = datetime.now()
        self.feature_cache['rail_temp_gradient'].append(features['rail_temp_gradient'])
        self.feature_cache['vibration_energy'].append(features['vibration_energy'])
        self.feature_cache['timestamps'].append(timestamp)
        
        # 记录特征到文件
        self._log_features(features)
        
        # 初始评分
        score = 0
        alerts = []
        triggered_rules = []  # 新增：记录触发的规则
        rules = [
            {'name': 'rail_temp_gradient', 'weight': 0.3, 'alert': "滑轨轴向温升异常"},
            {'name': 'vibration_energy', 'weight': 0.1, 'alert': "转矩波动异常"},
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
            'triggered_rules': triggered_rules  # 新增：返回触发的规则名称列表
        }