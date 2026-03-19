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

class PlungerWearDetector(FaultDetector):
    """随动活塞磨损故障检测"""
    def __init__(self, feature_calculator):
        super().__init__(feature_calculator)
        self.name = "随动活塞磨损"
        self.description = "柱塞泵随动活塞磨损故障"
        self.severity_levels = [
            {'level': 1, 'threshold': 0.1, 'action': "检查随动活塞密封性"},
            {'level': 2, 'threshold': 0.5, 'action': "立即停机更换活塞"},
            {'level': 3, 'threshold': 0.75, 'action': "紧急停机并检查液压系统"}
        ]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") 
        self.feature_log_file = f"./log/plunger_wear_detector_{timestamp}.csv"
        self._feature_log_header_written = False

        # 新增特征缓存
        window_size = 10
        self.feature_cache = {
            'plunger_pressure_diff': deque(maxlen=window_size),
            'plunger_pressure_fluctuation': deque(maxlen=window_size),
            'control_flow_ratio': deque(maxlen=window_size),
            'plunger_temp_gradient': deque(maxlen=window_size),
            'timestamps': deque(maxlen=window_size)
        }
        self.window_size = window_size

    def _log_features(self, features):
        """
        记录特征到文件（使用之前定义的独立函数）
        
        参数:
            features (dict): 特征字典
        """
        if self.feature_log_file:
            # 使用之前定义的独立函数
            log_features_to_csv(
                features=features,
                filepath=self.feature_log_file,
                feature_names=['plunger_pressure_diff', 'plunger_pressure_fluctuation', 
                             'control_flow_ratio', 'plunger_temp_gradient'],
                mode='a' if self._feature_log_header_written else 'w'
            )
            self._feature_log_header_written = True
    
    def _check_condition(self, rule_name, value):

        """实现具体的条件检查逻辑（不再使用eval）"""
        if rule_name == "plunger_pressure_diff":
            return value > 3
        elif rule_name == "plunger_pressure_fluctuation":
            return value > 0.01
        elif rule_name == "control_flow_ratio":
            #计算流量比返回数组异常点数组
            abnormal_points = np.abs(value - 30) > 0.05  # 找出所有异常点（布尔数组）
            num_abnormal = np.sum(abnormal_points)  # 计算异常点数量
            threshold = 10 #异常点数量大于10为异常
            return num_abnormal > threshold
        elif rule_name == "plunger_temp_gradient":
            return value < 2500
        else:
            raise ValueError(f"未知的规则名称: {rule_name}")
        
    def detect(self, data_dict):
        features = {
            'plunger_pressure_diff': self.feature_calculator.plunger_pressure_diff(data_dict),
            'plunger_pressure_fluctuation': self.feature_calculator.plunger_pressure_fluctuation(data_dict),
            'control_flow_ratio': self.feature_calculator.control_flow_ratio(data_dict),
            'plunger_temp_gradient': self.feature_calculator.plunger_temp_gradient(data_dict)
        }

        # 记录特征到缓存
        timestamp = datetime.now()
        self.feature_cache['plunger_pressure_diff'].append(features['plunger_pressure_diff'])
        self.feature_cache['plunger_pressure_fluctuation'].append(features['plunger_pressure_fluctuation'])
        self.feature_cache['control_flow_ratio'].append(features['control_flow_ratio'])
        self.feature_cache['plunger_temp_gradient'].append(features['plunger_temp_gradient'])
        self.feature_cache['timestamps'].append(timestamp)
        
        #记录特征到文件
        self._log_features(features)

        score = 0
        alerts = []
        triggered_rules = []  # 新增：记录触发的规则
        rules = [
            {'name': 'plunger_pressure_diff', 'weight': 0.1, 'alert': "活塞压差异常"},
            {'name': 'plunger_pressure_fluctuation', 'weight': 0.1, 'alert': "活塞压力波动过大"},
            {'name': 'control_flow_ratio', 'weight': 0.1, 'alert': "控制流量比偏离正常值"},
            {'name': 'plunger_temp_gradient', 'weight': 0.1, 'alert': "活塞温度梯度异常"}
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