from flask import Flask, request, jsonify, send_file
import os
import sys
import traceback
from werkzeug.serving import WSGIRequestHandler

# 设置 socket 选项
WSGIRequestHandler.protocol_version = "HTTP/1.1"
WSGIRequestHandler.tcp_nodelay = True

# 将项目根目录添加到 sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
print("项目根目录:", parent_dir)
sys.path.append(parent_dir)
print("sys.path:", sys.path)
import app.core.db_operations as db_ops



# 初始化 Flask 应用
app = Flask(__name__)

app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False  # 不格式化 JSON 输出
app.config['JSON_SORT_KEYS'] = False  # 不排序 JSON 键

# 存储诊断报告的 API
@app.route('/store_report', methods=['GET'])
def api_store_report():
    try:
        # 从查询参数中获取数据
        task_id = request.args.get('task_id')
        report_type = request.args.get('type')
        path = request.args.get('path')
        file_name_list = request.args.get('file_name').split(",")
        
        print(path)
        for file_name in file_name_list:
            file_real_name = os.path.join(path, file_name)
            task_id = db_ops.store_fault_diagnosis_report(task_id, report_type,file_real_name)
        return jsonify({"message": "Report stored successfully", "task_id": task_id}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 400
    
# 存储诊断报告的 API
@app.route('/stopJob', methods=['GET'])
def stopJob():
    try:
        # 从查询参数中获取数据
        task_id = request.args.get('task_id')
        if not task_id :
            raise ValueError("task_id are required parameters.")
        
        db_ops.stopJob(task_id)
        return jsonify({"message": "Report stored successfully", "task_id": task_id}), 200
    except Exception as e:
        print("Error:", str(e))  # 打印错误信息
        return jsonify({"error": str(e)}), 400
    
@app.route('/startJob', methods=['GET'])
def startJob():
    try:
        # 从查询参数中获取数据
        task_id = request.args.get('task_id')
        if not task_id :
            raise ValueError("task_id are required parameters.")
        
        onGoingTask = db_ops.getOngingJob()
        if onGoingTask and onGoingTask['task_id'] != task_id:
            return jsonify({"error": "有正在运行的任务"}), 400

        db_ops.startJob(task_id)
        return jsonify({"message": "Report stored successfully", "task_id": task_id}), 200
    except Exception as e:
        print("Error:", str(e))  # 打印错误信息
        return jsonify({"error": str(e)}), 400
    
@app.route('/deleteJob', methods=['GET'])
def deleteJob():
    try:
        # 从查询参数中获取数据
        task_id = request.args.get('task_id')
        if not task_id :
            raise ValueError("task_id are required parameters.")
        
        db_ops.deleteJob(task_id)
        return jsonify({"message": "Report stored successfully", "task_id": task_id}), 200
    except Exception as e:
        print("Error:", str(e))  # 打印错误信息
        return jsonify({"error": str(e)}), 400
    
@app.route('/getGoingJob', methods=['GET'])
def getGoingJob():
    try:
        # 从查询参数中获取数据
        task = db_ops.getOngingJob()
        return jsonify(task), 200
    except Exception as e:
        print("Error:", str(e))  # 打印错误信息
        return jsonify({"error": str(e)}), 400

@app.route('/getJobStatus', methods=['GET'])
def getJobStatus():
    try:
        taskId = request.args.get('taskId')
        if not taskId :
            raise ValueError("task_id are required parameters.")
        status = db_ops.getJobStatus(taskId)
        return jsonify({"status":status}), 200
    except Exception as e:
        print("Error:", str(e))  # 打印错误信息
        return jsonify({"error": str(e)}), 400

# 获取诊断报告的 API
@app.route('/retrieve_report/<task_id>', methods=['GET'])
def api_retrieve_report(task_id):
    try:
        report_stream = db_ops.retrieve_fault_diagnosis_report(task_id)
        if report_stream:
            return send_file(report_stream, as_attachment=True, download_name=f"{task_id}_diagnosis_report.docx")
        return jsonify({"error": "Report not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# 获取所有任务的 API
@app.route('/tasks', methods=['GET'])
def api_get_tasks():
    try:
        # 获取请求参数，并转换为整数类型
        page = request.args.get('page', default=1, type=int)  # 默认第1页
        page_size = request.args.get('pageSize', default=10, type=int)  # 默认每页10条
        task_id = request.args.get('nameOrCode', default=None, type=str)  # 模糊查询的ID
        status = request.args.get('status', default=None, type=str)  # 精确查询的状态

        # 调用分页查询函数
        tasks = db_ops.query_tasks(page=page, page_size=page_size, task_id=task_id, status=status)
        return jsonify(tasks), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# 更新任务状态的 API
@app.route('/update_status/<task_id>', methods=['POST'])
def api_update_status(task_id):
    try:
        data = request.get_json()
        status = data['status']
        success = db_ops.update_task_status(task_id, status)
        if success:
            return jsonify({"message": "Task status updated successfully"}), 200
        return jsonify({"error": "Task not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# 删除任务的 API
@app.route('/delete_task/<task_id>', methods=['DELETE'])
def api_delete_task(task_id):
    try:
        success = db_ops.delete_task(task_id)
        if success:
            return jsonify({"message": "Task deleted successfully"}), 200
        return jsonify({"error": "Task not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# 创建新任务的 API
@app.route('/createJob', methods=['GET'])
def api_create_job():
    try:
        # 从查询参数中获取数据
        task_id = request.args.get('task_id')
        report_type = request.args.get('type')
        path = request.args.get('path')
        file_name = request.args.get('file_name')
        
        # 检查必填参数
        if not all([task_id, report_type, path, file_name]):
            raise ValueError("task_id, type, path and file_name are required parameters.")
        
        # 调用数据库操作创建任务
        db_ops.createJob(task_id, report_type, path, file_name)
        
        return jsonify({
            "message": "Job created successfully",
            "task_id": task_id,
            "type": report_type,
            "path": path,
            "file_name": file_name
        }), 200
    except Exception as e:
        print("Error:", str(e))  # 打印错误信息
        return jsonify({"error": str(e)}), 400


# 运行 Flask 应用
if __name__ == '__main__':
    # 创建数据库表
    db_ops.create_tables()

    # 运行 Flask 服务器
    app.run(host='0.0.0.0', port=5001, threaded=True, processes=1)




