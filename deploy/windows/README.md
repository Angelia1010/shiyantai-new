# Windows 安装包：打包与安装

把整个系统（后端服务、前端页面、Python 运行环境、默认模型与配置）做成一个安装包 `BenchCheck-Setup-<版本>.exe`。
目标电脑**不需要**安装 Python、Node.js、Nginx，也不需要联网：双击安装，装完从桌面图标打开即可。

## 一、打包（在一台能联网的 Windows 电脑上）

### 1. 准备（只需一次）

| 软件 | 用途 | 下载 |
|---|---|---|
| Node.js 18 LTS（带 npm） | 编译前端 | https://nodejs.org |
| Inno Setup 6 | 生成安装包 | https://jrsoftware.org/isdl.php |
| Git（可选） | 获取代码 | https://git-scm.com |

Python 不需要预先安装：打包脚本会自动下载 Python 嵌入式运行环境。

### 2. 打包

在仓库根目录打开 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\build_installer.ps1
```

国内网络建议使用镜像：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\build_installer.ps1 `
    -PipIndex https://pypi.tuna.tsinghua.edu.cn/simple -NpmRegistry https://registry.npmmirror.com
```

完成后，安装包在 `deploy\windows\output\BenchCheck-Setup-<版本>.exe`（约 150–250 MB）。

| 参数 | 说明 |
|---|---|
| `-Version 1.2.0` | 版本号，默认读 `deploy\windows\VERSION`；发新版时改这个文件即可 |
| `-PythonVersion 3.11.9` | 打包的 Python 版本 |
| `-PipIndex` / `-NpmRegistry` | pip / npm 镜像 |
| `-SkipFrontend` | 不重新编译前端，用已有的 `digital-twin-platform\dist` |
| `-NoInstaller` | 只组装 `deploy\windows\build\stage`，不生成安装包（用于检查） |

脚本做的事情：下载并缓存 Python 嵌入式包 → 安装 `requirements-runtime.txt` 中的依赖 → `npm ci` 与 `npm run build:prod` →
组装程序目录 → 导入自检 → 调用 Inno Setup 生成安装包。下载的文件缓存在 `deploy\windows\cache`，再次打包不用重新下载。

### 3. 文件清单

| 文件 | 作用 |
|---|---|
| `build_installer.ps1` | 一键打包脚本 |
| `setup.iss` | 安装包脚本（Inno Setup）：安装向导、组件、快捷方式、卸载 |
| `installer_tools.py` | 安装后的配置与服务管理：写配置、注册开机运行、启动/停止、卸载 |
| `requirements-runtime.txt` | 安装包内 Python 的依赖 |
| `scripts\*.bat` | 安装后放在程序目录：启动 / 停止 / 重启服务、查看状态 |
| `VERSION` | 版本号 |

`build\`、`cache\`、`output\` 是打包过程的中间文件与产物，不提交到 git。

## 二、安装（目标电脑）

要求：Windows 10 / 11 64 位，安装时需要管理员权限。

1. 双击 `BenchCheck-Setup-<版本>.exe`。
2. 选择安装位置（默认 `C:\Program Files\BenchCheck`）。
3. 选择组件：标准安装即可；需要时在“自定义安装”中勾选：
   - **智能助手**：需要另外部署 Ollama 与大模型（见程序目录 `app\DeepSeek-model\README.md`）；
   - **AMESim 仿真服务**：需要本机已安装 AMESim，向导中选择其安装目录。
4. 是否允许局域网内其他电脑访问（勾选后会在防火墙中打开端口）。
5. 设置登录密码（用户名 admin）和网页端口（默认 8080）。
6. 安装完成后自动启动服务并打开浏览器；之后从桌面“标准台校验系统”图标打开。

安装后，系统作为后台服务**开机自动运行**（Windows 计划任务 `BenchCheck`，系统账户），不需要登录 Windows、不弹出窗口；
某个服务异常退出会自动重启。

### 目录

| 位置 | 内容 |
|---|---|
| `C:\Program Files\BenchCheck\` | 程序（升级时整体替换） |
| `C:\ProgramData\BenchCheck\.env` | 配置（密码、端口等），升级时保留 |
| `C:\ProgramData\BenchCheck\data\` | 数据库、自己建的仿真模型、诊断设置、登记的数据目录 |
| `C:\ProgramData\BenchCheck\logs\` | 日志（每个服务一个文件，按天滚动） |

### 日常管理

开始菜单“标准台校验系统”中：打开系统、启动服务、停止服务、重启服务（修改 `.env` 后用）、服务状态、打开数据与日志目录、卸载。

### 升级

在目标电脑上直接运行新版本安装包即可：会先停止旧版本，替换程序，配置与数据全部保留（密码可以留空表示不改）。

### 卸载

控制面板或开始菜单中“卸载”。卸载时会询问是否同时删除数据；选“否”时数据保留，重新安装后可以继续使用。

## 三、常见问题

| 现象 | 处理 |
|---|---|
| 浏览器打不开页面 | 运行“服务状态”；未运行则“启动服务”；仍不行看 `C:\ProgramData\BenchCheck\logs\supervisor.log` 与各 `*.out.log` |
| 端口被占用 | 修改 `C:\ProgramData\BenchCheck\.env` 中的 `GATEWAY_PORT`，然后“重启服务”；桌面图标的地址需重新安装或手动修改 |
| 局域网其他电脑访问不了 | 安装时勾选“允许局域网访问”（或在 `.env` 中设 `GATEWAY_HOST=0.0.0.0` 并重启服务，同时在防火墙放行端口） |
| 数据目录在网络盘（映射的 Z: 盘）上读不到 | 服务以系统账户运行，看不到用户映射的盘符：在页面中填写 UNC 路径（如 `\\服务器\共享\数据`），并给该共享授予本机计算机账户读权限 |
| 忘记登录密码 | 重新运行安装包，在密码页填写新密码 |
| 智能助手不可用 | 确认安装时勾选了“智能助手”，且 Ollama 已按说明部署并运行（`.env` 中 `OLLAMA_URL`） |
