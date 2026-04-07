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
from app.core.table_processor import handle_request_all_data,handle_request_page_data,handle_request_txt_page_data
from app.core.tmds_data_process import handle_request_tmds_data

# 初始化 Flask 应用
app = Flask(__name__)

# 设置默认监控的目录路径
default_directory_path = os.path.join(parent_dir, "app", "test_data")
# 当前监控的目录路径（可由前端动态设置）
directory_path = default_directory_path
# 存储监控到的新文件
new_files = []
# 全局 observer 实例
observer = None
# 线程锁，用于保护 observer 操作
observer_lock = threading.Lock()

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
         and f.lower().endswith((".tdms", ".xlsx", ".xls", ".txt"))]
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
    """根据文件名读取 Excel 文件数据，支持分页读取"""
    try:
        # 获取请求参数
        page = int(request.args.get('page', 0))  # 页码，默认为0
        page_size = int(request.args.get('page_size', 500))  # 每页大小，默认为500
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
        if not file_path.lower().endswith(('.xlsx', '.xls', '.txt')):
            file_data[file_name] = {"error": "Invalid file type. Only .xlsx, .xls and .txt files are supported"}
            continue
        
        try:
            if file_path.lower().endswith('.txt'):
                page_data_response = handle_request_txt_page_data(file_path, sheet_names, page, page_size)
            else:
                page_data_response = handle_request_page_data(file_path, sheet_names, page, page_size)
            file_data[file_name] = {
                "data": page_data_response,
                "sheet_names": sheet_names,
                "page": page,
                "page_size": page_size
            }
        except Exception as e:
            file_data[file_name] = {"error": str(e)}

    return jsonify(file_data), 200


# 实时监测目录下是否有新文件
class WatcherHandler(FileSystemEventHandler):
    def __init__(self, watch_path):
        self.watch_path = watch_path
        
    def on_created(self, event):
        if not event.is_directory:
            new_files.append(os.path.basename(event.src_path))
            print(f"新文件被添加: {event.src_path}")

# 停止当前监控
def stop_watching():
    global observer
    with observer_lock:
        if observer is not None:
            observer.stop()
            observer.join()
            observer = None
            print("已停止当前监控")
            return True
        return False

# 启动监控线程
def start_watching(watch_path=None):
    global observer, directory_path
    
    # 如果提供了新路径，更新监控路径
    if watch_path:
        directory_path = watch_path
    
    # 确保目录存在
    if not os.path.exists(directory_path):
        try:
            os.makedirs(directory_path, exist_ok=True)
            print(f"创建监控目录: {directory_path}")
        except Exception as e:
            print(f"创建目录失败: {e}")
            return False
    
    with observer_lock:
        # 如果已有监控，先停止
        if observer is not None:
            observer.stop()
            observer.join()
        
        event_handler = WatcherHandler(directory_path)
        observer = Observer()
        observer.schedule(event_handler, directory_path, recursive=False)
        observer.start()
        print(f"开始监控目录: {directory_path}")
        return True

# 后台线程启动默认监控
def init_default_monitoring():
    """初始化默认监控（在应用启动时调用）"""
    if os.path.exists(default_directory_path):
        start_watching(default_directory_path)

# 启动默认监控线程
monitor_thread = threading.Thread(target=init_default_monitoring, daemon=True)
monitor_thread.start()

# 设置监控路径（由前端调用）
@app.route('/set_watch_path', methods=['POST'])
def set_watch_path():
    """设置文件监控路径"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        path = data.get('path')
        if not path:
            return jsonify({"error": "path parameter is required"}), 400
        
        # 验证路径是否存在，不存在则尝试创建
        if not os.path.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                return jsonify({"error": f"Failed to create directory: {str(e)}"}), 400
        
        # 验证路径是否为目录
        if not os.path.isdir(path):
            return jsonify({"error": "Path must be a directory"}), 400
        
        # 清空之前监控到的新文件列表
        new_files.clear()
        
        # 启动新的监控
        success = start_watching(path)
        if success:
            return jsonify({
                "message": "Watch path updated successfully",
                "path": path
            }), 200
        else:
            return jsonify({"error": "Failed to start watching"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 获取当前监控路径
@app.route('/get_watch_path', methods=['GET'])
def get_watch_path():
    """获取当前监控路径"""
    try:
        return jsonify({
            "path": directory_path,
            "is_default": directory_path == default_directory_path
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 获取实时监测到的新文件
@app.route('/new_files', methods=['GET'])
def get_new_files():
    try:
        path = request.args.get('path')
        
        # 如果提供了路径参数，检查是否与当前监控路径匹配
        if path and path != directory_path:
            # 路径不匹配，返回提示信息
            return jsonify({
                "message": "Path mismatch",
                "current_watch_path": directory_path,
                "requested_path": path,
                "new_files": []
            }), 200
        
        if new_files:
            files = new_files.copy()  # 复制新文件列表
            new_files.clear()  # 清空已返回的文件列表
            return jsonify({"new_files": files}), 200
        else:
            return jsonify({"new_files": []}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/previewExcel', methods=['GET'])
def preview_excel():
    """预览 Excel 文件前几行数据，用于创建页面的文件验证"""
    try:
        file_path = request.args.get('file_path')
        if not file_path:
            return jsonify({"error": "file_path parameter is required"}), 400
        if not os.path.isfile(file_path):
            return jsonify({"error": "File not found"}), 404
        if not file_path.lower().endswith(('.xlsx', '.xls')):
            return jsonify({"error": "Only .xlsx and .xls files are supported"}), 400

        xl = pd.ExcelFile(file_path)
        sheet_names = xl.sheet_names
        preview = {}
        for sheet in sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet, nrows=5)
            preview[sheet] = {
                "columns": df.columns.tolist(),
                "rows": df.fillna("").values.tolist()
            }
        return jsonify({"sheet_names": sheet_names, "preview": preview}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 启动 Flask 服务
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True, use_reloader=False)

