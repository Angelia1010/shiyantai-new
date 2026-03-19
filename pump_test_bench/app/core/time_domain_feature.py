# !/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2023/03/12
# @Author  : CZQ
# @Theme   : extract features in time domain from ndarray
# @Software: Pycharm
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
import logging
logging.basicConfig(level=logging.DEBUG)


class TimeFeature(object):
    def __init__(self, framed_array):
        #self.time = framed_array.iloc[:, 0]
        self.signal = framed_array.iloc[:, 0]
        self.type_list = np.array(["max", "abs_max", "min",
                                   "mean", "pp_value", "abs_mean",
                                   "rms", "sra", "var",
                                   "std", "kurtosis", "skew",
                                   "clearance", "shape", "impulse",
                                   "crest"])

    def time_feature(self):
        signal = self.signal
        #time = self.time
        # 最大值
        max_value = signal.max()
        # 最大绝对值
        max_abs_value = signal.abs().max()
        # 最小值
        min_value = signal.min()
        # 均值
        mean_value = signal.mean()
        # 峰值
        peak_value = max_value - min_value
        # 绝对平均值
        mean_abs_value = signal.abs().mean()
        # 均方根值 (RMS)
        rms_value = np.sqrt(np.mean(signal**2))
        # 方根幅值
        root_mean_square_of_abs = np.sqrt(np.mean(signal.abs()**2))
        # 方差
        variance_value = signal.var()
        # 标准差
        std_dev_value = signal.std()
        # 峭度
        kurtosis_value = signal.kurtosis()
        # 偏度
        skewness_value = signal.skew()
        # 裕度指标
        crest_factor = peak_value / rms_value
        # 波形指标
        shape_factor = rms_value / mean_abs_value
        # 脉冲指标
        impulse_factor = peak_value / mean_abs_value
        # 峰值指标
        peak_factor = peak_value / rms_value
        # 将结果汇总为一个字典
        statistical_measures = {
            "最大值": max_value,
            "最大绝对值": max_abs_value,
            "最小值": min_value,
            "均值": mean_value,
            "峰值": peak_value,
            "绝对平均值": mean_abs_value,
            "均方根值 (RMS)": rms_value,
            "方根幅值": root_mean_square_of_abs,
            "方差": variance_value,
            "标准差": std_dev_value,
            "峭度": kurtosis_value,
            "偏度": skewness_value,
            "裕度指标": crest_factor,
            "波形指标": shape_factor,
            "脉冲指标": impulse_factor,
            "峰值指标": peak_factor
        }
        features = [max_value,max_abs_value,min_value,mean_value,peak_value,mean_abs_value,rms_value,root_mean_square_of_abs,variance_value,std_dev_value,kurtosis_value,skewness_value,crest_factor,shape_factor,impulse_factor,peak_factor]
        return statistical_measures,features

