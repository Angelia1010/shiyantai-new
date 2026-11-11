# AMESim 仿真服务

把 Simcenter Amesim 2021.1 的 Python API（`ame_apy`）封装成 HTTP 接口，供平台的“自动诊断”流程设置参数、运行仿真并读取结果。

- 默认地址 `http://127.0.0.1:5003`，前端经代理以 `/api/amesim` 访问；
- 所有接口（`/health` 除外）都要求请求头 `X-Token` 携带登录令牌，令牌由任务服务 `POST /auth/login` 签发；
- 模型文件（`.ame`）和仿真数据文件（`.data`）只能放在模型目录 `AMESIM_MODEL_DIR`（默认 `AMESim_server/model/`）中，接口只接受纯文件名；
- AMESim API 不是线程安全的，服务单线程运行，请求依次执行。多人同时使用会共用同一个已打开的模型。

## 启动

1. 设置环境变量 `AME` 指向 AMESim 安装目录；
2. 在仓库根目录准备好 `.env`（参考 `.env.example`）；
3. 双击 `startAmeServer.bat`，或在仓库根目录执行：

```bat
"%AME%\sys\python\win64\python.exe" -m pip install -r AMESim_server\requirements.txt
"%AME%\sys\python\win64\python.exe" -m AMESim_server.src.AmeSimuSessionServer
```

如果 `ame_apy` 导入失败，服务会直接退出并在日志里说明原因。

## 接口

成功响应为 `{"success": true, ...}`，失败响应为 `{"error": "原因"}` 加相应的 HTTP 状态码。

| 方法 | 路径 | 请求 | 说明 |
| --- | --- | --- | --- |
| GET | `/health` | — | 健康检查，无需令牌 |
| POST | `/api/init` | — | 初始化 AMESim API |
| POST | `/api/close` | — | 关闭 AMESim API |
| POST | `/api/model/open` | `{"filePath": "pump.ame"}` | 打开模型目录下的模型 |
| POST | `/api/model/close` | — | 关闭模型（不保存） |
| GET | `/api/model/parameters` | — | 运行参数、全局参数、部件参数 |
| PUT | `/api/model/parameters/run` | `{"parameter", "value"}` | 设置运行参数，如 `stop_time_s` |
| PUT | `/api/model/parameters/global` | `{"parameter", "value"}` | 设置全局参数 |
| PUT | `/api/model/parameters/component` | `{"parameter", "value"}` | 设置部件参数，如 `speed@pmover01` |
| POST | `/api/simulation/run` | — | 运行仿真（同步，跑完才返回） |
| GET | `/api/simulation/variable?path=` | — | 单个变量的信息和取值 |
| POST | `/api/simulation/results` | `{"variables": {"别名": "变量路径"}}` | 以第一个变量的时间点为轴的结果表，缺失值为 `null` |
| GET | `/api/simulation/data-file?fileName=` | — | 读取模型目录下的 `.data` 文件内容 |
| POST | `/api/simulation/input-data` | `{"data": [y1, y2, ...]}` | 把数值写成一维表格 `input.data`（X 从 0.1 起，步长 0.1） |

## 客户端示例

Python（`src/client.py`）：

```python
from AMESim_server.src.client import AMESimClient, login

token = login("http://127.0.0.1:5001", "admin", "你的密码")
client = AMESimClient(token)
client.init_api()
client.open_model("pump.ame")
client.run_simulation()
print(client.get_simulation_results({"speed": "pin@pump01", "flow": "qout@pump01"}))
```

Java（`src/java/AMESimClient.java`，Java 8+，依赖 Gson）：

```java
AMESimClient client = new AMESimClient("http://127.0.0.1:5003", token);
client.initAPI();
client.openModel("pump.ame");
client.runSimulation();
Map<String, String> vars = new LinkedHashMap<>();
vars.put("speed", "pin@pump01");
JsonObject result = client.getSimulationResults(vars);
```
