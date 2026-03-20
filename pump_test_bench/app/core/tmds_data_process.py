import os
import sys
import numpy as np
import pandas as pd
from nptdms import TdmsFile,TdmsWriter,GroupObject, ChannelObject,RootObject
import json
import time
import psutil


class TDMSProcessor:
    def __init__(self, file_path, fixed_chunk_size=10):
        """初始化 TDMSProcessor 类"""
        self.file_path = file_path
        self.fixed_chunk_size = fixed_chunk_size

    def read_chunk(self, group_name, channel_name, start_row, chunk_size):
        """按固定大小读取通道数据"""
        try:
            with TdmsFile.open(self.file_path) as tdms_file:
                if group_name not in tdms_file:
                    raise ValueError(f"文件中不存在组 '{group_name}'")
                group = tdms_file[group_name]
                if channel_name not in group:
                    raise ValueError(f"组 '{group_name}' 中不存在通道 '{channel_name}'")
                channel = group[channel_name]
                # 返回指定范围的数据块
                return channel[start_row:start_row + chunk_size]
        except Exception as e:
            print(f"读取数据块时发生错误: {e}")
            return np.array([])

    def extract_features(self, data_chunk):
        """从数据块中提取特征值"""
        features = {}
        try:
            if len(data_chunk) == 0:
                print("跳过：数据块为空")
                return features
            df = pd.DataFrame(data_chunk, columns=['Signal'])
            features['mean'] = df['Signal'].mean()
            features['std'] = df['Signal'].std()
            features['min'] = df['Signal'].min()
            features['max'] = df['Signal'].max()
        except Exception as e:
            print(f"提取特征时发生错误: {e}")
        return features

    def generate_spectrum(self, data_chunk):
        """从数据块生成频谱图"""
        if len(data_chunk) == 0:
            print("跳过：数据块为空，无法生成频谱图")
            return None

        sampling_frequency = 100  # 示例采样频率
        data = np.array(data_chunk).flatten()
        if len(data) < 2:
            print("跳过：数据块长度不足，无法生成频谱图")
            return None
        try:
            # 计算频谱
            freqs = np.fft.fftfreq(len(data), d=1/sampling_frequency)
            fft_values = np.fft.fft(data)
            spectrum = np.abs(fft_values[:len(fft_values)//2])
            freqs = freqs[:len(freqs)//2]
            spectrumInfo = {"freqs": freqs.tolist(), "spectrum": spectrum.tolist()}
            return spectrumInfo
        except Exception as e:
            print(f"生成频谱图时发生错误: {e}")
            return None

    def stream_data(self, group_channel_list, page):
        """分页读取指定组和通道的数据"""
        result = {}
        for group_name, channel_name in group_channel_list:
            try:
                print(f"开始处理组 '{group_name}' 的通道 '{channel_name}'...")
                start_row = page * self.fixed_chunk_size  # 计算当前页的起始行
                data_chunk = self.read_chunk(group_name, channel_name, start_row, self.fixed_chunk_size)

                if len(data_chunk) == 0:
                    print(f"跳过：组 '{group_name}' 的通道 '{channel_name}' 数据为空")
                    continue

                # 提取特征
                features = self.extract_features(data_chunk)
                # 生成频谱图
                spectrum = self.generate_spectrum(data_chunk)

                result[f"{group_name}/{channel_name}"] = {
                    'data_chunk': data_chunk.tolist(),
                    'features': features,
                    'spectrum': spectrum
                }

                print(f"完成处理组 '{group_name}' 的通道 '{channel_name}'")
            except Exception as e:
                print(f"处理组 '{group_name}' 的通道 '{channel_name}' 时发生错误: {e}")

        return result

    def get_all_channels_data(self, page=0):
        """一次性读取文件中所有通道的数据"""
        result = {}
        start_time = time.time()  # 开始计时
        try:
            read_time_1 = time.time() # 计时
            initial_memory = psutil.virtual_memory().used  # 获取初始内存使用情况
            with TdmsFile.open(self.file_path) as tdms_file:
                read_time_2 = time.time() # 计时
                groups = tdms_file.groups()

                read_time_3 = time.time() # 计时
                print(f"开始处理组的数量 '{len(groups)}'")
                for group in groups:
                    
                    group_name = group.name  # 获取组名
                    read_time_4 = time.time() # 计时
                    channels = group.channels()
                    read_time_5 = time.time() # 计时
                    print(f"group.channels耗时 {read_time_5 - read_time_4:.3f} 秒")
                    print(f"开始处理组 '{group_name}' 的通道数量 '{len(channels)}'")
                    for channel in channels:
                        
                        channel_name = channel.name  # 获取通道名
                        try:
                            print(f"开始处理组 '{group_name}' 的通道 '{channel_name}'...")
                            read_time_6 = time.time() # 计时
                            channel_start_time = time.time()
                            # 获取数据总量
                            total_data_len = len(channel)
                            start_idx = page * self.fixed_chunk_size
                            end_idx = min((page + 1) * self.fixed_chunk_size, total_data_len)

                            # 如果当前页面数据超出了范围，跳过
                            if start_idx >= total_data_len:
                                print(f"跳过：组 '{group_name}' 的通道 '{channel_name}'，数据已读取完毕")
                                continue
                            
                            data_chunk = channel[start_idx:end_idx]
                            read_time_7 = time.time() # 计时
                            print(f"处理channel耗时 {read_time_7 - read_time_6:.3f} 秒")
                            if len(data_chunk) == 0:
                                print(f"跳过：组 '{group_name}' 的通道 '{channel_name}' 数据为空")
                                continue

                            read_time_8 = time.time() # 计时
                            # 提取特征
                            features = self.extract_features(data_chunk)
                            read_time_9 = time.time() # 计时
                            # 生成频谱图
                            spectrum = self.generate_spectrum(data_chunk)
                            read_time_10 = time.time() # 计时
                            print(f"提取特征耗时 {read_time_9 - read_time_8:.3f} 秒")
                            print(f"生成频谱图耗时 {read_time_10 - read_time_9:.3f} 秒")

                            result[f"{group_name}/{channel_name}"] = {
                                'data_chunk': data_chunk.tolist(),
                                'features': features,
                                'spectrum': spectrum
                                
                            }

                            channel_end_time = time.time()
                            print(f"完成处理组 '{group_name}' 的通道 '{channel_name}'，耗时 {channel_end_time - channel_start_time:.2f} 秒")

                        except Exception as e:
                            print(f"处理组 '{group_name}' 的通道 '{channel_name}' 时发生错误: {e}")
                final_memory = psutil.virtual_memory().used  # 获取最终内存使用情况
                memory_used = final_memory - initial_memory
                print(f"多次打开并多次读取,内存增加: {memory_used / (1024 ** 2):.2f} MB")      
        except Exception as e:
            print(f"读取所有通道数据时发生错误: {e}")

        end_time = time.time()
        print(f"读取所有通道数据完成，总耗时 {end_time - start_time:.2f} 秒")
        print(f"耗时统计 '{group_name}' 的通道 '{channel_name}'，耗时 {read_time_2 - read_time_1:.3f} 秒")
        print(f"处理tdms_file.groups耗时 {read_time_3 - read_time_2:.3f} 秒")

        return result if result else {"message": "已读取完毕或没有数据"}


def handle_request_tmds_data(file_path, group_channel_list=None, page=0, page_size=100):
    """处理请求并返回指定页的数据"""
    processor = TDMSProcessor(file_path, page_size)
    if group_channel_list:
        result = processor.stream_data(group_channel_list, page)
    else:
        result = processor.get_all_channels_data(page)

    if not result or (isinstance(result, dict) and result.get("message")):
        return {"message": "已读取完毕或没有数据"}

    return result


def generate_tdms_file(filename, max_size_gb=2):

    group_channel_map = {
        "供油温度RTD2":["℃"],
        "出油口温度RTD5":["℃"], 
        "排油口温度RTD4":["℃"], 
        "控制口温度RTD3":["℃"], 
        "主油箱压力PT1":["MPa"],
        "低压气压力APT2":["MPa"], 
        "供油压力PT2":["MPa"],
        "出油口压力PT5":["MPa"], 
        "回油流量FM2":["L/h"], 
        "回油质量流量":["Kg/h"],
        "排油质量流量":["Kg/h"]
    }
    max_size_bytes = max_size_gb * 1024 * 1024 * 1024  # 2GB in bytes
    data_length = 100000  # Number of samples per channel per write

    with TdmsWriter(filename) as tdms_writer:
        root_object = RootObject()
        tdms_writer.write_segment([root_object])

        while os.path.getsize(filename) < max_size_bytes:
            for group_name, channel_names in group_channel_map.items():
                group_object = GroupObject(group_name)
                tdms_writer.write_segment([group_object])

                for channel_name in channel_names:
                    # 生成随机数据并写入 channel
                    data = np.random.uniform(0, 100, size=data_length).astype(np.float32)
                    channel_object = ChannelObject(group_name, channel_name, data.tolist())
                    tdms_writer.write_segment([channel_object])

            print(f"Current file size: {os.path.getsize(filename) / (1024 * 1024 * 1024):.2f} GB")

    print(f"File generation complete. Final file size: {os.path.getsize(filename) / (1024 * 1024 * 1024):.2f} GB")

def read_tdms_segment(file_path, start_index, chunk_size=100):
    """
    流式读取TDMS文件的指定数据段
    
    :param file_path: TDMS文件路径
    :param start_index: 起始读取位置（基于每个channel的0-based索引）
    :param chunk_size: 要读取的数据条数（默认100）
    :return: 包含40个group数据的字典，键为group名称，值为numpy数组
    """
    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    sys.path.append(parent_dir)

    # print("项目根目录（上一级目录）:", parent_dir)
    directory_path = os.path.join(parent_dir, "app", "core", "20241224-a")
    data_dict = {}
    
    # 使用内存映射模式打开文件（关键点）
    with TdmsFile.open(file_path, memmap_dir=directory_path) as tdms_file:
        for group_num in range(40):  # 遍历40个group
            group_name = f"group{group_num}"
            try:
                # 获取当前group的MA通道（关键点）
                channel = tdms_file[group_name]["MA"]
                
                # 计算结束索引
                end_index = start_index + chunk_size
                
                # 直接访问数据切片（内存映射特性保证不加载全部数据）
                data_segment = channel[start_index:end_index]
                
                # 将数据存入字典
                data_dict[group_name] = data_segment
                
            except KeyError:
                # 处理不存在的group/channel（根据实际情况调整）
                data_dict[group_name] = None
    
    return data_dict

def read_once_and_multiple_times(filename, group_count=40, data_length=100000):
    start_time = time.time()
    initial_memory = psutil.virtual_memory().used  # 获取初始内存使用情况
    chunk_size=100

    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    sys.path.append(parent_dir)

    print("项目根目录（上一级目录）:", parent_dir)
    directory_path = os.path.join(parent_dir, "app", "core", "20241224-a")

    tdms_file = TdmsFile(filename,memmap_dir=directory_path)
    
    for group_index in range(group_count):
        group_name = f"group{group_index}"
        group = tdms_file[group_name]
        
        # 使用get()按需读取
        channel = group["MA"]
        
        for i in range(0, data_length, chunk_size):
            # 逐块读取数据
            data = channel[i:i+chunk_size]
            # print(f"Group {group_name}, Data points {i}-{i+chunk_size-1}: {data}")

    
    end_time = time.time()
    final_memory = psutil.virtual_memory().used  # 获取最终内存使用情况
    time_taken = end_time - start_time
    memory_used = final_memory - initial_memory

    print(f"一次打开并多次读取 - 时间: {time_taken:.2f} 秒，内存增加: {memory_used / (1024 ** 2):.2f} MB")

def read_multiple_times_and_multiple_reopens(filename, group_count=40, data_length=100000):
    start_time = time.time()
    initial_memory = psutil.virtual_memory().used  # 获取初始内存使用情况

    for i in range(0, data_length, 100):
        read_tdms_segment(filename, i, 100)
        print(f"read_tdms_segment {i}")


    end_time = time.time()
    final_memory = psutil.virtual_memory().used  # 获取最终内存使用情况
    time_taken = end_time - start_time
    memory_used = final_memory - initial_memory

    print(f"多次打开并多次读取 - 时间: {time_taken:.2f} 秒，内存增加: {memory_used / (1024 ** 2):.2f} MB")

def read_tdms_in_chunks(file_path, chunk_size=100):
    """
    分块读取TDMS文件
    :param file_path: 文件路径
    :param start_index: 起始读取位置
    :param chunk_size: 每块的数据条数
    """
    
    initial_memory = psutil.virtual_memory().used  # 获取初始内存使用情况
    start_time = time.time()

    with TdmsFile.open(file_path) as tdms_file:
        for i in range(0, 100000, chunk_size):
        
            for group_num in range(40):  # 遍历40个group
                group_name = f"group{group_num}"
                try:
                    channel = tdms_file[group_name]["MA"]
                    # 计算结束索引
                    end_index = i + chunk_size
                    # 读取当前块
                    data_chunk = channel[i:end_index]
                except KeyError:
                    print(f"{group_name}: Channel MA not found")

    end_time = time.time()
    final_memory = psutil.virtual_memory().used  # 获取最终内存使用情况
    time_taken = end_time - start_time
    memory_used = final_memory - initial_memory
    print(f"多次打开并多次读取start={i} - 时间: {time_taken:.2f} 秒，内存增加: {memory_used / (1024 ** 2):.2f} MB")        

def describe_tdms_file(file_name):
    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    sys.path.append(parent_dir)

    print("项目根目录（上一级目录）:", parent_dir)
    directory_path = os.path.join(parent_dir, "app", "core", "20241224-a")
    file_path = os.path.join(directory_path, file_name)
    # 打开 .tdms 文件
    tdms_file = TdmsFile.read(file_path)

    # 打印文件中的所有 group 和 channel
    for group in tdms_file.groups():
        print(f"Group: {group.name}")
        for channel in group.channels():
            print(f"  Channel: {channel.name}")
            print(f"    Data type: {channel.data_type}")
            print(f"    Number of values: {len(channel)}")
            print(f"    Properties: {channel.properties}")


# 测试函数
def main():
    """测试接口功能"""
    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    sys.path.append(parent_dir)

    print("项目根目录（上一级目录）:", parent_dir)
    directory_path = os.path.join(parent_dir, "app", "core", "20241224-a")
    file_path = os.path.join(directory_path, "大文件测试.tdms")
    '''
    # 测试指定通道的分页读取
    group_channel_list = [
        ('控制口压力PT3', 'MPa'),
        ('排油口压力PT4', 'MPa'),
    ]
    result = handle_request_tmds_data(file_path, group_channel_list=group_channel_list, page=0, page_size=10)
    print(json.dumps(result, ensure_ascii=False, indent=4))
    '''
    # 测试读取所有通道数据
    # result = handle_request_tmds_data(file_path, group_channel_list=None, page=50000, page_size=100)
    #print(json.dumps(result, ensure_ascii=False, indent=4))
    # file_list = os.listdir(directory_path)
    # 过滤掉目录，只保留文件
    # files = [f for f in file_list if os.path.isfile(os.path.join(directory_path, f))]
    # group_name = "主油箱压力PT1"
    # channel_name = "MPa"
    # for file in files:
    #     tdms_file = TdmsFile(file_path)
    #     if group_name not in tdms_file:
    #         raise ValueError(f"文件中不存在组 '{group_name}'")
    #     group = tdms_file[group_name]
    #     if channel_name not in group:
    #         raise ValueError(f"组 '{group_name}' 中不存在通道 '{channel_name}'")
    #     channel = group[channel_name]

    #     # 获取该通道的数据
    #     data = channel[0:10]

    #     # 读取前5条数据
    #     print(data)  # 打印前5条数据
    
    generate_tdms_file(file_path, max_size_gb=10)
    # describe_tdms_file("大文件测试.tdms")
    # describe_tdms_file("2412241121232020001（24A试验前3）_.tdms")
    # read_once_and_multiple_times(file_path)
    # read_multiple_times_and_multiple_reopens(file_path)
    # read_tdms_in_chunks(file_path)

   
if __name__ == "__main__":
    main()
