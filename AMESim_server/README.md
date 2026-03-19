# AMESim Server

## 项目简介

本项目使用 AMESim 2021.1 版本 API 进行二次开发，通过 Flask REST API 将 AMESim 的接口函数封装为 HTTP 服务，使得任何支持 HTTP 请求的语言（Python、Java、JavaScript 等）都可以轻松调用 AMESim 的仿真功能。

## 主要功能

- ✅ **模型管理**：打开、关闭 AMESim 模型文件
- ✅ **参数管理**：读取和设置模型的运行参数、全局参数、部件参数
- ✅ **仿真控制**：运行仿真实验
- ✅ **结果获取**：获取仿真变量的结果数据，支持自定义格式输出（JSON）
- ✅ **RESTful API**：标准的 HTTP REST 接口，易于集成
- ✅ **跨域支持**：支持前端页面直接调用

## 技术栈

- **开发语言**：Python
- **Web框架**：Flask 2.3.3
- **仿真平台**：Simcenter Amesim 2021.1
- **通信协议**：HTTP/HTTPS (端口 5003)
- **数据格式**：JSON
- **跨域支持**：Flask-CORS

## 快速开始

### 环境要求

- Windows 操作系统
- Simcenter Amesim 2021.1
- 设置 `AME` 环境变量指向 AMESim 安装目录

### 安装依赖

```bash
# 使用AMESim自带的Python环境安装Flask
cmd:"%AME%\sys\python\win64\python.exe" -m pip install -r requirements.txt
powershell:"$env:AME\sys\python\win64\python.exe" -m pip install -r requirements.txt
```

### 启动服务器

```batch
# Windows
startAmeServer.bat
```

服务器将在 `http://0.0.0.0:5003` 启动

### Python客户端调用示例

```python
from src.client import AMESimClient
import json

# 创建客户端
client = AMESimClient('http://localhost:5003')

# 初始化API
client.init_api()

# 打开模型
client.open_model('Model.ame')

# 运行仿真
client.run_simulation()

# 获取仿真结果
result = client.get_simulation_results(
    timeVariablePath='time',
    speedVariablePath='speed',
    heightVariablePath='height'
)

print(json.dumps(result, indent=2, ensure_ascii=False))
```

### Java客户端调用示例

```java
import com.amesim.client.AMESimClient;
import com.google.gson.JsonObject;

// 创建客户端
AMESimClient client = new AMESimClient("http://localhost:5003");

// 初始化API
client.initAPI();

// 打开模型
client.openModel("Model.ame");

// 运行仿真
client.runSimulation();

// 获取仿真结果
JsonObject result = client.getSimulationResults(
    "time",    // 时间变量路径
    "speed",   // 速度变量路径
    "height"   // 高度变量路径
);

System.out.println(result);
```

### JavaScript/前端调用示例

```javascript
// 使用fetch API
async function runSimulation() {
    // 初始化API
    await fetch('http://localhost:5003/api/init', {
        method: 'POST'
    });
    
    // 打开模型
    await fetch('http://localhost:5003/api/model/open', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            filePath: 'Model.ame'
        })
    });
    
    // 运行仿真
    await fetch('http://localhost:5003/api/simulation/run', {
        method: 'POST'
    });
    
    // 获取仿真结果
    const response = await fetch(
        'http://localhost:5003/api/simulation/results?' +
        'timePath=time&speedPath=speed&heightPath=height'
    );
    const result = await response.json();
    console.log(result);
}
```

## API接口文档

### 基础接口

#### 健康检查
```
GET /api/health
```

#### 初始化API
```
POST /api/init
```

#### 关闭API
```
POST /api/close
```

### 模型管理

#### 打开模型
```
POST /api/model/open
Content-Type: application/json

{
    "filePath": "Model.ame"
}
```

#### 关闭模型
```
POST /api/model/close
```

### 参数管理

#### 获取所有参数
```
GET /api/model/parameters
```

#### 设置运行参数
```
PUT /api/model/parameters/run
Content-Type: application/json

{
    "parameter": "stop_time_s",
    "value": "10.0"
}
```

#### 设置全局参数
```
PUT /api/model/parameters/global
Content-Type: application/json

{
    "parameter": "参数名",
    "value": "参数值"
}
```

#### 设置部件参数
```
PUT /api/model/parameters/component
Content-Type: application/json

{
    "parameter": "部件路径/参数名",
    "value": "参数值"
}
```

### 仿真控制

#### 运行仿真
```
POST /api/simulation/run
```

### 结果获取

#### 获取变量值
```
GET /api/simulation/variable?path=变量路径
```

#### 获取仿真结果（时间、速度、高度）
```
GET /api/simulation/results?timePath=时间路径&speedPath=速度路径&heightPath=高度路径
```

**返回格式**：
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

## 项目结构

```
AMESim_Server-main/
├── src/                          # 源代码目录
│   ├── AmeSimuSessionServer.py   # Flask服务器主程序
│   ├── client.py                 # Python客户端示例
│   └── java/                     # Java客户端代码
│       ├── AMESimClient.java     # Java客户端实现
│       └── pom.xml               # Maven配置文件
├── model/                        # 模型文件目录
│   └── Model.ame                 # AMESim模型文件
├── docs/                         # 文档目录
│   └── Java使用指南.md           # Java客户端使用指南
├── requirements.txt             # Python依赖包
├── startAmeServer.bat            # 启动脚本
├── README.md                     # 项目说明文档
├── ARCHITECTURE.md               # 架构说明文档
└── LICENSE                       # 许可证文件
```

## 响应格式

所有API接口统一返回JSON格式：

**成功响应**：
```json
{
    "success": true,
    "message": "操作成功",
    "data": { ... }  // 可选，包含返回数据
}
```

**错误响应**：
```json
{
    "success": false,
    "error": "错误信息"
}
```

## 文档

- **[架构说明文档](ARCHITECTURE.md)**：详细的系统架构、模块说明和设计文档

## 注意事项

1. **环境变量**：必须正确设置 `AME` 环境变量
2. **模型路径**：相对路径会自动从 `model/` 目录查找
3. **端口占用**：确保 5003 端口未被其他程序占用
4. **API调用顺序**：建议按照 `init → open → run → getResults → close` 的顺序调用
5. **跨域请求**：已启用CORS，支持前端页面直接调用
6. **错误处理**：所有接口都有统一的错误处理机制

## 许可证

详见 [LICENSE](LICENSE) 文件
