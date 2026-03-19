# -*- coding: utf-8 -*-
import sys
import os

# 将项目根目录添加到 sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
print("项目根目录（上一级目录）:", parent_dir)
sys.path.append(parent_dir)

CONF_FILE = os.path.join(parent_dir, "app", "config", "hydraulic_config.yaml")

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
    def __init__(self, file_name, conf_file):
        """模型初始化"""
        self.file_name = file_name
        self.conf_file = CONF_FILE

    def load_model(self):
        """加载数据及规则"""
        pass

    # 诊断处理函数 #
    def diagnosis_process(self):
        """
        params:taskid 对应任务id，任务id从目录下取数据
        """
        diagnosis_result = {}
        alarms = []
        
        # 试验台设备信息
        test_bench_info = {
            'name': '燃油柱塞泵综合试验台',
            'model': 'FPT-3000',
            'serial': 'TB-2022-0425',
            'last_calibration': '2023-11-15',
            'operator': '王五',
            'location': '测试车间2区'
        }

        # 试验台故障表现
        fault_manifestations = [
            '压力加载不稳定，波动幅度超过±0.5MPa',
            '流量计显示数值跳变异常',
            '温度控制系统响应迟缓',
            '数据采集系统偶发中断'
        ]

        # 试验台监测参数异常值
        abnormal_parameters = [
            {'name': '液压系统压力', 'reference': '10±0.3 MPa', 'Value': '8.5-11.2 MPa波动'},
            {'name': '油温控制精度', 'reference': '±2°C', 'Value': '±5°C'},
            {'name': '数据采样率', 'reference': '1000Hz', 'Value': '不稳定，600-1200Hz波动'},
            {'name': '电源电压', 'reference': '380V±5%', 'Value': '365V-395V波动'}
        ]

        # 故障诊断
        diagnosis = {
            'location': " 液压系统蓄能器失效,温度传感器漂移",
            'analysis': '液压系统蓄能器膜片破裂导致压力波动，进而影响整个系统稳定性'
        }

        # 维修建议
        repair_advice = "1. 更换液压系统蓄能器 2. 校准温度传感器 3. 检查并重新安装数据采集卡"
        falt_res = {
            "repair_advice":repair_advice,
            "indicators": abnormal_parameters,
            "diagnosis": diagnosis
        }
        return falt_res
