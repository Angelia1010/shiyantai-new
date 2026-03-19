# -*- coding: utf-8 -*-
import numpy as np
from scipy import signal
import pywt
from abc import ABC, abstractmethod
class FaultDetector(ABC):
    """故障检测基类"""
    def __init__(self, feature_calculator):
        self.feature_calculator = feature_calculator
    
    @abstractmethod
    def detect(self, data_dict):
        """执行故障检测"""
        pass
    
    def _check_condition(self, rule, value):
        """检查条件表达式"""
        pass
        '''
        try:
            return eval(condition_str, {'value': value, 'abs': abs})
        except:
            raise ValueError(f"无效的条件表达式: {condition_str}")
        '''

class RuleFeature:
    def __init__(self):
        # 列名映射表（中文列名 -> 内部标准列名）
        self.column_mapping = {
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
        
        # 采样率设置（单位：Hz）
        self.sampling_rate = 100
        
        # 基线数据存储（可在运行时更新）
        self.baseline_data = None
        
    def _map_column_names(self, data_dict):
        """将输入数据的中文列名映射为内部标准列名"""
        mapped_data = {}
        for ch_name, value in data_dict.items():
            if ch_name in self.column_mapping:
                std_name = self.column_mapping[ch_name]
                mapped_data[std_name] = value
            else:
                raise ValueError(f"未知的列名: {ch_name}")
        return mapped_data
    
    # ========== 压力相关特征 ==========
    def calculate_pressure_features(self, data_dict):
        """
        计算压力相关特征（PT4下降率、PT6上升率、PT3下降率）
        
        Args:
            current_data (dict): 当前数据，包含PT4, PT6, PT3的实时值（支持标量或数组）
            baseline_data (dict): 基线数据，包含PT4_baseline, PT6_baseline, PT3_baseline
        
        Returns:
            dict: 包含三个压力特征的字典，键为'PT4_drop_rate', 'PT6_rise_rate', 'PT3_drop_rate'
        
        Raises:
            ValueError: 如果输入数据缺失或基线值为0
        """
        # 检查数据完整性
        required_keys = ['PT4', 'PT6', 'PT3']
        if not all(k in data_dict for k in required_keys) or \
        not all(k+'_baseline' in data_dict for k in required_keys):
            raise ValueError("Missing required pressure data keys")
        
        features = {}
        
        # 计算PT4下降率（百分比）
        pt4_baseline = 400 # 这个直接统计的
        if np.any(pt4_baseline <= 0):
            raise ValueError("PT4 baseline must be positive")
        features['PT4_drop_rate'] = np.mean(
            (pt4_baseline - data_dict['PT4']) / pt4_baseline * 100
        )
        
        # 计算PT6上升率（百分比）
        pt6_baseline = 700 # 这个直接统计的
        if np.any(pt6_baseline <= 0):
            raise ValueError("PT6 baseline must be positive")
        features['PT6_rise_rate'] = np.mean(
            (data_dict['PT6'] - pt6_baseline) / pt6_baseline * 100
        )
        
        # 计算PT3下降率（百分比）
        pt3_baseline = 300 #这个直接统计的
        if np.any(pt3_baseline <= 0):
            raise ValueError("PT3 baseline must be positive")
        features['PT3_drop_rate'] = np.mean(
            (pt3_baseline - data_dict['PT3']) / pt3_baseline * 100
        )
        return features
    def pt3_mean(self, data_dict):
        """计算PT3的平均值"""
        data = self._map_column_names(data_dict)
        return float(np.nanmean(data["PT3"]))  # 直接返回PT3均值
    
    def plunger_pressure_diff(self, data_dict):
        """计算随动活塞压差 (PT1 - PT3)"""
        data = self._map_column_names(data_dict)
        diff_series = data["PT3"] - data["PT1"] # 一个时间段的压差序列
        return float(np.nanmean(diff_series))  # 使用nanmean避免空值影响 
    
    def plunger_pressure_fluctuation(self, data_dict, window_size=60):
        """计算随动活塞压力波动 (std(PT3 - PT4))"""
        data = self._map_column_names(data_dict)
        pt3 = self._clean_signal(data["PT3"])
        pt4 = self._clean_signal(data["PT4"])
        #pressure_diff = data["PT3"] - data["PT4"]
        pressure_diff = pt4 - pt3
        window_samples = window_size * self.sampling_rate
        return float(np.std(pressure_diff[-window_samples:]))
    
    def control_flow_ratio(self, data_dict):
        """计算控制流量比 ((FM1 - FM2)/(speed + 1e-6))"""
        data = self._map_column_names(data_dict)
        ratio_series = (data["FM1"] - data["FM2"]) / (data["speed"] + 1e-6)
        return float((np.max(ratio_series) - np.min(ratio_series)) / (np.mean(np.abs(ratio_series)) + 1e-6))
    def valve_pressure_ratio(self, data_dict):
        """计算控制活门压力比 (PT4/(PT3 + 1e-6))"""
        data = self._map_column_names(data_dict)
        data = self._map_column_names(data_dict)
        pt2 = np.asarray(data["PT2"], dtype=np.float64).ravel()  # 确保一维数组
        pt3 = np.asarray(data["PT3"], dtype=np.float64).ravel()
        # 2. 基础验证
        if len(pt2) == 0 or len(pt3) == 0:
            print("空数组输入!")
            return 0.0
        with np.errstate(divide='ignore', invalid='ignore'):
            ratio = np.divide(pt3, pt2, where=(pt2 > 1e-6))  # 仅当pt2>0.000001时计算
            valid_ratios = ratio[~np.isnan(ratio)]
            
        if len(valid_ratios) == 0:
            print("无有效比值!")
            return 0.0
            
        mean_ratio = np.mean(valid_ratios)
        print(f"计算完成: 均值={mean_ratio:.4f} (范围:{np.min(valid_ratios):.4f}-{np.max(valid_ratios):.4f})")
        return float(mean_ratio)

    def valve_pressure_fluctuation(self, data_dict, window_size=100):
        """计算控制压力波动系数 (std(PT3)/mean(PT3))"""
        data = self._map_column_names(data_dict)
        window_samples = window_size * self.sampling_rate
        window_data = data["PT3"][-window_samples:]
        return np.std(window_data) / np.mean(window_data)
    
    def valve_pressure_delay(self, data_dict, window_size=100, sample_rate=100) -> float:
        """
        通过互相关计算PT2到PT3的延迟时间（秒）
        改进点：
        1. 增加数据有效性检查
        2. 处理常数值和NaN
        3. 优化互相关计算
        """
        try:
            # 数据提取和验证
            data = self._map_column_names(data_dict)
            pt2 = np.asarray(data["PT2"], dtype=np.float64).ravel()  # 确保一维数组
            pt3 = np.asarray(data["PT3"], dtype=np.float64).ravel()
            
            # 数据有效性检查
            #if len(pt2) < 10 or len(pt3) < 10 or np.all(pt2 == pt2[0]) or np.all(pt3 == pt3[0]):
            #    return 0.0

            # 数据清洗和预处理
            pt2 = self._clean_signal(pt2)
            pt3 = self._clean_signal(pt3)
            
            # 带通滤波 (0.1Hz-5Hz)
            b, a = signal.butter(2, [0.1, 5], 'bandpass', fs=sample_rate)
            pt2_filt = signal.filtfilt(b, a, pt2)
            pt3_filt = signal.filtfilt(b, a, pt3)
            
            # 改进的归一化
            pt2_norm = self._safe_normalize(pt2_filt)
            pt3_norm = self._safe_normalize(pt3_filt)
            
            # 互相关计算
            corr = signal.correlate(pt2_norm, pt3_norm, mode='full')
            lags = signal.correlation_lags(len(pt2_norm), len(pt3_norm), mode='full')
            pos_lags = lags[lags >= 0]
            pos_corr = corr[lags >= 0]
            
            if len(pos_lags) == 0:
                return 0.0
                
            # 找最大相关点（排除零延迟）
            max_idx = np.argmax(pos_corr[1:] if len(pos_corr) > 1 else pos_corr) + 1
            delay = pos_lags[max_idx] / sample_rate
            
            return float(delay)
            
        except Exception as e:
            print(f"[Delay Calc Error] {str(e)}")
            return 0.0

    def _clean_signal(self, signal: np.ndarray) -> np.ndarray:
        """信号清洗函数"""
        # 替换NaN
        signal = np.nan_to_num(signal, nan=np.nanmean(signal))
        
        # 添加微小噪声防止除零
        if np.std(signal) < 1e-6:
            signal = signal + np.random.normal(0, 1e-6, len(signal))
        
        return signal

    def _safe_normalize(self, signal: np.ndarray) -> np.ndarray:
        """安全归一化"""
        mean = np.mean(signal)
        std = np.std(signal)
        denominator = std if std > 1e-4 else 1.0
        return (signal - mean) / (denominator + 1e-12)

    def valve_step_response_delay(self, data_dict, window_size=100, sample_rate=100) -> float:
        """
        通过阶跃响应法计算延迟
        改进点：
        1. 更鲁棒的阶跃检测
        2. 动态阈值调整
        3. 多条件验证
        """
        try:
            # 数据准备
            data = self._map_column_names(data_dict)
            pt2 = np.asarray(data["PT2"], dtype=np.float64).ravel()  # 确保一维数组
            pt3 = np.asarray(data["PT3"], dtype=np.float64).ravel()
            
            # 基础检查
            if len(pt2) < 20 or len(pt3) < 20:
                return 0.0
                
            # 信号预处理
            pt2 = self._clean_signal(pt2)
            pt3 = self._clean_signal(pt3)
            
            # 低通滤波
            b, a = signal.butter(4, 10/(sample_rate/2), 'lowpass')
            pt2_filt = signal.filtfilt(b, a, pt2)
            pt3_filt = signal.filtfilt(b, a, pt3)
            
            # 动态阶跃检测
            pt2_diff = np.diff(pt2_filt)
            dynamic_threshold = 0.2 * np.percentile(np.abs(pt2_diff), 95)  # 基于95分位数
            
            # 多条件阶跃检测
            rising_edges = np.where(
                (pt2_diff > dynamic_threshold) &
                (pt2_filt[1:] > np.percentile(pt2_filt, 75)) &  # 高于75分位数
                (np.abs(pt2_diff) > 0.5 * np.max(pt2_diff))  # 显著变化
            )[0]
            
            if len(rising_edges) == 0:
                return 0.0
                
            rise_start = rising_edges[0]
            
            # 响应检测（动态稳态估计）
            pre_steady = np.median(pt3_filt[:rise_start])
            response_level = pre_steady + 0.1 * (np.max(pt3_filt) - pre_steady)  # 超过稳态10%
            
            response_idx = np.where(pt3_filt[rise_start:] > response_level)[0]
            if len(response_idx) == 0:
                return 0.0
                
            delay = response_idx[0] / sample_rate
            return float(max(delay, 0.0))
            
        except Exception as e:
            print(f"[Step Response Error] {str(e)}")
            return 0.0

    # ========== 流量相关特征 ==========
    def valve_leakage_rate(self, data_dict):
        """计算活门泄漏率系数 ((FM1 - 0.92*FM2)/APT1)"""
        data = self._map_column_names(data_dict)
        value =  (data["FM1"] - 0.92 * data["FM2"]) / data["APT1"]
        #q90 = np.quantile(np.abs(value), 0.9)  # 90%分位数
        return float(np.nanmean(value)) 
        #return (data["FM1"] - 0.92 * data["FM2"]) / data["APT1"]
    
    def leakage_indicator(self, data_dict):
        """
        计算泄漏流量指标 (FM2_current - FM2_baseline)
        :return: 泄漏流量（标量）
        """
        fm1 = data_dict["FM1"]
        fm2 = data_dict["FM2"]
        fm2_baseline = 500 # 这个要给一个base值
        fm1_baseline = 400 #给一个base值 
        return np.mean(fm2 - fm2_baseline) - np.mean(fm1_baseline - fm1)
    
    # ========== 振动相关特征 ==========
    def plunger_vibration(self, data_dict, window_size=10):
        """计算活塞径向振动 (sqrt(mean(Y**2)))"""
        data = self._map_column_names(data_dict)
        window_samples = window_size * self.sampling_rate
        window_data = data["Y"][-window_samples:]
        fft_result = np.fft.fft(window_data, n=2048)
        power_spectrum = np.abs(fft_result)**2
        return np.sqrt(np.mean(power_spectrum))
    
    def vibration_energy(self, data_dict):
        """计算合成振动能量 (sqrt(mean(X**2 + Y**2 + Z**2)))"""
        data = self._map_column_names(data_dict)
        print("hahahhahahhahah")
        print(data["X"].isnull().sum())  # 检查空值
        print(data["X"].dtype)           # 检查数据类型
        x = np.asarray(data["X"], dtype=np.float64).ravel()  # 确保一维数组
        y = np.asarray(data["Y"], dtype=np.float64).ravel()
        z = np.asarray(data["Z"], dtype=np.float64).ravel()   
        #combined = data["X"]**2 + data["Y"]**2 + data["Z"]**2
        combined = x**2 + y**2 + z**2
        fft_result = np.fft.fft(combined, n=2048)
        power_spectrum = np.abs(fft_result)**2
        return np.sqrt(np.mean(power_spectrum))
    
    def rail_vibration_energy(self, data_dict, window_size=15):
        """计算滑轨振动能量 (sqrt(mean(X**2 + Y**2)))"""
        data = self._map_column_names(data_dict)
        window_samples = window_size * self.sampling_rate
        window_data_X = data["X"][-window_samples:]
        window_data_Y = data["Y"][-window_samples:]
        combined = window_data_X**2 + window_data_Y**2
        
        # FFT处理
        fft_result = np.fft.fft(combined, n=2048)
        power_spectrum = np.abs(fft_result)**2
        
        # 小波变换
        coeffs = pywt.wavedec(combined, 'db4', level=5)
        wavelet_energy = np.sum([np.sum(np.abs(c)**2) for c in coeffs])
        
        return np.sqrt(np.mean(power_spectrum) + wavelet_energy)
    
    # ========== 温度相关特征 ==========
    def calculate_temperature_features(self, data_dict):
        """
        计算温度相关特征（温升百分比）
        
        Args:
            current_data (dict): 当前数据（支持中文列名）
        
        Returns:
            dict: 包含温升百分比的特征字典，键为：
                - RTD5_rise_rate: 回油温升百分比
                - RTD3_rise_rate: 控制口温升百分比
        """

        current = self._map_column_names(data_dict)
        features = {}
        
        # 计算回油温升（RTD5）
        if 'RTD5' in current:
            baseline = 800 #暂时给一个baseline
            current_temp = current['RTD5']
            features['RTD5_rise_rate'] = np.mean(
                self._safety_divide(current_temp - baseline, baseline) * 100
            )
        
        # 计算控制口温升（RTD3）
        if 'RTD3' in current:
            baseline = 700 #暂时给一个baseline
            current_temp = current['RTD3']
            features['RTD3_rise_rate'] = np.mean(
                self._safety_divide(current_temp - baseline, baseline) * 100
            )
            
        return features
    
    def plunger_temp_gradient(self, data_dict):
        """计算活塞温度梯度 (RTD3 - RTD4)"""
        data = self._map_column_names(data_dict)
        diff_series =  data["RTD3"] - data["RTD4"]
        return float(np.nanmean(diff_series))  # 使用nanmean避免空值影响 
    
    def rail_temp_gradient(self, data_dict):
        """计算滑轨轴向温升梯度 (RTD8 - RTD9)"""
        data = self._map_column_names(data_dict)
        diff_series = data["RTD8"] - data["RTD9"]
        return float(np.nanmean(diff_series))  # 使用nanmean避免空值影响 
    
    def valve_temp_gradient(self, data_dict):
        """计算活门温度梯度 (RTD3 - RTD4)"""
        data = self._map_column_names(data_dict)
        diff_series = data["RTD3"] - data["RTD4"] # 一个时间段的温度差序列
        return float(np.nanmean(diff_series))  # 使用nanmean避免空值影响
        #return diff_series 
    
    # ========== 机械相关特征 ==========
    def calculate_vibration_features(self, data_dict):
        """
        计算振动相关特征
        
        Args:
            data_dict (dict): 当前数据（支持中文列名）
        
        Returns:
            dict: 包含振动比值的特征字典，键为：
                - vib_high_ratio: 高频振动能量比
                - BPFI_harmonic: BPFI谐波幅值比
        """
        
        current = self._map_column_names(data_dict)
        features = {}
        
        # 高频振动能量比（X/Y/Z三轴综合）
        if all(k in current for k in ['X', 'Y', 'Z']) and \
           all(k in self.baseline_data for k in ['X', 'Y', 'Z']):
            # 计算当前振动RMS（三轴合成）
            current_vib = np.sqrt(np.mean([
                current['X']**2, current['Y']**2, current['Z']**2
            ], axis=0))
            
            # 计算基线振动RMS
            baseline_vib = 100 #先给一个基准的
            features['vib_high_ratio'] = np.mean(
                self._safety_divide(current_vib, baseline_vib)
            )
        
        # BPFI谐波幅值比（需外部提供BPFI_amplitude）
        if 'BPFI_amplitude' in current and 'BPFI_amplitude' in self.baseline_data:
            features['BPFI_harmonic'] = np.mean(
                self._safety_divide(
                    current['BPFI_amplitude'], 
                    self.baseline_data['BPFI_amplitude']
                )
            )
            
        return features
    def torque_ripple(self, data_dict, window_size=30):
        """计算转矩纹波系数 (std(torque)/(mean(torque)+1e-6))"""
        data = self._map_column_names(data_dict)
        window_samples = window_size * self.sampling_rate
        window_data = data["torque"][-window_samples:]
        return np.std(window_data) / (np.mean(window_data) + 1e-6)
    

