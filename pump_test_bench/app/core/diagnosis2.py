# -*- coding: utf-8 -*-
import sys
import os
import logging
import json
import pandas as pd
import numpy as np
from datetime import datetime
import asyncio
import aiohttp
from pathlib import Path
import uuid
from scipy import signal
# 将项目根目录添加到 sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
print("项目根目录（上一级目录）:", parent_dir)
# 将该路径添加到 sys.path
sys.path.append(parent_dir)

#from app.utils.pump_util import get_failure_map
from app.core.diagonis_data_process import FaultDataProcessor
from app.core.analysis.rule.hydraulic_system_monitor import HydraulicSystemMonitor
from app.core.time_domain_feature import TimeFeature
from app.core.frequency_features import FrequencyFeature
from app.core.analysis.llm.llm_service import LLMService
from app.core.analysis.model.forest_predict import FaultDiagnosisPredictor
CONF_FILE = os.path.join(parent_dir,"app", "config", "hydraulic_config.yaml")
MODEL_FILE = os.path.join(parent_dir,"app", "core","analysis","model","fault_diagnosis_model.joblib")

def generate_data_prompt(colums, time_feature_value, frequency_freature_value):
        """数据存在时的专业分析提示模板"""
        return f"""作为燃油柱塞泵试验台故障的分析专家，各传感器为{colums}考虑各个传感器的口可能的依赖关系，传感器对应提取的传感器信号数据的统计信息：
        
[设备参数统计]
{time_feature_value},{frequency_freature_value}

给出：
1. 可能存在的故障模式，给出诊断的依据和原因
2. 给出维护建议

要求：
- 包含量化指标
- 中英文专业术语对照"""


class Diagnosis:
    def __init__(self, file_name,conf_file):
        #模型初始化

        self.file_name = file_name
        self.conf_file = CONF_FILE
         # 配置文件路径
        #config_path = os.path.join(parent_dir, "config", "hydraulic_config.yaml")
        # 初始化监控器
        self.monitor = HydraulicSystemMonitor()
        self.llm = LLMService()
        self.predictor = FaultDiagnosisPredictor(MODEL_FILE)

    def load_model(self):
        #加载数据及规则
        #self.rule = load(self.ruleConfPath)
        pass

    # 诊断处理函数 #
    def diagnosis_process(self):
        """
        params:taskid 对应任务id，任务id从目录下取数据
        """
        diagnosis_result = {}
        # 使用FaultDataProcessor读取数据
        try:
            result = self.predictor.predict_tdms_file(self.file_name)
            
            # 3. 生成报告
            diagnosis_result = self.predictor.generate_analysis_result(result)  
        except Exception as e:
            print(f"预测过程中出错: {str(e)}")
        
        if diagnosis_result:  # 确保results不为空
            #print(diagnosis_result)
            main_fault = diagnosis_result['basic_info']['main_fault_type']
            indicator_list = []
            template_report= {}
            # 一、异常性能指标摘要
            # 从信号分析中提取异常指标
            for signal, stats in diagnosis_result['signal_analysis'].items():
                #print(diagnosis_result['signal_analysis'])
                if stats['is_abnormal'] == False:
                    # 构造指标条目
                    indicator = {
                        "name": signal,
                        "reference": f"{stats['mean']:.2f}±{stats['std']:.2f}",
                        "value": f"当前:{stats['mean']:.2f}(范围:{stats['min']:.2f}-{stats['max']:.2f})"
                    }
                    indicator_list.append(indicator)
            
            # 从特征重要性中补充重要指标
            if diagnosis_result['feature_importance']:
                for feature in diagnosis_result['feature_importance'][:3]:  # 取前3个重要特征
                    indicator = {
                        "name": f"关键特征[{feature['feature']}]",
                        "reference": "N/A",
                        "value": f"重要性:{feature['importance']:.4f}"
                    }
                    indicator_list.append(indicator)
            template_report["indicator"] = indicator_list
            # 添加异常信号信息
            location_points = []
            abnormal_signals = [sig for sig, stats in diagnosis_result['signal_analysis'].items() 
                            if stats['is_abnormal']==False]
            if abnormal_signals:
                location_points.append("检测到异常信号指标: " + ", ".join(abnormal_signals))
            else:
                location_points.append("未检测到明显异常信号指标")
            print(location_points)
            analysis_points = []
            # 添加特征重要性信息
            if diagnosis_result['feature_importance']:
                top_feature = diagnosis_result['feature_importance'][0]['feature']
                analysis_points.append(f"关键影响因素是特征'{top_feature}'")
            
            # 添加统计置信度
            main_percentage = next(stat['percentage'] for stat in diagnosis_result['prediction_stats'] 
                                if stat['fault_type'] == main_fault)
            analysis_points.append(f"诊断置信度: {main_percentage:.1%}")
            
            diagnosis = {
                "location": '\n'.join(f"{i+1}. {item}" for i, item in enumerate(location_points)),
                "analysis": '\n'.join(f"{i+1}. {item}" for i, item in enumerate(analysis_points)),
                "fault_name": main_fault
            }
            # 构建最终结果 falt_res
            falt_res = {
                "repair_advice":("待补充每一类故障的排障意见"),
                "indicators": indicator_list,
                "diagnosis": diagnosis
            }
                    
        return falt_res
        #print(time_feature_value)
        #print(frequerce_feature_value)
        '''
        base_prompt = generate_data_prompt(columns,time_feature_value,frequerce_feature_value)
        # 调用大模型服务
        print(base_prompt)
        response = await self.llm.generate(base_prompt)
        #return {"result": response.get('response')}
        raw_result = response.get('response', '')
        print(raw_result)
            
        #all_alarms = self.monitor.process_full_dataset(data_df)
        #print(all_alarms)
        #return all_alarms
        '''
        

if __name__ == "__main__":
    # 设置监控的目录路径
    #data_dir = os.path.join(parent_dir, "app","test_data", "2025.04.14-b")
    #data_dir = os.path.join(parent_dir, "app","test_data", "2025.04.17-c")
    data_dir = os.path.join(parent_dir,"app", "test_data", "20241224-a")
    print(f"数据目录检查: {'存在' if os.path.exists(data_dir) else '不存在'} - {data_dir}")
    
    # 数据文件路径
    #data_file = os.path.join(data_dir, "250414151544控制活门磨损0414-1_.tdms")
    #data_file = os.path.join(data_dir, "250414152815控制活门磨损0414-2_.tdms")
    #data_file = os.path.join(data_dir, "250414154044控制活门磨损0414-3_.tdms")
    #data_file = os.path.join(data_dir, "250414154044控制活门磨损0414-3_.tdms")

    #data_file = os.path.join(data_dir, "250417134030滑轨磨损 _1.tdms")
    #data_file = os.path.join(data_dir, "250417135300 滑轨磨损_2.tdms")
    data_file = os.path.join(data_dir, "2412241412502020001（24A试验载荷谱-随动活塞磨损试验-调载荷谱2）_.tdms")
    def main():
        dia = Diagnosis(data_file, CONF_FILE)
        return dia.diagnosis_process()

    all_alarms = main()
    #print(all_alarms)

    #dia = Diagnosis(file_name,CONF_FILE)
    #all_alarms = dia.diagnosis_process()
    '''
    # 输出结果
    if all_alarms:
        print("\n故障诊断结果汇总:")
        print(f"共检测到 {len(all_alarms)} 条报警")
        
        # 按故障类型统计
        fault_stats = {}
        for alarm in all_alarms:
            fault_name = alarm['fault']
            fault_stats[fault_name] = fault_stats.get(fault_name, 0) + 1
        
        print("\n故障类型统计:")
        for fault, count in fault_stats.items():
            print(f"- {fault}: {count}次")
        
        # 输出前10条报警详情
        print("\n详细报警信息（前10条）:")
        for alarm in all_alarms[:10]:
            print(f"\n[故障] {alarm['fault']} (等级: {alarm['level']})")
            print(f"评分: {alarm['score']:.2f} 时间: {alarm['timestamp']}")
            print(f"建议操作: {alarm['action']}")
            print("触发规则:")
            for rule in alarm['triggered_rules']:
                print(f"  - {rule['rule_description']}")
                print(f"    条件: {rule['condition']} (实际值: {rule['actual_value']:.2f})")
    else:
        print("\n未检测到任何故障")
    '''
