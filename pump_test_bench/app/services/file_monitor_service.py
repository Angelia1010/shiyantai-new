import os
import sys
import time
import json
import pandas as pd
from flask import Flask, jsonify, request
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading

# 将项目根目录添加到 sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
print("项目根目录（上一级目录）:", parent_dir)
sys.path.append(parent_dir)
from app.core.table_processor import handle_request_all_data,handle_request_page_data
from app.core.tmds_data_process import handle_request_tmds_data

# 初始化 Flask 应用
app = Flask(__name__)

# 设置监控的目录路径
directory_path = os.path.join(parent_dir, "app", "test_data")
# 存储监控到的新文件
new_files = []

# 获取本地目录下的所有文件
@app.route('/files', methods=['GET'])
def get_files():
    try:
        path = request.args.get('path')  # 获取文件名列表
        print("files params:------------------")
        print(path)
        if not path:
            return jsonify({"error": "path parameter is required"}), 400
        files = [f for f in os.listdir(path) 
         if os.path.isfile(os.path.join(path, f)) 
         and f.lower().endswith((".tdms", ".xlsx", ".xls"))]
        return jsonify({"files": files}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/read_tdms', methods=['GET'])
def read_tdms():
    """根据文件名读取 TDMS 文件数据"""
    try:
        page = int(request.args.get('page', 0))  # 默认为第 0 页
        page_size = int(request.args.get('page_size', 10))  # 每页大小，默认为 10
        file_names = request.args.getlist('file_names[]')  # 获取文件名列表
        path = request.args.get('path')  # 获取文件名列表
        group_channel_str = request.args.get('group_channel', '')
        group_channel_list = group_channel_str.split(',') if group_channel_str else []
    except ValueError:
        return jsonify({"error": "Invalid page or page_size parameter. Must be an integer"}), 400

    if not file_names:
        return jsonify({"error": "file_names parameter is required"}), 400

    # 将组名和通道名解析为 [(group1, channel1), (group2, channel2), ...]
    try:
        group_channel_list = [tuple(item.split('/')) for item in group_channel_list]
    except ValueError:
        return jsonify({"error": "Invalid group_channel format. Expected 'GroupName/ChannelName'"}), 400

    print(group_channel_list)
    file_data = {}
    for file_name in file_names:
        # 构建文件路径，处理路径末尾的斜杠
        if path and path.endswith('/'):
            file_path = os.path.join(path.rstrip('/'), file_name)
        else:
            file_path = os.path.join(path, file_name) if path else file_name

        print(f"文件路径: {file_path}")
        if not os.path.isfile(file_path):
            file_data[file_name] = {"error": "File not found"}
            continue
        try:
            all_page_data_response = handle_request_tmds_data(file_path, group_channel_list, page, page_size)
            file_data[file_name] = all_page_data_response
        except Exception as e:
            file_data[file_name] = {"error": str(e)}

    return jsonify(file_data), 200

# 根据文件名读取 Excel 文件数据（返回多个文件内容）
@app.route('/read_excel', methods=['GET'])
def read_excel():
    """根据文件名读取 Excel 文件数据，返回所有数据（不分页）"""
    try:
        # 获取请求参数
        file_names = request.args.getlist('file_names[]')  # 获取文件名列表（支持多个文件）
        if not file_names:
            # 兼容单个文件名的参数名
            file_name = request.args.get('file_name')
            if file_name:
                file_names = [file_name]
        path = request.args.get('path')  # 获取文件路径
        sheet_names_str = request.args.get('sheet_names', '')  # 获取sheet名称，逗号分隔
        
        # 解析sheet名称列表
        sheet_names = [s.strip() for s in sheet_names_str.split(',') if s.strip()] if sheet_names_str else []
    except ValueError as e:
        return jsonify({"error": f"Invalid parameter format: {str(e)}"}), 400

    if not file_names:
        return jsonify({"error": "file_names or file_name parameter is required"}), 400
    
    if not path:
        return jsonify({"error": "path parameter is required"}), 400
    
    if not sheet_names:
        return jsonify({"error": "sheet_names parameter is required"}), 400

    file_data = {}
    for file_name in file_names:
        # 构建文件路径，处理路径末尾的斜杠
        if path and path.endswith('/'):
            file_path = os.path.join(path.rstrip('/'), file_name)
        else:
            file_path = os.path.join(path, file_name) if path else file_name
        
        # 验证文件是否存在
        if not os.path.isfile(file_path):
            file_data[file_name] = {"error": "File not found"}
            continue
        
        # 验证文件扩展名
        if not file_path.lower().endswith(('.xlsx', '.xls')):
            file_data[file_name] = {"error": "Invalid file type. Only .xlsx and .xls files are supported"}
            continue
        
        try:
            # 调用处理函数读取Excel全部数据
            all_data_response = handle_request_all_data(file_path, sheet_names)
            file_data[file_name] = {
                "data": all_data_response,
                "sheet_names": sheet_names
            }
        except Exception as e:
            file_data[file_name] = {"error": str(e)}

    return jsonify(file_data), 200


# 实时监测目录下是否有新文件
class WatcherHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            new_files.append(event.src_path)
            print(f"新文件被添加: {event.src_path}")

# 启动监控线程
def start_watching():
    event_handler = WatcherHandler()
    observer = Observer()
    observer.schedule(event_handler, directory_path, recursive=False)  # 监控当前目录
    observer.start()
    print(f"开始监控目录: {directory_path}")
    try:
        while True:
            time.sleep(1)  # 保持线程活跃
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

# 后台线程启动监控
monitor_thread = threading.Thread(target=start_watching, daemon=True)
monitor_thread.start()

# 获取实时监测到的新文件
@app.route('/new_files', methods=['GET'])
def get_new_files():
    try:
        if new_files:
            files = new_files.copy()  # 复制新文件列表
            new_files.clear()  # 清空已返回的文件列表
            return jsonify({"new_files": files}), 200
        else:
            return jsonify({"message": "No new files detected"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 启动 Flask 服务
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

