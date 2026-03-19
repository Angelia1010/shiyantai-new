import pandas as pd
import pandas as pd

# 假设 Excel 文件的路径
EXCEL_FILE_PATH = 'large_file.xlsx'

# 根据页码和每页数据大小流式读取 Excel 文件的函数
def query_excel(file_path, page, page_size):
    try:
        # 使用 pandas 的 chunk 读取功能按块读取 Excel 文件
        chunk_iter = pd.read_excel(file_path, chunksize=page_size, engine='openpyxl')

        # 跳到第 `page` 页
        for _ in range(page - 1):
            next(chunk_iter)

        # 获取当前页的数据
        current_chunk = next(chunk_iter)

        # 将当前块的数据转换为字典列表，方便后续返回 JSON
        return current_chunk.to_dict(orient='records')
    
    except Exception as e:
        return {"error": f"查询失败: {str(e)}"}

# 流式读取 Excel 文件并按页返回数据
def get_page_data(page, page_size):
    return query_excel(EXCEL_FILE_PATH, page, page_size)

