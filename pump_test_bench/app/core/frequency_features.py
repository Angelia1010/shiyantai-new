# !/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2023/03/13
# @Author  : ycj
# @Theme   : extract features in frequency domain from ndarray
# @Software: Pycharm
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import logging
logging.basicConfig(level=logging.DEBUG)


class FrequencyFeature(object):
    def __init__(self, framed_array):
        if isinstance(framed_array, pd.DataFrame):
            self.data = framed_array.iloc[:, 0]
        else:
            raise TypeError("Expected a pandas DataFrame for framed_array")
        #logging.info(f"frame data shape: {framed_array.shape}")
        #self.time = framed_array.iloc[:, 0]
        self.signal = framed_array.iloc[:, 0]
        #self.sampling_rate = 1/ (self.time[1] - self.time[0])
        self.sampling_rate = 100
        #self.type_list = np.array(["center", "mean", "rms", "var"])
    
    def get_magnitude(self):
        #logging.info(f"frame data shape: {self.data.shape}")
        #进行傅里叶变换
        signal_fft = np.fft.fft(self.signal)
        n = len(self.signal)
        frequencies = np.fft.fftfreq(n, 1/self.sampling_rate)
        # 计算幅度谱
        magnitude = np.abs(signal_fft)
        return magnitude


    def frequency_feature(self):
        #logging.info(f"frame data shape: {self.data.shape}")
        #进行傅里叶变换
        signal_fft = np.fft.fft(self.signal)
        n = len(self.signal)
        frequencies = np.fft.fftfreq(n, 1/self.sampling_rate)
        # 计算幅度谱
        magnitude = np.abs(signal_fft)

        #取正频率部分的数据
        positive_frequencies = frequencies[:n//2]
        positive_magnitude = np.abs(signal_fft)[:n//2]
        # 计算重心频率
        centroid_frequency = sum(positive_frequencies * positive_magnitude) / sum(positive_magnitude)
        # 计算平均频率
        mean_frequency = np.mean(positive_frequencies)
        # 计算均方根频率
        rms_frequency = np.sqrt(np.mean(positive_frequencies**2))
        # 计算频率方差
        frequency_variance = np.var(positive_frequencies)

        features = [centroid_frequency, mean_frequency, rms_frequency, frequency_variance]
        statistical_measures = {
            "重心频率": centroid_frequency,
            "平均频率": mean_frequency,
            "均方根频率": rms_frequency,
            "频率方差": frequency_variance,
        }

        #logging.info(f"features: {features}")

        return statistical_measures,features

    def frequency_plot(self, feature_type):
        array_ori = self.data.reshape(-1)  # 原始数据
        features = self.frequency_feature()  # 全部特征
        sample_index = np.arange(start=1, stop=self.samples + 1)  # 样本数量
        # 选定的特征转换为索引
        index_list = np.array([np.where(self.type_list == i) for i in feature_type]) \
            .reshape(len(feature_type))
        num = index_list.shape[0]
        # print(index_list)
        # 原始图像
        fig = plt.figure(figsize=(30, 30), dpi=200)
        plt.subplot(num + 1, 1, 1)
        plt.plot(array_ori)
        # 选定的特征图像
        for i in range(num):
            plt.subplot(num + 1, 1, i + 2)
            # plt.plot(sample_index, features[index_list[i]])
            plt.plot(features[index_list[i]])
            plt.xlabel("样本数")
            plt.ylabel(self.type_list[index_list[i]])
        fig.tight_layout()
        plt.show()
        # plt.savefig("test_freq.jpg")
