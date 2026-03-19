from datetime import datetime
import csv
import string
import random
import time
import json
import sys
import os
import pandas as pd
import scipy.io as sio
import logging
logging.basicConfig(level=logging.INFO)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#print("{0:50} {1}".format(__file__.split("/")[-1], BASE_DIR))
sys.path.append(BASE_DIR)
from preprocess.data_process import DataProcess

######################
#### 故障failure map #####
######################
def get_failure_map(file_conf):
    failure_map = {}
    # 打开文件以进行读取
    with open(file_conf, 'r') as file:
        # 遍历文件的每一行
        for line in file:
            # 使用制表符 '\t' 分割每一行的内容
            parts = line.split('\t')
            if len(parts) != 2:
                continue
            failure_map[parts[0]] = parts[1]
    return failure_map

######################
#### PQ K值 #####
######################
def get_pq_k_value(data_group, frequency_feature_map, time_feature_map):
    full_flow_label = 'PsQ100N42'
    zero_flow_label = 'PrQ0N42'
    #logging.info(f"data group:{len(data_group)}")
    if len(data_group)== 0:
        return 0
    #full_flow_data = data_group.get(full_flow_label)
    full_flow_data = data_group[full_flow_label]
    #logging.info(f"full flow data:{full_flow_data.shape}")
    zero_flow_data = data_group[zero_flow_label]
    #logging.info(f"zero flow data:{zero_flow_data.shape}")
    full_p = 0
    full_q = 0
    zero_p = 0
    zero_q = 0
    if not full_flow_data.empty:
        full_p_q = full_flow_data.iloc[-1]
        #logging.info(f"full flow p q:{full_p_q}")
        full_p = full_p_q.iloc[1]
        "目前数据有问题，暂时先写死按198L/min"
        full_q = full_p_q.iloc[4]
        #full_q = 198
        logging.info(f"full flow p q:{full_p}, {full_q}")
    if not zero_flow_data.empty:
        zero_p_q = zero_flow_data.iloc[0]
        #logging.info(f"full flow p q:{zero_p_q}")
        zero_p = zero_p_q.iloc[1]
        zero_q = zero_p_q.iloc[4]        
        logging.info(f"zero flow p q:{zero_p}, {zero_q}")
    k = (zero_q - full_q) / (zero_p - full_p)
    logging.info(f"PQ K value:{k}")
    return k

if __name__ == "__main__":
    data = DataProcess()
    path = sys.argv[1]
    data_group = data.read_csv_data(path)
    frequency_feature_map = {}
    time_feature_map = {}
    get_pq_k_value(data_group, frequency_feature_map, time_feature_map)
