# 503 标准试验台数字化校验系统

燃油泵标准试验台的数据监控与故障诊断平台：实时监控试验台导出的数据文件，计算特征并在三维/二维模型上展示，结合 AMESim 仿真做初步诊断，再用流量计模型做精确诊断，生成 Word 诊断报告；另提供基于本地大模型的数据分析与问答。

## 架构

```
浏览器 ── digital-twin-platform（Vue 2 + Element UI）
   │  /api/task   ──►  任务服务     pump_test_bench/app/services/task_service.py   :5001  登录、任务、诊断、报告
   │  /api/file   ──►  文件服务     pump_test_bench/app/services/file_service.py   :5002  列文件、分页读取、实时监控
   │  /api/ai     ──►  大模型服务   pump_test_bench/app/services/llm_service.py    :8999  数据分析与问答 ──► Ollama
   └  /api/amesim ──►  AMESim 服务  AMESim_server/src/AmeSimuSessionServer.py      :5003  仿真（AMESim 自带 Python）
```

- 开发时由 `vue.config.js` 的代理转发 `/api/*`，生产环境由 Nginx 转发（`deploy/nginx.conf`）。
- 所有后端默认只监听 `127.0.0.1`；除 `/health` 与登录接口外都要求请求头 `X-Token`。令牌由任务服务签发，各服务用同一个 `SECRET_KEY` 校验。
- 数据目录在前端填写（工作台“数据目录”、自动诊断配置页），后端校验后登记到 `pump_test_bench/data/data_dirs.json`，
  所有服务共用；`.env` 的 `DATA_ROOTS` 只是可选的预置目录。接口只能访问预置或登记过的目录，
  登记时要求目录存在且不是磁盘根目录或系统目录；文件名可以带子目录，但不能跳出该目录。

### 实时监控（`pump_test_bench/app/core/live_monitor.py`）

试验台通过文件共享把数据写到一个目录，系统这样对接：

1. 在工作台右上角“数据目录”里填写该目录的完整路径（也可在“自动诊断”实时模式中填写），
   目录会自动登记并保存到 `pump_test_bench/data/live_monitor.json`，文件服务重启后自动恢复。
2. 文件服务每 `LIVE_SCAN_SECONDS` 秒扫描一次目录（含子目录）。用定时扫描而不用文件系统通知，
   是因为网络共享（SMB）上的变化通知不可靠。
3. 正在变大的文件只读新增的完整行（没写完的半行留到下次），按时间列每 1 秒聚合成一帧（max/min/avg）。
4. 工作台每秒取一次新帧（`/live/frames`），延迟约 1–2 秒，与“自动诊断”页面是否打开无关，任何电脑都能看。
5. 文件停止变化 `LIVE_SETTLE_SECONDS` 秒后视为写完，发布“文件完成”事件，自动诊断据此处理整个文件。

没有试验台时可以用回放工具模拟“边测边写”：

```bash
# 然后在工作台“数据目录”里填写目标目录的完整路径
python -m pump_test_bench.tools.replay_data pump_test_bench/samples/标准台样例 --to 数据/实时 --speed 1 --loop
```

### 数据文件格式兼容（`pump_test_bench/app/core/table_parser.py`）

文本文件（.txt / .csv）不假设固定格式，逐项自动识别：

- 编码：UTF-8（含 BOM）、UTF-16、GBK/GB18030；分隔符：制表符、逗号、分号、竖线或连续空白；
- 表头：没有表头（试验台软件偶尔会把表头覆盖掉）时，先借用同目录中列数相同的文件的表头，
  再按列数匹配 `app/core/known_headers.py` 中的标准表头（试验台软件升级后列数/顺序有变化，在这里追加即可）；
- 任意位置的空行、行尾多余的分隔符、文件中途重复的表头行；
- 分隔符个数不足的行（没写完或被覆盖的残行）丢弃并计数，不影响其他行；
- 列名全角转半角，末尾括号里的单位单独记录（如“供油压力1-1(MPa)”）；
- 时间：`时:分:秒.毫秒`、`分:秒.毫秒`、不补零写法（`17:3:36.243`）、带日期前缀，跨午夜/整点自动接续。

### 自动诊断流程

“自动诊断”页面按文件依次执行（逻辑在 `views/autoDiagnosis/pipeline.js`）：

1. 实时模式下轮询文件服务的“文件完成”事件，写完的文件进入队列；文件模式下处理选中的文件（可选子目录中的文件）。
2. 创建任务，分页读取文件，每 `groupSize` 行聚合成一帧特征（max/min/avg）作为诊断输入。
3. 开启仿真时：用试验数据设置 AMESim 参数、运行仿真、读回仿真结果。
4. 有仿真数据时做初步诊断（各变量均值偏差超阈值的个数超过限值即异常，异常时后端接着做精确诊断）；否则直接做流量计精确诊断。
5. 报告存入 SQLite，可在“任务列表”查看和下载 Word 版；诊断状态和结果通过 BroadcastChannel 推送给同一浏览器中打开的工作台。

### 流量计精确诊断（`pump_test_bench/app/core/flow_meter.py`）

| 回路 | 质量流量列（kg/h） | 实测流量列（L/h） |
| --- | --- | --- |
| 回路1流量计 | 回油质量流量1 | 回油流量1-1 |
| 回路2流量计 | 回油质量流量2 | 回油流量1-2 |

X1 = 质量流量均值 / 3600（kg/s），X2 = 介质密度；仿真转速 Y = 2696.17 + 15468.63·X1 − 3.42·X2（rad/s）；
频率 f = 6·Y/(2π)（6 片涡轮叶片）；理论流量 q = 0.304921·f + 0.210230（L/h）；与实测均值相对偏差 > 15% 判为异常。

## 快速开始（Windows）

1. **配置**：复制 `.env.example` 为 `.env`，至少填写 `SECRET_KEY`、`ADMIN_PASSWORD`。数据目录在前端填写，不需要改 `.env`。
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
   新版 Node（17 及以上）需先设置 `$env:NODE_OPTIONS = "--openssl-legacy-provider"`。

## 目录

```
shared/                     各后端服务共用：配置、鉴权、路径校验、日志、Flask 应用工厂
pump_test_bench/
  app/core/                 数据解析与读取、实时监控、流量计诊断、初步诊断、报告生成
  app/db/tasks.py           任务存储（SQLite，自动迁移旧版 fault_diagnosis_tasks_2 表）
  app/llm/                  大模型客户端、会话存储、窗口分析
  app/services/             三个 HTTP 服务
  samples/                  样例数据（测试也用它）；标准台样例/ 为试验台实际导出格式（含无表头、末行未写完）
  tools/replay_data.py      回放工具：按真实速度把数据文件写入目录，模拟试验台
  tests/                    后端测试
AMESim_server/              AMESim 仿真服务与 Python/Java 客户端示例
DeepSeek-model/             本地大模型部署说明与可选的独立推理接口
digital-twin-platform/      前端
  src/views/dashboard/      工作台；三维场景在 scene/（部件、材质、视角配置见 scene/components.js）
  public/model/             试验台三维模型 shiyantai5.glb；public/*.hdr 为环境贴图
deploy/nginx.conf           生产部署示例
```

## 测试

```bash
pip install -r pump_test_bench/requirements.txt
python -m pytest            # 在仓库根目录运行，覆盖后端核心逻辑与接口（AMESim 用假模块测试）
cd digital-twin-platform && npm run lint && npm run test:unit
```
