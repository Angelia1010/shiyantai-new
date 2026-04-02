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
sys.path.append(parent_dir)
import app.core.db_operations as db_ops



# 初始化 Flask 应用
app = Flask(__name__)

app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False  # 不格式化 JSON 输出
app.config['JSON_SORT_KEYS'] = False  # 不排序 JSON 键

# 存储诊断报告的 API
@app.route('/store_report', methods=['GET'])
def api_store_report():
    """
    支持两种模式：
    1. 文件模式：传入 task_id + type + path + file_name
    2. 直接传参模式：传入 task_id + type + x1 + x2
    """
    try:
        task_id = request.args.get('task_id')
        report_type = request.args.get('type')
        if not all([task_id, report_type]):
            raise ValueError("task_id and type are required.")

        x1 = request.args.get('x1', type=float)
        x2 = request.args.get('x2', type=float)

        if x1 is not None and x2 is not None:
            task_id = db_ops.store_fault_diagnosis_report(task_id, report_type, x1=x1, x2=x2)
        else:
            path = request.args.get('path')
            file_name_str = request.args.get('file_name')
            if not all([path, file_name_str]):
                raise ValueError("需要提供 (path + file_name) 或 (x1 + x2)。")
            for file_name in file_name_str.split(","):
                file_real_name = os.path.join(path, file_name.strip())
                task_id = db_ops.store_fault_diagnosis_report(task_id, report_type, file_name=file_real_name)

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

# 获取结构化诊断报告（供前端展示）
@app.route('/report_preview/<task_id>', methods=['GET'])
def api_report_preview(task_id):
    try:
        data = db_ops.get_report_json(task_id)
        if data is None:
            return jsonify({"error": "Report not found"}), 404
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# 获取诊断报告的 API（下载 Word 文件）
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
        page = request.args.get('page', default=1, type=int)
        page_size = request.args.get('pageSize', default=10, type=int)
        task_id = request.args.get('nameOrCode', default=None, type=str)
        status = request.args.get('status', default=None, type=str)
        start_time = request.args.get('startTime', default=None, type=int)
        end_time = request.args.get('endTime', default=None, type=int)
        
        if end_time is not None:
            end_time = end_time + 86400000

        tasks = db_ops.query_tasks(
            page=page, 
            page_size=page_size, 
            task_id=task_id, 
            status=status,
            start_time=start_time,
            end_time=end_time
        )
        return jsonify(tasks), 200
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


# 故障诊断接口
@app.route('/diagnose', methods=['GET'])
def diagnose():
    """
    支持两种模式：
    1. 文件模式：传入 task_id + path + file_name，从 Excel 文件读取 X1/X2
    2. 直接传参模式：传入 task_id + x1 + x2，直接用公式计算
    """
    try:
        task_id = request.args.get('task_id')
        if not task_id:
            raise ValueError("task_id is required.")

        x1 = request.args.get('x1', type=float)
        x2 = request.args.get('x2', type=float)

        if x1 is not None and x2 is not None:
            # 直接传参模式
            task_id = db_ops.store_fault_diagnosis_report(
                task_id, '0', file_name=None, x1=x1, x2=x2
            )
        else:
            # 文件模式
            path = request.args.get('path')
            file_name = request.args.get('file_name')
            if not all([path, file_name]):
                raise ValueError("需要提供 (path + file_name) 或 (x1 + x2)。")
            file_real_name = os.path.join(path, file_name)
            task_id = db_ops.store_fault_diagnosis_report(task_id, '0', file_name=file_real_name)

        return jsonify({"message": "Diagnosis completed", "task_id": task_id}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 400


# ============ 仿真数据模型接口 ============

@app.route('/dataModels', methods=['GET'])
def api_get_data_models():
    try:
        page = request.args.get('page', default=1, type=int)
        page_size = request.args.get('pageSize', default=10, type=int)
        name = request.args.get('name', default=None, type=str)
        status = request.args.get('status', default=None, type=str)
        result = db_ops.get_data_models(page=page, page_size=page_size, name=name, status=status)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/dataModel/<int:model_id>', methods=['GET'])
def api_get_data_model(model_id):
    try:
        model = db_ops.get_data_model(model_id)
        if not model:
            return jsonify({"error": "DataModel not found"}), 404
        return jsonify(model), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/createDataModel', methods=['POST'])
def api_create_data_model():
    try:
        data = request.get_json()
        if not data or not data.get('name'):
            raise ValueError("name is required.")
        model = db_ops.create_data_model(
            name=data['name'],
            description=data.get('description', ''),
            file_path=data.get('file_path', '')
        )
        return jsonify(model), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 400


@app.route('/updateDataModel/<int:model_id>', methods=['PUT'])
def api_update_data_model(model_id):
    try:
        data = request.get_json()
        model = db_ops.update_data_model(
            model_id=model_id,
            name=data.get('name'),
            description=data.get('description'),
            file_path=data.get('file_path')
        )
        if not model:
            return jsonify({"error": "DataModel not found"}), 404
        return jsonify(model), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/deleteDataModel/<int:model_id>', methods=['DELETE'])
def api_delete_data_model(model_id):
    try:
        success = db_ops.delete_data_model(model_id)
        if not success:
            return jsonify({"error": "DataModel not found"}), 404
        return jsonify({"message": "DataModel deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/analyzeDataModel/<int:model_id>', methods=['POST'])
def api_analyze_data_model(model_id):
    try:
        model = db_ops.get_data_model(model_id)
        if not model:
            return jsonify({"error": "DataModel not found"}), 404
        db_ops.set_data_model_status(model_id, 'Processing')
        # 以模型文件路径执行诊断分析，将结果存入数据库
        file_path = model.get('file_path', '')
        if file_path and os.path.isfile(file_path):
            try:
                db_ops.store_fault_diagnosis_report(
                    task_id=f"dm_{model_id}",
                    type='0',
                    file_name=file_path
                )
                db_ops.set_data_model_status(model_id, 'Completed')
            except Exception as inner_e:
                db_ops.set_data_model_status(model_id, 'Failed')
                return jsonify({"error": str(inner_e)}), 400
        else:
            db_ops.set_data_model_status(model_id, 'Completed')
        return jsonify({"message": "Analysis started", "model_id": model_id}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 400


@app.route('/downloadAnalysisResult/<int:model_id>', methods=['GET'])
def api_download_analysis_result(model_id):
    try:
        result_stream = db_ops.get_data_model_result(model_id)
        if result_stream:
            return send_file(result_stream, as_attachment=True,
                             download_name=f"datamodel_{model_id}_analysis.docx")
        return jsonify({"error": "Analysis result not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ============ 自动诊断流程接口 ============

auto_diagnosis_state = {
    'running': False,
    'step': 0,
    'message': '等待启动',
    'type': 'info',
    'level': 'info',
    'featureMap': {},
    'result': None,
    'completed': False,
    'config': {}
}

@app.route('/auto_diagnosis/start', methods=['POST'])
def api_start_auto_diagnosis():
    try:
        data = request.get_json()
        if not data:
            raise ValueError("请求体必须是JSON格式")

        auto_diagnosis_state['running'] = True
        auto_diagnosis_state['step'] = 1
        auto_diagnosis_state['message'] = '数据监控中...'
        auto_diagnosis_state['type'] = 'info'
        auto_diagnosis_state['level'] = 'info'
        auto_diagnosis_state['result'] = None
        auto_diagnosis_state['completed'] = False
        auto_diagnosis_state['config'] = data

        import uuid
        task_id = f"auto_{uuid.uuid4().hex[:8]}"

        return jsonify({
            "success": True,
            "message": "自动诊断已启动",
            "taskId": task_id
        }), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 400


@app.route('/auto_diagnosis/stop', methods=['POST'])
def api_stop_auto_diagnosis():
    try:
        auto_diagnosis_state['running'] = False
        auto_diagnosis_state['message'] = '已停止'
        auto_diagnosis_state['type'] = 'warning'
        auto_diagnosis_state['level'] = 'warn'

        return jsonify({
            "success": True,
            "message": "自动诊断已停止"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/auto_diagnosis/status', methods=['GET'])
def api_get_diagnosis_status():
    try:
        return jsonify({
            "step": auto_diagnosis_state['step'],
            "message": auto_diagnosis_state['message'],
            "type": auto_diagnosis_state['type'],
            "level": auto_diagnosis_state['level'],
            "featureMap": auto_diagnosis_state['featureMap'],
            "result": auto_diagnosis_state['result'],
            "completed": auto_diagnosis_state['completed']
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# 运行 Flask 应用
if __name__ == '__main__':
    # 创建数据库表
    db_ops.create_tables()

    # 运行 Flask 服务器
    app.run(host='0.0.0.0', port=5001, threaded=True, processes=1)




