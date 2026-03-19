import pandas as pd
import json
import numpy as np
import sys
import os
import base64
import io
import matplotlib.pyplot as plt
from openpyxl import load_workbook
import logging
import re

# 设置日志级别为 WARNING 或更高，这样就不会显示 DEBUG 级别的日志
logging.basicConfig(level=logging.WARNING)
# 禁用 PIL 的所有日志
logging.getLogger('PIL').addHandler(logging.NullHandler())
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
print("项目根目录（上一级目录）:", parent_dir)
# 将该路径添加到 sys.path
sys.path.append(parent_dir)
from app.core.time_domain_feature import TimeFeature

class TableProcessor:
    def __init__(self, file_path, fixed_chunk_size=10):
        """初始化 TableProcessor 类"""
        self.file_path = file_path  # 文件路径
        self.fixed_chunk_size = fixed_chunk_size  # 每次读取的固定数据行数

    def get_total_rows(self, sheet_name):
        """使用 openpyxl 获取行数，避免加载整个数据"""
        try:
            wb = load_workbook(self.file_path, read_only=True, keep_vba=False)
            sheet = wb[sheet_name]
            total_rows = sheet.max_row
            return total_rows
        except Exception as e:
            print(f"获取行数时发生错误: {e}")
            return 0

    def read_sheet(self, sheet_name, start_row, chunk_size):
        """按固定大小读取指定 sheet 页数据，跳过标题行"""
        try:
            total_rows = self.get_total_rows(sheet_name)
            # 修改 read_sheet
            skip_header = 1  # 假设第1行是标题
            actual_start = start_row + skip_header
            if actual_start >= total_rows:
                return pd.DataFrame()
            # 读取数据时将所有列作为对象/字符串读取
            sheet_data = pd.read_excel(
                self.file_path,
                sheet_name=sheet_name,
                engine='openpyxl',
                skiprows=range(0, actual_start),
                nrows=chunk_size,
                dtype=object  # 使用object类型保留原始格式
            )
            
            # 打印前几行数据以检查格式
            #print(f"Sheet {sheet_name} 前5行数据:")
            #print(sheet_data.head())
            
            # 尝试将数值列转换为数字
            for col in sheet_data.columns:
                # 检查是否是时间格式的列
                if sheet_data[col].astype(str).str.match(r'^\d{2}:\d{2}:\d{2}(\.\d+)?$').any():
                    # 如果是时间格式，保留为字符串
                    continue
                try:
                    # 尝试转换为数值
                    sheet_data[col] = pd.to_numeric(sheet_data[col], errors='coerce')
                except:
                    pass
            
            return sheet_data
        except Exception as e:
            print(f"读取 {sheet_name} 时发生错误: {e}")
            return pd.DataFrame()

    def get_page_data(self, sheet_name, page):
        """动态加载并获取分页数据，支持流式返回"""
        start_row = page * self.fixed_chunk_size
        sheet_data = self.read_sheet(sheet_name, start_row, self.fixed_chunk_size)
        return sheet_data

    def extract_features(self, data_chunk):
        """从数据块中提取特征值：均值、标准差等"""
        features = {}
        # 计算均值和标准差
        df = pd.DataFrame(data_chunk, columns=['Signal'])
        time_feature = TimeFeature(df)
        # 获取计算的特征
        features = time_feature.time_feature()
        return features

    def generate_spectrum(self, sheet_name, data_chunk):
        """从数据块生成频谱图，并返回图像的 base64 编码"""
        if len(data_chunk) == 0:
            print(f"Warning: 数据块 {sheet_name} 为空，无法生成频谱图")
            return None
        
        data = np.array(data_chunk).flatten()
        if len(data_chunk) < 2:
            print(f"Warning: 数据块 {sheet_name} 数据不足以计算频谱图")
            return None
        
        plt.figure()
        sampling_frequency = 100
        freqs = np.fft.fftfreq(len(data), d=1/sampling_frequency)
        fft_values = np.fft.fft(data)
        spectrum = np.abs(fft_values[:len(fft_values)//2])
        freqs = freqs[:len(freqs)//2]

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(freqs, spectrum)
        ax.set_title(f"Spectrogram of {sheet_name}")
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("Amplitude")
        ax.grid(True)
        
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        return img_base64

    def read_sheet_all(self, sheet_name):
        """读取整个 sheet 的所有数据"""
        try:
            # 读取整个 sheet，保留原始格式
            sheet_data = pd.read_excel(
                self.file_path,
                sheet_name=sheet_name,
                engine='openpyxl',
                dtype=object  # 使用object类型保留原始格式
            )
            
            # 尝试将数值列转换为数字
            for col in sheet_data.columns:
                # 检查是否是时间格式的列
                if sheet_data[col].astype(str).str.match(r'^\d{2}:\d{2}:\d{2}(\.\d+)?$').any():
                    # 如果是时间格式，保留为字符串
                    continue
                try:
                    # 尝试转换为数值
                    sheet_data[col] = pd.to_numeric(sheet_data[col], errors='coerce')
                except:
                    pass
            
            return sheet_data
        except Exception as e:
            print(f"读取 {sheet_name} 时发生错误: {e}")
            return pd.DataFrame()

    def stream_data(self, sheet_names, page):
        """返回指定页的数据"""
        result = {}
        for sheet_name in sheet_names:
            data_chunk = self.get_page_data(sheet_name, page)
            #print(data_chunk)
            if not data_chunk.empty:
                result[sheet_name] = {
                    'data_chunk': data_chunk,
                }
        return result

    def stream_data_all(self, sheet_names):
        """返回所有 sheet 的完整数据"""
        result = {}
        for sheet_name in sheet_names:
            data_chunk = self.read_sheet_all(sheet_name)
            if not data_chunk.empty:
                result[sheet_name] = {
                    'data_chunk': data_chunk,
                }
        return result

def handle_request_page_data(file_path, sheet_names, page, page_size=1000):
    """处理请求并返回指定页的数据"""
    processor = TableProcessor(file_path, fixed_chunk_size=page_size)
    result = processor.stream_data(sheet_names, page)
    result_res = {
        key: {
            column: result[key]['data_chunk'][column].astype(str).tolist()
            for column in result[key]['data_chunk'].columns
        }
        for key in result.keys()
    }
    return result_res

def handle_request_all_data(file_path, sheet_names):
    """处理请求并返回所有数据（不分页）"""
    processor = TableProcessor(file_path, fixed_chunk_size=1000)  # fixed_chunk_size 参数不再使用，但保留以兼容
    result = processor.stream_data_all(sheet_names)
    
    if not result:
        return {"message": "没有数据或sheet不存在"}
    
    result_res = {
        key: {
            column: result[key]['data_chunk'][column].astype(str).tolist()
            for column in result[key]['data_chunk'].columns
        }
        for key in result.keys()
    }
    return result_res

def main():
    """测试接口功能"""
    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    sys.path.append(parent_dir)

    print("项目根目录（上一级目录）:", parent_dir)
    directory_path = os.path.join(parent_dir, "app", "test_data")
    file_name = "标准泵3.18.xlsx"
    file_path = os.path.join(directory_path, file_name)
    sheet_names = ['13-1', '1']
    
    # 测试返回所有数据
    result = handle_request_all_data(file_path, sheet_names)
    print("返回的数据：", json.dumps(result, ensure_ascii=False, indent=4))
    
    # 如果需要测试分页功能，可以取消下面的注释
    # page = 0
    # page_size = 5000
    # result = handle_request_page_data(file_path, sheet_names, page, page_size)
    # print("返回的分页数据：", json.dumps(result, ensure_ascii=False, indent=4))

if __name__ == "__main__":
    res = main()
    print(res)