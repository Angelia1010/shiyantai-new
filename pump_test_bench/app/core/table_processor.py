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

# 设置日志级别为 WARNING 或更高，这样就不会显示 DEBUG 级别的日志
logging.basicConfig(level=logging.WARNING)
# 禁用 PIL 的所有日志
logging.getLogger('PIL').addHandler(logging.NullHandler())
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(parent_dir)
from app.core.time_domain_feature import TimeFeature

class TableProcessor:
    def __init__(self, file_path, fixed_chunk_size=10):
        """初始化 TableProcessor 类"""
        self.file_path = file_path  # 文件路径
        self.fixed_chunk_size = fixed_chunk_size  # 每次读取的固定数据行数
        self.column_names = {}  # 存储每个sheet的列名 {sheet_name: [col1, col2, ...]}

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
            # 第1行是标题，数据从第2行开始（Excel行号从1开始，pandas使用0-based索引）
            # start_row=0 表示从第2行开始读取（跳过第1行标题）
            header_row = 0  # 标题行索引（0-based）
            data_start_row = 1  # 数据开始行索引（0-based）
            
            # 计算实际要跳过的行数
            # page=0: 跳过第0行（标题），从第1行开始读取数据
            # page=1: 跳过第0行（标题）+ 第1-500行（数据），从第501行开始
            actual_start = data_start_row + start_row
            if actual_start >= total_rows:
                print(f"实际起始行 {actual_start} >= 总行数 {total_rows}，返回空数据")
                return pd.DataFrame()
            
            print(f"读取sheet: {sheet_name}, start_row: {start_row}, chunk_size: {chunk_size}, "
                  f"actual_start: {actual_start}, total_rows: {total_rows}")
            
            # 读取数据时将所有列作为对象/字符串读取
            if start_row == 0:
                # 第一页：读取标题行和数据
                sheet_data = pd.read_excel(
                    self.file_path,
                    sheet_name=sheet_name,
                    engine='openpyxl',
                    header=header_row,  # 使用第0行作为标题
                    nrows=chunk_size,
                    dtype=object  # 使用object类型保留原始格式
                )
                # 保存列名供后续页使用
                self.column_names[sheet_name] = list(sheet_data.columns)
                print(f"第一页，保存列名: {self.column_names[sheet_name][:5]}...")
            else:
                # 后续页：跳过标题行和之前的数据行
                skip_rows = range(0, actual_start)
                sheet_data = pd.read_excel(
                    self.file_path,
                    sheet_name=sheet_name,
                    engine='openpyxl',
                    skiprows=skip_rows,
                    nrows=chunk_size,
                    dtype=object,  # 使用object类型保留原始格式
                    header=None  # 不将第一行作为标题
                )
                # 使用第一页保存的列名
                if sheet_name in self.column_names:
                    # 确保列数匹配
                    saved_cols = self.column_names[sheet_name]
                    if len(sheet_data.columns) == len(saved_cols):
                        sheet_data.columns = saved_cols
                    else:
                        print(f"警告：列数不匹配，保存的列数 {len(saved_cols)}，实际列数 {len(sheet_data.columns)}")
                        # 使用默认列名
                        sheet_data.columns = [f"Col_{i}" for i in range(len(sheet_data.columns))]
                else:
                    # 如果没有保存的列名，使用默认列名
                    sheet_data.columns = [f"Col_{i}" for i in range(len(sheet_data.columns))]
                print(f"后续页，使用列名: {list(sheet_data.columns)[:5]}...")
            
            print(f"读取到 {len(sheet_data)} 行数据")
            
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
            import traceback
            traceback.print_exc()
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