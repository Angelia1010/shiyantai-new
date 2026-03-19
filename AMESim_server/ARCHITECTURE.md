# AMESim Server 项目架构说明文档

## 1. 项目概述

### 1.1 项目简介
AMESim Server 是一个基于 Simcenter Amesim 2021.1 API 的二次开发项目，通过 Flask REST API 将 AMESim 的接口函数封装为 HTTP 服务，使得任何支持 HTTP 请求的语言（Python、Java、JavaScript 等）都可以轻松调用 AMESim 的仿真功能。

### 1.2 主要功能
- **模型管理**：打开、关闭 AMESim 模型文件
- **参数管理**：读取和设置模型的运行参数、全局参数、部件参数
- **仿真控制**：运行仿真实验
- **结果获取**：获取仿真变量的结果数据，支持自定义格式输出

### 1.3 技术栈
- **开发语言**：Python
- **Web框架**：Flask 2.3.3
- **跨域支持**：Flask-CORS 4.0.0
- **仿真平台**：Simcenter Amesim 2021.1
- **通信协议**：HTTP/HTTPS (端口 5000)
- **数据格式**：JSON

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        客户端应用层                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │  Python  │  │   Java  │  │    JS    │  │  其他语言 │     │
│  │  客户端   │  │  客户端   │  │  前端    │  │  客户端   │     │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘     │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP/HTTPS REST API
                           │ (JSON格式)
┌──────────────────────────▼──────────────────────────────────┐
│                    Flask Web服务层                            │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Flask Application                                      │  │
│  │  - RESTful API路由                                      │  │
│  │  - 请求/响应处理                                        │  │
│  │  - CORS跨域支持                                         │  │
│  │  - 错误处理                                             │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    业务逻辑处理层                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  AmeSimuSessionServiceHandler                           │  │
│  │  - 模型管理方法                                         │  │
│  │  - 参数管理方法                                         │  │
│  │  - 仿真控制方法                                         │  │
│  │  - 结果获取方法                                         │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    AMESim API 封装层                          │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  ame_apy (AMESim Python API)                           │  │
│  │  - AMEInitAPI()                                         │  │
│  │  - AMEOpenAmeFile()                                     │  │
│  │  - AMERunSimulation()                                  │  │
│  │  - AMEGetVariableValues()                              │  │
│  │  - ...                                                  │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    Simcenter Amesim 引擎                      │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  模型文件 (.ame)                                        │  │
│  │  仿真引擎                                               │  │
│  │  结果数据                                               │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 架构层次说明

1. **客户端应用层**
   - 支持多种语言：Python、Java、JavaScript等
   - 通过HTTP请求调用REST API
   - 处理返回的JSON数据

2. **Flask Web服务层**
   - 提供RESTful API接口
   - 处理HTTP请求和响应
   - 支持CORS跨域访问
   - 统一的错误处理机制

3. **业务逻辑处理层**
   - 实现具体的业务逻辑
   - 调用AMESim API
   - 数据格式转换（JSON）

4. **AMESim API 封装层**
   - 封装AMESim的原生API
   - 提供统一的接口调用方式

5. **Simcenter Amesim 引擎**
   - 执行实际的仿真计算
   - 管理模型文件和结果数据

---

## 3. 项目目录结构

```
AMESim_Server-main/
│
├── src/                          # 源代码目录
│   ├── AmeSimuSessionServer.py   # Flask服务器主程序（核心业务逻辑）
│   ├── client.py                 # Python客户端示例代码
│   └── java/                     # Java客户端代码
│       ├── AMESimClient.java     # Java客户端实现
│       └── pom.xml               # Maven配置文件
│
├── model/                        # 模型文件目录
│   └── Model.ame                 # AMESim 模型文件
│
├── docs/                         # 文档目录
│   └── Java使用指南.md           # Java客户端使用指南
│
├── requirements.txt              # Python依赖包列表
├── startAmeServer.bat            # 服务器启动脚本（Windows）
├── README.md                     # 项目说明文档
├── ARCHITECTURE.md               # 架构说明文档（本文档）
└── LICENSE                       # 许可证文件
```

---

## 4. 核心模块说明

### 4.1 服务器主程序模块 (`AmeSimuSessionServer.py`)

**功能**：实现 AMESim 服务的核心业务逻辑和 REST API

**主要组件**：

#### 4.1.1 环境初始化 (`StartUp()`)
- **功能**：配置 AMESim Python API 的运行环境
- **主要操作**：
  - 添加 AMESim Python 模块路径到 `sys.path`
  - 配置 DLL 路径
  - 设置 QT 插件路径
  - 禁用用户站点

#### 4.1.2 Flask应用初始化
- 创建Flask应用实例
- 启用CORS跨域支持
- 配置路由和错误处理

#### 4.1.3 服务处理器类 (`AmeSimuSessionServiceHandler`)

**API 生命周期管理方法**：
- `init_api()`：初始化 AMESim API
- `open_ame_file(ame_file_path)`：打开模型文件
  - 支持相对路径，自动从 `model/` 目录查找
- `close_circuit()`：关闭当前打开的模型（不保存）
- `close_api()`：关闭 AMESim API

**参数管理方法**：
- `get_model_all_parameter()`：获取所有模型参数
  - 返回字典格式，包含：
    - `runParameter`：运行参数（停止时间、时间间隔等）
    - `globalParameter`：全局参数
    - `compParameter`：部件参数
- `set_run_parameter(path_of_parameter, value_of_parameter)`：设置运行参数
- `set_global_parameter(path_of_parameter, value_of_parameter)`：设置全局参数
- `set_comp_parameter(path_of_parameter, value_of_parameter)`：设置部件参数

**仿真控制方法**：
- `run_simulation()`：运行仿真实验

**结果获取方法**：
- `get_variable_values(path_of_variable)`：获取指定变量的结果数据
  - 返回字典格式，包含变量信息和数值
- `get_simulation_results(time_variable_path, speed_variable_path, height_variable_path)`：获取仿真结果
  - 返回列表格式
  - 每个元素包含：`{"时间(s)": 值, "速度(m/s)": 值, "高度(m)": 值}`

#### 4.1.4 REST API路由

**基础接口**：
- `GET /api/health`：健康检查
- `POST /api/init`：初始化API
- `POST /api/close`：关闭API

**模型管理**：
- `POST /api/model/open`：打开模型文件
- `POST /api/model/close`：关闭模型

**参数管理**：
- `GET /api/model/parameters`：获取所有参数
- `PUT /api/model/parameters/run`：设置运行参数
- `PUT /api/model/parameters/global`：设置全局参数
- `PUT /api/model/parameters/component`：设置部件参数

**仿真控制**：
- `POST /api/simulation/run`：运行仿真

**结果获取**：
- `GET /api/simulation/variable`：获取变量值
- `GET /api/simulation/results`：获取仿真结果

#### 4.1.5 错误处理
- 统一的错误响应格式
- 404错误处理
- 500错误处理

---

### 4.2 Python客户端模块 (`src/client.py`)

**功能**：提供Python客户端封装类

**主要功能**：
- `AMESimClient`类：封装所有API调用
- 使用`requests`库发送HTTP请求
- 自动处理JSON序列化/反序列化
- 提供完整的使用示例

**使用示例**：
```python
client = AMESimClient('http://localhost:5000')
client.init_api()
client.open_model('Model.ame')
client.run_simulation()
result = client.get_simulation_results(time_path, speed_path, height_path)
```

---

### 4.3 Java客户端模块 (`src/java_client_example.java`)

**功能**：提供Java客户端示例代码

**主要功能**：
- 使用`HttpURLConnection`发送HTTP请求
- 使用`Gson`库处理JSON数据
- 封装所有API方法
- 提供完整的使用示例

**依赖**：
- Gson库（用于JSON处理）

**使用示例**：
```java
AMESimClient client = new AMESimClient("http://localhost:5000");
client.initAPI();
client.openModel("Model.ame");
client.runSimulation();
JsonObject result = client.getSimulationResults(timePath, speedPath, heightPath);
```

---

### 4.4 启动脚本模块 (`startAmeServer.bat`)

**功能**：Windows 环境下的服务器启动脚本

**主要功能**：
1. 检查 `AME` 环境变量是否设置
2. 检查并安装Flask依赖
3. 使用 AMESim 自带的 Python 解释器运行服务器
4. 确保使用正确的 Python 环境（包含 AMESim API）

**使用方式**：
```batch
# 确保已设置 AME 环境变量
set AME=C:\Program Files\Simcenter\Amesim\2021.1

# 运行启动脚本
startAmeServer.bat
```

---

## 5. API接口设计

### 5.1 RESTful设计原则

- **资源导向**：使用名词表示资源（如 `/api/model`, `/api/simulation`）
- **HTTP方法**：使用标准HTTP方法（GET、POST、PUT、DELETE）
- **状态码**：使用标准HTTP状态码（200、400、500等）
- **统一响应格式**：所有接口返回统一的JSON格式

### 5.2 接口分类

#### 5.2.1 基础接口
- 健康检查、初始化、关闭

#### 5.2.2 模型管理接口
- 打开模型、关闭模型

#### 5.2.3 参数管理接口
- 获取参数、设置运行参数、设置全局参数、设置部件参数

#### 5.2.4 仿真控制接口
- 运行仿真

#### 5.2.5 结果获取接口
- 获取变量值、获取仿真结果

### 5.3 数据流说明

```
客户端请求 (HTTP)
    │
    ├─> Flask路由处理
    │
    ├─> 业务逻辑处理 (AmeSimuSessionServiceHandler)
    │
    ├─> 调用 AMESim API
    │
    ├─> AMESim 执行仿真
    │
    ├─> 获取结果数据
    │
    ├─> 格式化为 JSON
    │
    └─> HTTP响应返回客户端
```

### 5.4 数据格式示例

#### 5.4.1 仿真结果 JSON 格式
```json
{
    "success": true,
    "data": [
        {
            "时间(s)": 0.0,
            "速度(m/s)": 0.0,
            "高度(m)": 0.0
        },
        {
            "时间(s)": 0.1,
            "速度(m/s)": 1.2,
            "高度(m)": 0.5
        }
    ]
}
```

#### 5.4.2 变量结果 JSON 格式
```json
{
    "success": true,
    "data": {
        "variableInfo": {
            "path": "变量路径",
            "title": "变量标题",
            "unit": "变量单位"
        },
        "variableValue": {
            "0.0": 值1,
            "0.1": 值2
        }
    }
}
```

#### 5.4.3 模型参数 JSON 格式
```json
{
    "success": true,
    "data": {
        "runParameter": {
            "stop_time_s": 10.0,
            "interval_s": 0.01
        },
        "globalParameter": {
            "参数名1": "参数值1"
        },
        "compParameter": {
            "部件路径/参数名": "参数值"
        }
    }
}
```

#### 5.4.4 错误响应格式
```json
{
    "success": false,
    "error": "错误信息描述"
}
```

---

## 6. 部署和运行

### 6.1 环境要求
- **操作系统**：Windows（支持 AMESim 2021.1）
- **Python**：AMESim 自带的 Python 环境
- **环境变量**：需要设置 `AME` 环境变量指向 AMESim 安装目录
- **网络**：服务器监听 `0.0.0.0:5000`，确保端口未被占用
- **依赖包**：Flask、Flask-CORS（通过requirements.txt安装）

### 6.2 安装依赖
```bash
# 使用AMESim自带的Python环境
"%AME%\sys\python\win64\python.exe" -m pip install -r requirements.txt
```

### 6.3 启动服务器
```batch
# Windows
startAmeServer.bat

# 或直接使用 Python
"%AME%\sys\python\win64\python.exe" src/AmeSimuSessionServer.py
```

### 6.4 客户端连接

**Python客户端**：
```python
from src.client import AMESimClient
client = AMESimClient('http://服务器IP:5000')
```

**Java客户端**：
```java
AMESimClient client = new AMESimClient("http://服务器IP:5000");
```

**JavaScript客户端**：
```javascript
fetch('http://服务器IP:5000/api/health')
    .then(response => response.json())
    .then(data => console.log(data));
```

---

## 7. 扩展说明

### 7.1 添加新的API接口

1. **在Handler类中添加业务方法**
   ```python
   def new_method(self, param1, param2):
       # 实现业务逻辑
       return result
   ```

2. **添加Flask路由**
   ```python
   @app.route('/api/new-endpoint', methods=['POST'])
   def new_endpoint():
       try:
           data = request.get_json()
           result = handler.new_method(data['param1'], data['param2'])
           return jsonify({'success': True, 'data': result})
       except Exception as e:
           return jsonify({'success': False, 'error': str(e)}), 500
   ```

### 7.2 支持其他语言客户端

由于使用HTTP REST API，任何支持HTTP请求的语言都可以轻松调用：

- **C#/.NET**：使用`HttpClient`
- **Go**：使用`net/http`
- **Node.js**：使用`axios`或`fetch`
- **PHP**：使用`curl`或`Guzzle`
- **Ruby**：使用`Net::HTTP`

---

## 8. 优势对比（Flask vs Thrift）

### 8.1 Flask REST API的优势

1. **易于使用**：标准HTTP协议，无需学习Thrift语法
2. **跨语言支持**：任何支持HTTP的语言都可以调用
3. **调试方便**：可以直接使用浏览器或Postman测试
4. **前端集成**：前端页面可以直接调用，无需额外代理
5. **轻量级**：Flask框架轻量，启动快速
6. **标准化**：RESTful API是业界标准

### 8.2 适用场景

- ✅ Web前端直接调用
- ✅ 多语言客户端集成
- ✅ 快速原型开发
- ✅ 微服务架构
- ✅ API网关集成

---

## 9. 注意事项

1. **环境变量**：必须正确设置 `AME` 环境变量
2. **模型路径**：相对路径会自动从 `model/` 目录查找
3. **端口占用**：确保 5000 端口未被其他程序占用
4. **API调用顺序**：建议按照 `init → open → run → getResults → close` 的顺序调用
5. **错误处理**：客户端应妥善处理HTTP错误状态码和响应中的错误信息
6. **数据格式**：所有请求和响应均为JSON格式
7. **跨域请求**：已启用CORS，支持前端页面直接调用
8. **安全性**：生产环境建议添加认证和HTTPS支持

---

## 10. 总结

本项目通过 Flask REST API 将 AMESim 的本地 API 封装为 HTTP 服务，实现了：
- ✅ 标准化的 RESTful API 接口
- ✅ 跨语言的客户端支持
- ✅ 易于集成和调试
- ✅ 前端页面直接调用
- ✅ 轻量级和高效的架构

该架构具有良好的扩展性和兼容性，可以方便地添加新的接口和支持更多的客户端语言。
