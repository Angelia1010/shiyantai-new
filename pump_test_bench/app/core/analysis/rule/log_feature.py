# -*- coding: utf-8 -*-
import csv
from datetime import datetime
import sys
import os

def log_features_to_csv(features, filepath, feature_names=None, mode='a'):
    """
    将特征值记录到CSV文件的通用函数
    
    参数:
        features (dict): 包含特征值的字典
        filepath (str): 要写入的CSV文件路径
        feature_names (list): 可选，指定要记录的特征名列表及顺序
        mode (str): 文件写入模式，'a'为追加(默认)，'w'为覆盖
        
    返回:
        bool: 是否成功写入
    """
    try:
        # 确定要记录的特征名及顺序
        if feature_names is None:
            feature_names = sorted(features.keys())
        
        # 检查文件是否存在以决定是否写表头
        write_header = not os.path.exists(filepath) or os.path.getsize(filepath) == 0 or mode == 'w'
        
        with open(filepath, mode, newline='') as f:
            writer = csv.writer(f)
            
            # 添加时间戳
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            row_data = [timestamp]
            
            # 准备数据行
            for name in feature_names:
                row_data.append(features.get(name, None))
            
            # 写入表头(如果需要)
            if write_header:
                header = ['timestamp'] + feature_names
                writer.writerow(header)
            
            # 写入数据行
            writer.writerow(row_data)
        
        return True
    except Exception as e:
        print(f"写入特征数据到CSV失败: {str(e)}")
        return False