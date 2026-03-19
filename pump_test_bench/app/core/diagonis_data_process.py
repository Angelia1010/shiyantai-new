import numpy as np
from nptdms import TdmsFile
import os
import sys

# 获取项目根目录路径
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
print("项目根目录（上一级目录）:", parent_dir)
sys.path.append(parent_dir)

# 从自定义模块导入
from app.core.time_domain_feature import TimeFeature
from app.core.frequency_features import FrequencyFeature

class FaultDataProcessor:
    def __init__(self, file_path, sampling_rate=100):
        self.file_path = file_path
        self.sampling_rate = sampling_rate

    def read_and_process_channels(self, group_channel_list):
        """读取指定通道的数据并进行处理"""
        print(f"开始读取 {len(group_channel_list)} 个通道数据...")

        tdms_file = TdmsFile.read(self.file_path)
        processed_data = []

        # 如果 group_channel_list 为空，读取所有通道数据
        if not group_channel_list:
            group_channel_list = [
                (group.name, channel.name)
                for group in tdms_file.groups()
                for channel in group.channels()
            ]
            print(f"读取所有通道数据，共 {len(group_channel_list)} 个通道。")
        else:
            print(f"读取指定通道数据，共 {len(group_channel_list)} 个通道。")

        # 遍历每个指定的通道
        for group_name, channel_name in group_channel_list:
            # 获取指定通道的数据
            channel_data = tdms_file[group_name][channel_name].data
            processed_data.append(channel_data)

        # 返回处理后的数据（一个列表，每个元素是一个通道的数据）
        print(f"所有指定通道数据处理完毕.")
        return processed_data, group_channel_list

    def get_fault_data(self, group_channel_list):
        """获取处理后的故障数据"""
        # 读取并处理指定通道的数据
        processed_data, group_channel_list = self.read_and_process_channels(group_channel_list)

        # 计算所有通道数据的最大长度
        max_length = max(len(channel_data) for channel_data in processed_data)

        # 对所有数据进行填充，使得每列的数据长度相同
        padded_data = [
            np.pad(channel_data, (0, max_length - len(channel_data)), mode='constant', constant_values=np.nan)
            for channel_data in processed_data
        ]

        # 将所有通道数据堆叠成一个二维数组
        fault_data = np.column_stack(padded_data)

        # 生成列名：基于通道名称生成列名
        column_names = [f"{group_name}_{channel_name}" for group_name, channel_name in group_channel_list]

        return fault_data, column_names

def main():
    # 设置 TDMS 文件路径（请替换为实际文件路径）
    # 将项目根目录添加到 sys.path
    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))

    # 将该路径添加到 sys.path
    sys.path.append(parent_dir)
    print("项目根目录（上一级目录）:", parent_dir)
    
    # 设置监控的目录路径
    directory_path = os.path.join(parent_dir, "app", "test_data", "20241224-a")
    file_path = directory_path + "/2412241520302020001（24A试验载荷谱-随动活塞磨损试验-12.24载荷谱）_.tdms"
    
    # 创建 FaultDataProcessor 实例
    processor = FaultDataProcessor(file_path)
    
    # group_channel_list 为空，意味着读取所有通道
    group_channel_list = []
    
    # 获取处理后的数据
    print("开始处理指定通道数据...")
    fault_data, column_names = processor.get_fault_data(group_channel_list=group_channel_list)
    
    # 打印处理结果，展示前五行数据
    print(f"处理后的数据：\n{fault_data.shape}")
    print(f"列名：\n{column_names}")

if __name__ == "__main__":
    main()
