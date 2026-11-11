"""AMESim 服务的 Python 客户端示例。

服务所有接口都需要登录令牌：先用账号密码向任务服务（默认 5001 端口）换取令牌，
再在请求头 X-Token 中携带。
"""
import json

import requests


def login(task_service_url: str, username: str, password: str) -> str:
    resp = requests.post(f"{task_service_url}/auth/login", json={"username": username, "password": password})
    resp.raise_for_status()
    return resp.json()["token"]


class AMESimClient:
    def __init__(self, token: str, base_url: str = "http://127.0.0.1:5003"):
        self.base_url = base_url
        self.api = f"{base_url}/api"
        self.session = requests.Session()
        self.session.headers["X-Token"] = token

    def _call(self, method: str, endpoint: str, **kwargs):
        url = endpoint if endpoint.startswith("http") else f"{self.api}{endpoint}"
        resp = self.session.request(method, url, **kwargs)
        body = resp.json()
        if resp.status_code >= 400:
            raise RuntimeError(body.get("error", resp.text))
        return body

    def health_check(self):
        return self._call("GET", f"{self.base_url}/health")

    def init_api(self):
        return self._call("POST", "/init")

    def open_model(self, file_name: str):
        """file_name 为模型目录（AMESIM_MODEL_DIR）下的 .ame 文件名。"""
        return self._call("POST", "/model/open", json={"filePath": file_name})

    def close_model(self):
        return self._call("POST", "/model/close")

    def get_parameters(self):
        return self._call("GET", "/model/parameters")

    def set_run_parameter(self, parameter, value):
        return self._call("PUT", "/model/parameters/run", json={"parameter": parameter, "value": value})

    def set_global_parameter(self, parameter, value):
        return self._call("PUT", "/model/parameters/global", json={"parameter": parameter, "value": value})

    def set_comp_parameter(self, parameter, value):
        return self._call("PUT", "/model/parameters/component", json={"parameter": parameter, "value": value})

    def run_simulation(self):
        return self._call("POST", "/simulation/run")

    def get_variable(self, variable_path):
        return self._call("GET", "/simulation/variable", params={"path": variable_path})

    def get_simulation_results(self, variables: dict):
        """variables 形如 {"speed": "pin@pump01", "flow": "qout@pump01"}。"""
        return self._call("POST", "/simulation/results", json={"variables": variables})

    def close_api(self):
        return self._call("POST", "/close")


if __name__ == "__main__":
    token = login("http://127.0.0.1:5001", "admin", "<你的密码>")
    client = AMESimClient(token)
    client.init_api()
    client.open_model("test.ame")
    client.set_run_parameter("stop_time_s", "1")
    client.run_simulation()
    result = client.get_simulation_results({"speed": "pin@pump01", "flow": "qout@pump01"})
    print(json.dumps(result, indent=2, ensure_ascii=False))
    client.close_model()
    client.close_api()
