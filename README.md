# 503 标准试验台数字化校验系统

燃油泵标准试验台的数据监控与故障诊断平台：实时监控试验台导出的数据文件，计算特征并在三维/二维模型上展示，用流量计互校、质量-体积校核与仿真模型（健康参考模型）对比做诊断并归纳原因，生成 Word 诊断报告；另提供基于本地大模型的数据分析与问答。

## 架构

```
浏览器 ── digital-twin-platform（Vue 2 + Element UI）
   │  /api/task   ──►  任务服务     pump_test_bench/app/services/task_service.py   :5001  登录、任务、诊断、报告、仿真模型
   │                        └─ 重建仿真基准表（AMESim 模型时）──►  AMESim 服务  AMESim_server/src/AmeSimuSessionServer.py  :5003
   │  /api/file   ──►  文件服务     pump_test_bench/app/services/file_service.py   :5002  列文件、分页读取、实时监控、自动诊断
   └  /api/ai     ──►  大模型服务   pump_test_bench/app/services/llm_service.py    :8999  数据分析与问答 ──► Ollama
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

### 诊断（`pump_test_bench/app/diagnosis/`）

**何时诊断**：实时监控时，数据文件写完后由文件服务在后台自动诊断（任务类型“自动诊断”，可在工作台“数据目录”
或“自动诊断”页开关）；也可以在“自动诊断”页选择文件批量诊断。

**怎么诊断**（`engine.py`）：

1. 识别稳定段：按 1 秒窗口找流量最平稳的最长一段（起停、换工况的过渡数据不参与判断）；
2. **冗余比对**（主判据）：同一路油上串联的多只流量计，每只与“其余各表的中位数”比较（留一法）；
   有健康基准时先扣除该表在当前流量、油温下的固有偏差。偏离大的就是嫌疑表；
3. **泄漏/分流**：比较“单表偏离”与“回油侧整体少一个比例”两种解释，后者更能解释数据、且同侧各表彼此一致时，
   判为供回油不平衡，而不是把同侧几只表都报成故障；
4. **质量-体积校核**：质量流量 ÷ 密度（按油温修正）与同侧体积流量比较，校核质量流量计。密度默认用健康基准拟合的
   密度-温度关系；**换油品或换批次后**，在工作台“数据目录”或“自动诊断”页填写当前燃油的 20 ℃ 密度（合格证上的值），
   否则可能误报质量流量计异常；
5. 零点：无流量管路上流量计应接近 0；传感器自检：卡死/冻结、掉零、超量程、噪声、毛刺、偏差渐变，
   同位置两只温度传感器互校。已知损坏的测点（如 T6、T7）在 `bench.json` 的 `ignored_sensors` 中屏蔽，不重复报警；
6. 原经验公式（质量流量→涡轮转速→理论流量，`app/core/flow_meter.py`）只在报告中作参考；
7. **模型残差**：按实测工况查仿真基准表，与健康参考模型的预期值比较（见下方“仿真模型”）。

结论分四级：正常 / 预警 / 异常 / 无法判定。

**原因分析**（`causes.py`）：一个故障常同时触发几项检查（例如逐渐扩大的泄漏 = 供回油不平衡 + 回油侧偏差渐变），
报告把这些现象归并为最可能的原因，每个原因给出解释、判断依据、其他可能和处理建议。例如“供油比回油多”时，
用同在回油侧的质量流量计区分“真实泄漏”与“两只回油表同时偏低”。

**历史趋势**（`history.py`）：每次诊断后与同类来源（试验台实时/自动诊断，或手动选择的文件，两类分开）近 90 天的
诊断结果对比：某只表偏差持续往一个方向走时提示长期漂移；质量流量计有偏差时，用几次不同流量的结果把误差拆成
零点（kg/h）与标定（%）两部分。只作补充说明，不改变本次结论。任务列表页“诊断趋势”可查看各表偏差随时间的变化。

报告包括结论、原因分析、检查项、检测明细、处理建议，以及算法版本、配置与健康基准来源。

**配置**（`pump_test_bench/config/bench.json`，修改后下次诊断即生效）：管路与流量计的对应关系、各表对应的
三维部件、密度-温度模型、各项阈值、传感器合理范围。当前对应关系是按 2026-11 实测数据推断的，请对照管路图核对。

**健康基准**（`baseline.py`）：用设备正常时的数据，统计每只流量计相对其余表的固有偏差（拟合为流量、油温的函数）、
短时波动，并拟合密度-温度关系。随代码提供的 `config/baseline_default.json` 由 2026-11 的 60 个工况文件生成；
设备检修、更换流量计后应重新建立：

```bash
python -m pump_test_bench.tools.build_baseline 健康数据目录 --save      # 保存到 pump_test_bench/data/baseline.json
python -m pump_test_bench.tools.validate_diagnosis 健康数据目录          # 故障注入验证：检出率、定位准确率、误报率
python -m pump_test_bench.tools.generate_fault_data 健康数据目录 --out 故障数据  # 生成 15 类物理故障的异常数据文件（原格式）+ 故障清单.csv
```

### 仿真模型（`pump_test_bench/app/simulation/`）

仿真模型是试验台各部分的**健康参考模型**：给定工况，给出健康时各测点的预期值，诊断时与实测比较。
每个模型一份配置（`config/simulation/<id>.json`），各有一张仿真基准表并用正常数据标定。第一批三个模型对应三维模型的三片区域：

| 模型 | 三维部件 | 引擎 | 输入 → 输出 | 负责发现 |
|---|---|---|---|---|
| 泵-管路系统 `bench` | 被试件、供/回油管路 | 数据代理模型 | 电传转速、进口压力、油温 → 流量、压力、扭矩 | 被试泵出力下降、无冗余的压力传感器漂移 |
| 涡轮流量计 `turbine` | 回路 1/2 流量计、供油管路 | 数学公式 | 质量流量、燃油密度 → 理论体积流量 | 单只/几只涡轮表 K 系数漂移；参考量（质量计、密度）偏差 |
| 温控链路 `thermal` | 加热器、板式换热器、循环油箱 | 数据代理模型 | 汇流温度、流量 → 油箱、供油、回油温度 | 温度传感器偏差；汇流温度（模型输入）测点偏差 |

- **引擎**：`surrogate` 数据代理模型（由正常数据拟合的二次响应面，AMESim 接入前用于跑通流程）、`formula` 内置数学公式
  （`formulas.py`）、`amesim` AMESim 模型（补全配置中 `amesim` 段后重建基准表即可切换）。
- **基准表**：离线在工况网格上运行模型，在线按实测工况插值（毫秒级，自动诊断也能用）。随代码提供的默认表在
  `config/simulation_tables/`，前端或工具重建的保存在数据库目录 `simulation_tables/`，优先使用。
- **标定**：用正常数据求每个测点的固有偏差（随工况平滑变化）与离散 σ，按留一组（油温目录）交叉验证，阈值 = max(下限, 倍数 × σ)。
  2026-11 数据：系统流量 σ≈1.1%，压力 1.6–4.5%，涡轮表 1.1–1.5%，温度 1.4–2.0 ℃。
- **规则**：单测点偏离；整体偏移（一组测点彼此一致、整体偏离，含义分 pump / reference / input 三种）。
  模型的发现并入原因分析：属于已有原因的作为补充依据，否则单独成为原因。
- **诊断方案**：每个模型“参与结论 / 仅作参考 / 关闭”，以及预警、异常的 σ 倍数。全局一套（“仿真模型”页），
  自动诊断与手动诊断共用；手动诊断时可在“自动诊断”页临时调整。
- **加模型**：在 `config/simulation/` 加一份配置（输入、输出与测点、规则、阈值），重建基准表即可，诊断代码不用改。

```bash
python -m pump_test_bench.tools.build_simulation_table 健康数据目录                    # 所有模型，保存到数据目录
python -m pump_test_bench.tools.build_simulation_table 健康数据目录 --model turbine    # 只建一个模型
python -m pump_test_bench.tools.build_simulation_table 健康数据目录 --engine amesim    # 用 AMESim
```

## 快速开始（Windows）

1. **配置**：复制 `.env.example` 为 `.env`，至少填写 `SECRET_KEY`、`ADMIN_PASSWORD`。数据目录在前端填写，不需要改 `.env`。
2. **后端**：
   ```powershell
   conda env create -f pump_test_bench/environment.yml   # 首次
   powershell -ExecutionPolicy Bypass -File pump_test_bench/start_project.ps1
   ```
   也可以在仓库根目录分别运行 `python -m pump_test_bench.app.services.task_service`（以及 `file_service`、`llm_service`）。
3. **AMESim 服务**（只在用 AMESim 重建仿真基准表时需要）：设置环境变量 `AME`，运行 `AMESim_server/startAmeServer.bat`，模型文件放在 `AMESim_server/model/`。
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
  app/core/                 数据解析与读取、实时监控、报告生成、原经验公式
  app/diagnosis/            诊断：稳定段、流量计互校、泄漏、质量-体积校核、传感器自检、健康基准、故障注入
  app/simulation/           仿真模型：模型注册、代理模型/数学公式/AMESim 适配、基准表、标定、模型残差检查
  config/                   诊断配置 bench.json、默认健康基准 baseline_default.json、
                            仿真模型配置 simulation/*.json、默认仿真基准表 simulation_tables/*.json
  app/db/tasks.py           任务存储（SQLite，自动迁移旧版 fault_diagnosis_tasks_2 表）
  app/llm/                  大模型客户端、会话存储、窗口分析
  app/services/             三个 HTTP 服务
  samples/                  样例数据（测试也用它）；标准台样例/ 为试验台实际导出格式（含无表头、末行未写完）
  tools/                    replay_data（回放数据模拟试验台）、build_baseline（建立健康基准）、
                            validate_diagnosis（故障注入验证）、generate_fault_data（生成异常数据文件）、
                            build_simulation_table（建立仿真基准表）
  tests/                    后端测试
AMESim_server/              AMESim 仿真服务与 Python/Java 客户端（后端重建仿真基准表时调用）
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
