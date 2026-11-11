# 503 标准试验台数字化校验系统

燃油泵标准试验台的数据监控与故障诊断平台：实时监控试验台导出的数据文件，计算特征并在三维/二维模型上展示，结合 AMESim 仿真做初步诊断，再用流量计模型做精确诊断，生成 Word 诊断报告；另提供基于本地大模型的数据分析与问答。

## 架构

```
浏览器 ── digital-twin-platform（Vue 2 + Element UI）
   │  /api/task   ──►  任务服务     pump_test_bench/app/services/task_service.py   :5001  登录、任务、诊断、报告
   │  /api/file   ──►  文件服务     pump_test_bench/app/services/file_service.py   :5002  列文件、分页读取、目录监控
   │  /api/ai     ──►  大模型服务   pump_test_bench/app/services/llm_service.py    :8999  数据分析与问答 ──► Ollama
   └  /api/amesim ──►  AMESim 服务  AMESim_server/src/AmeSimuSessionServer.py      :5003  仿真（AMESim 自带 Python）
```

- 开发时由 `vue.config.js` 的代理转发 `/api/*`，生产环境由 Nginx 转发（`deploy/nginx.conf`）。
- 所有后端默认只监听 `127.0.0.1`；除 `/health` 与登录接口外都要求请求头 `X-Token`。令牌由任务服务签发，各服务用同一个 `SECRET_KEY` 校验。
- 前端提交的数据目录必须位于 `DATA_ROOTS` 配置的目录内，文件名不能带路径。

### 自动诊断流程

“自动诊断”页面按文件依次执行（逻辑在 `views/autoDiagnosis/pipeline.js`）：

1. 实时模式下轮询文件服务的目录事件（文件写完 2 秒后才发布事件），新文件进入队列；文件模式下处理选中的文件。
2. 创建任务，分页读取文件，每 `groupSize` 行聚合成一帧特征（max/min/avg），通过 BroadcastChannel 推送给工作台播放。
3. 开启仿真时：用试验数据设置 AMESim 参数、运行仿真、读回仿真结果。
4. 有仿真数据时做初步诊断（各变量均值偏差超阈值的个数超过限值即异常，异常时后端接着做精确诊断）；否则直接做流量计精确诊断。
5. 报告存入 SQLite，可在“任务列表”查看和下载 Word 版。

### 流量计精确诊断（`pump_test_bench/app/core/flow_meter.py`）

| 回路 | 质量流量列（kg/h） | 实测流量列（L/h） |
| --- | --- | --- |
| 回路1流量计 | 回油质量流量1 | 回油流量1-1 |
| 回路2流量计 | 回油质量流量2 | 回油流量1-2 |

X1 = 质量流量均值 / 3600（kg/s），X2 = 介质密度；仿真转速 Y = 2696.17 + 15468.63·X1 − 3.42·X2（rad/s）；
频率 f = 6·Y/(2π)（6 片涡轮叶片）；理论流量 q = 0.304921·f + 0.210230（L/h）；与实测均值相对偏差 > 15% 判为异常。

## 快速开始（Windows）

1. **配置**：复制 `.env.example` 为 `.env`，至少填写 `SECRET_KEY`、`ADMIN_PASSWORD`，并把 `DATA_ROOTS` 设为试验数据所在目录。
2. **后端**：
   ```powershell
   conda env create -f pump_test_bench/environment.yml   # 首次
   powershell -ExecutionPolicy Bypass -File pump_test_bench/start_project.ps1
   ```
   也可以在仓库根目录分别运行 `python -m pump_test_bench.app.services.task_service`（以及 `file_service`、`llm_service`）。
3. **AMESim 服务**（需要仿真时）：设置环境变量 `AME`，运行 `AMESim_server/startAmeServer.bat`，模型文件放在 `AMESim_server/model/`。
4. **大模型**（需要智能助手时）：按 `DeepSeek-model/README.md` 部署 Ollama。
5. **前端**：
   ```bash
   cd digital-twin-platform
   npm ci
   npm run dev          # 开发，http://localhost:9528
   npm run build:prod   # 生产构建，配合 deploy/nginx.conf
   ```
   工作台的三维模型文件（`public/model/*.glb` 等）体积较大，没有放进仓库，请从共享盘拷贝到 `digital-twin-platform/public/model/`。

## 目录

```
shared/                     各后端服务共用：配置、鉴权、路径校验、日志、Flask 应用工厂
pump_test_bench/
  app/core/                 数据读取、流量计诊断、初步诊断、报告生成
  app/db/tasks.py           任务存储（SQLite，自动迁移旧版 fault_diagnosis_tasks_2 表）
  app/llm/                  大模型客户端、会话存储、窗口分析
  app/services/             三个 HTTP 服务
  samples/                  样例数据（测试也用它）
  tests/                    后端测试
AMESim_server/              AMESim 仿真服务与 Python/Java 客户端示例
DeepSeek-model/             本地大模型部署说明与可选的独立推理接口
digital-twin-platform/      前端
deploy/nginx.conf           生产部署示例
```

## 测试

```bash
pip install -r pump_test_bench/requirements.txt
python -m pytest            # 在仓库根目录运行，覆盖后端核心逻辑与接口（AMESim 用假模块测试）
cd digital-twin-platform && npm run lint && npm run test:unit
```
