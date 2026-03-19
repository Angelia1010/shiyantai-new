# client.py - Python客户端示例
import requests
import json

class AMESimClient:
    """AMESim服务客户端类"""
    
    def __init__(self, base_url='http://localhost:5003'):
        self.base_url = base_url
        self.api_base = f"{base_url}/api"
    
    def health_check(self):
        """健康检查"""
        response = requests.get(f"{self.api_base}/health")
        return response.json()
    
    def init_api(self):
        """初始化API"""
        response = requests.post(f"{self.api_base}/init")
        return response.json()
    
    def open_model(self, file_path):
        """打开模型文件"""
        data = {'filePath': file_path}
        response = requests.post(
            f"{self.api_base}/model/open",
            json=data,
            headers={'Content-Type': 'application/json'}
        )
        return response.json()
    
    def close_model(self):
        """关闭模型"""
        response = requests.post(f"{self.api_base}/model/close")
        return response.json()
    
    def get_parameters(self):
        """获取所有参数"""
        response = requests.get(f"{self.api_base}/model/parameters")
        return response.json()
    
    def set_run_parameter(self, parameter, value):
        """设置运行参数"""
        data = {'parameter': parameter, 'value': value}
        response = requests.put(
            f"{self.api_base}/model/parameters/run",
            json=data,
            headers={'Content-Type': 'application/json'}
        )
        return response.json()
    
    def set_global_parameter(self, parameter, value):
        """设置全局参数"""
        data = {'parameter': parameter, 'value': value}
        response = requests.put(
            f"{self.api_base}/model/parameters/global",
            json=data,
            headers={'Content-Type': 'application/json'}
        )
        return response.json()
    
    def set_comp_parameter(self, parameter, value):
        """设置部件参数"""
        data = {'parameter': parameter, 'value': value}
        response = requests.put(
            f"{self.api_base}/model/parameters/component",
            json=data,
            headers={'Content-Type': 'application/json'}
        )
        return response.json()
    
    def run_simulation(self):
        """运行仿真"""
        response = requests.post(f"{self.api_base}/simulation/run")
        return response.json()
    
    def get_variable(self, variable_path):
        """获取变量值"""
        params = {'path': variable_path}
        response = requests.get(f"{self.api_base}/simulation/variable", params=params)
        return response.json()
    
    def get_simulation_results(self, time_path, speed_path, height_path):
        """获取仿真结果"""
        params = {
            'timePath': time_path,
            'speedPath': speed_path,
            'heightPath': height_path
        }
        response = requests.get(f"{self.api_base}/simulation/results", params=params)
        return response.json()
    
    def close_api(self):
        """关闭API"""
        response = requests.post(f"{self.api_base}/close")
        return response.json()


# 使用示例
if __name__ == '__main__':
    # 创建客户端
    client = AMESimClient('http://localhost:5003')
    
    try:
        # 健康检查
        print("健康检查:", client.health_check())
        
        # 初始化API
        print("初始化API:", client.init_api())
        
        # 打开模型
        print("打开模型:", client.open_model('test.ame'))

        # 设置仿真结束时间
        print("设置仿真结束时间:",client.set_run_parameter('stop_time_s',"1"))
        
        # 运行仿真
        print("运行仿真:", client.run_simulation())
        
        # 获取仿真结果（需要替换为实际的变量路径）
        time_path = "ame_simulation_time"  # 替换为实际的时间变量路径
        speed_path = "pin@pump01"  # 替换为实际的速度变量路径
        height_path = "qout@pump01"  # 替换为实际的高度变量路径
        
        result = client.get_simulation_results(time_path, speed_path, height_path)
        print("仿真结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # 关闭模型
        print("关闭模型:", client.close_model())
        
        # 关闭API
        print("关闭API:", client.close_api())
        
    except Exception as e:
        print(f"错误: {e}")
