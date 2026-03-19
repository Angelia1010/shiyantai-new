from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import sys

# 获取当前脚本所在目录的父目录（项目根目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE_DIR, "model")

def StartUp():
    # 添加 Python 模块路径
    ame_path = os.environ.get("AME")
    if ame_path:
        print("AME path",ame_path)
        module_path = os.path.join(ame_path, "scripting", "python")
        sys.path.append(module_path)
        sys.path.append(os.path.join(module_path, "win64"))
        sys.path.append(os.path.join(ame_path,"win64"))

        # 添加 DLLs 路径
        os.environ["PATH"] = os.path.join(ame_path, "sys", "python", "win64", "DLLs") + os.pathsep + os.environ["PATH"]
        os.environ["CONDA_DLL_SEARCH_MODIFICATION_ENABLE"] = "1"
        #请根据自身情况修改Amesim的安装路径
        os.add_dll_directory(os.path.join(ame_path,"win64"))
        os.add_dll_directory(module_path)
        os.add_dll_directory(os.path.join(module_path, "win64"))

        # 禁用用户站点
        os.environ["PYTHONNOUSERSITE"] = "1"

        # 设置 QT 插件路径
        os.environ["QT_PLUGIN_PATH"] = os.path.join(ame_path, "win64")

StartUp()

if 'ame_apy' not in sys.modules:
    try:
        from ame_apy import *
    # except ImportError:
    #     print('Unable to import Simcenter Amesim API module.\nCheck the AME environment variable.')
    except Exception as e:
        print("Import error:", repr(e))

# 创建Flask应用
app = Flask(__name__)
CORS(app)  # 启用跨域支持

class AmeSimuSessionServiceHandler:
    """AMESim服务处理器类"""
    
    # 初始化API
    def init_api(self):
        AMEInitAPI()
    
    # 打开模型文件
    def open_ame_file(self, ame_file_path):
        # 如果路径是相对路径，尝试从model目录查找
        if not os.path.isabs(ame_file_path):
            # 尝试在model目录下查找
            model_path = os.path.join(MODEL_DIR, ame_file_path)
            if os.path.exists(model_path):
                ame_file_path = model_path
            # 如果model目录下没有，尝试当前路径
            elif not os.path.exists(ame_file_path):
                # 如果都不存在，使用原始路径（可能会报错，但保持原有行为）
                pass
        AMEOpenAmeFile(ame_file_path)
    
    # 关闭circuit且不保存
    def close_circuit(self):
        AMECloseCircuit(False)
    
    # 关闭API
    def close_api(self):
        AMECloseAPI()
    
    # 读取模型运行参数，全局参数，部件参数
    def get_model_all_parameter(self):
        total_parameter = {}
        run_parameter = {}
        global_parameter = {}
        comp_parameter = {}

        run_parameter['stop_time_s'] = AMEGetRunParameter('stop_time_s')
        run_parameter['interval_s'] = AMEGetRunParameter('interval_s')

        for gP in AMEGetGlobalParameterNames():
            global_parameter[gP] = AMEGetGlobalParameterValue(gP)

        for compline in AMECreateCompLineIteration(ame_compline_comp):
            for parvar in AMECreateParVarIteration(compline, ame_parvar_all):
                if AMEIsParameter(parvar):
                    comp_parameter[AMECopyDataPath(parvar)] = AMEGetParameterValue(parvar)

        total_parameter = {
            'runParameter': run_parameter,
            'globalParameter': global_parameter,
            'compParameter': comp_parameter
        }
        return total_parameter
    
    # 设置运行参数
    def set_run_parameter(self, path_of_parameter, value_of_parameter):
        AMESetRunParameter(path_of_parameter, value_of_parameter)

    # 设置全局参数
    def set_global_parameter(self, path_of_parameter, value_of_parameter):
        AMESetGlobalParameterValue(path_of_parameter, value_of_parameter)

    # 设置部件参数
    def set_comp_parameter(self, path_of_parameter, value_of_parameter):
        AMESetParameterValue(path_of_parameter, value_of_parameter)

    # 运行仿真实验
    def run_simulation(self):
        print("in AMERunSimulation")
        AMERunSimulation()
    
    # 获取指定变量结果数据
    def get_variable_values(self, path_of_variable):
        result = {}

        value_result_tuple = AMEGetVariableValues(path_of_variable)
        value_dict = dict(value_result_tuple)

        info_dict = {}
        variable_info = AMEGetVariableInfos(path_of_variable)
        info_dict['path'] = path_of_variable
        info_dict['title'] = variable_info[2]
        info_dict['unit'] = variable_info[3]
        
        result['variableInfo'] = info_dict
        result['variableValue'] = value_dict
        return result
    
    # 获取仿真结果数据，返回指定格式的JSON（包含时间、速度、高度）
    def get_simulation_results(self, variable_paths_dict):
        """
        获取多个变量的仿真结果，使用任一变量的时间点作为时间轴。
        :param variable_paths_dict: 字典，如 {"speed": "qout@pump01", "height": "h@tank01"}
        :return: 列表，每个元素为 { "时间(s)": t, "speed": v1, "height": v2, ... }
        """
        # 获取所有变量的数据
        var_data_dict = {}
        for name, path in variable_paths_dict.items():
            raw_data = dict(AMEGetVariableValues(path))
            var_data_dict[name] = raw_data

        # 任选一个变量的时间点作为全局时间轴（假设所有变量时间一致）
        first_var_data = next(iter(var_data_dict.values()))
        time_points = sorted(first_var_data.keys())

        # 构建结果列表
        result_list = []
        for t in time_points:
            entry = {}
            entry["时间(s)"] = round(float(t), 3)
            for name in variable_paths_dict:
                value = var_data_dict[name].get(t, 0)
                entry[name] = round(float(value), 3)
            result_list.append(entry)
            # print("entry keys order:", list(entry.keys()))
        # print(result_list)
        return result_list

# 创建服务处理器实例
handler = AmeSimuSessionServiceHandler()

# ==================== API路由定义 ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'ok',
        'message': 'AMESim Server is running'
    })

@app.route('/api/init', methods=['POST'])
def init_api():
    """初始化AMESim API"""
    try:
        handler.init_api()
        return jsonify({
            'success': True,
            'message': 'API initialized successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/model/open', methods=['POST'])
def open_model():
    """打开模型文件"""
    try:
        data = request.get_json()
        if not data or 'filePath' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing filePath parameter'
            }), 400
        
        file_path = data['filePath']
        handler.open_ame_file(file_path)
        return jsonify({
            'success': True,
            'message': f'Model opened: {file_path}'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/model/close', methods=['POST'])
def close_model():
    """关闭模型"""
    try:
        handler.close_circuit()
        return jsonify({
            'success': True,
            'message': 'Model closed successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/model/parameters', methods=['GET'])
def get_parameters():
    """获取所有模型参数"""
    try:
        parameters = handler.get_model_all_parameter()
        return jsonify({
            'success': True,
            'data': parameters
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/model/parameters/run', methods=['PUT'])
def set_run_parameter():
    """设置运行参数"""
    try:
        data = request.get_json()
        if not data or 'parameter' not in data or 'value' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing parameter or value'
            }), 400
        
        handler.set_run_parameter(data['parameter'], data['value'])
        return jsonify({
            'success': True,
            'message': 'Run parameter set successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/model/parameters/global', methods=['PUT'])
def set_global_parameter():
    """设置全局参数"""
    try:
        data = request.get_json()
        if not data or 'parameter' not in data or 'value' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing parameter or value'
            }), 400
        
        handler.set_global_parameter(data['parameter'], data['value'])
        return jsonify({
            'success': True,
            'message': 'Global parameter set successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/model/parameters/component', methods=['PUT'])
def set_comp_parameter():
    """设置部件参数"""
    try:
        data = request.get_json()
        if not data or 'parameter' not in data or 'value' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing parameter or value'
            }), 400
        
        handler.set_comp_parameter(data['parameter'], data['value'])
        return jsonify({
            'success': True,
            'message': 'Component parameter set successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/simulation/run', methods=['POST'])
def run_simulation():
    """运行仿真"""
    try:
        print("in run simulation")
        handler.run_simulation()
        return jsonify({
            'success': True,
            'message': 'Simulation completed successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/simulation/variable', methods=['GET'])
def get_variable():
    """获取指定变量的结果"""
    try:
        variable_path = request.args.get('path')
        if not variable_path:
            return jsonify({
                'success': False,
                'error': 'Missing path parameter'
            }), 400
        
        result = handler.get_variable_values(variable_path)
        return jsonify({
            'success': True,
            'data': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/simulation/results', methods=['POST'])
def get_simulation_results():
    """获取仿真结果：使用任一变量的时间点作为时间轴"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body must be JSON'}), 400

        variables = data.get('variables')
        if not isinstance(variables, dict) or not variables:
            return jsonify({'success': False, 'error': 'variables must be a non-empty object'}), 400

        results = handler.get_simulation_results(variables)
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/close', methods=['POST'])
def close_api():
    """关闭AMESim API"""
    try:
        handler.close_api()
        return jsonify({
            'success': True,
            'message': 'API closed successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# 错误处理
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500

if __name__ == '__main__':
    print("Starting AMESim Flask Server...")
    print("Server will be available at http://0.0.0.0:5003")
    app.run(host='0.0.0.0', port=5003, debug=False,threaded = False)
    # 测试API功能
    
    # print("Init API done:",AMEInitAPI())
    
    # print("open model done:",AMEOpenAmeFile("D:/files/Riselab_WANG_Hongxuan/Project_503/Amesim_simulation/AMESim_Server-main/model/test.ame"))

    # print("Run simulation done:",AMERunSimulation())

    # print("Get time variable:",AMEGetVariableValues("qout@pump01"))

    # AMECloseCircuit(False)

    # AMECloseAPI()



