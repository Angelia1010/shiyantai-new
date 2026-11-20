"""AMESim 仿真服务（默认端口 5003，前端代理前缀 /api/amesim）。

把 AMESim 2021.1 的 Python API 封装成 HTTP 接口。AMESim API 同一时间只能操作一个模型，
所以服务以单线程方式运行，请求依次执行；多人同时使用时会共用同一个已打开的模型。

模型文件和仿真数据文件都只能位于 AMESIM_MODEL_DIR（默认 AMESim_server/model）目录内。

启动：在仓库根目录用 AMESim 自带的 Python 执行
    "%AME%\\sys\\python\\win64\\python.exe" -m AMESim_server.src.AmeSimuSessionServer
或直接运行 AMESim_server/startAmeServer.bat。
"""
import logging
import os
import sys
from pathlib import Path

from flask import jsonify, request

from shared.config import get_settings
from shared.flask_app import ApiError, create_app, json_body
from shared.logging_setup import setup_logging

SERVICE_NAME = "amesim_service"
logger = logging.getLogger(SERVICE_NAME)

MODEL_SUFFIXES = (".ame",)
DATA_SUFFIXES = (".data",)
INPUT_DATA_FILE = "input.data"
INPUT_X_STEP = 0.1


def _prepare_ame_environment() -> None:
    """把 AMESim 安装目录下的 Python 模块和 DLL 加入搜索路径。"""
    ame = os.environ.get("AME")
    if not ame:
        raise RuntimeError("未设置环境变量 AME（应指向 AMESim 安装目录）")
    module_path = os.path.join(ame, "scripting", "python")
    for p in (module_path, os.path.join(module_path, "win64"), os.path.join(ame, "win64")):
        sys.path.append(p)
    os.environ["PATH"] = os.path.join(ame, "sys", "python", "win64", "DLLs") + os.pathsep + os.environ["PATH"]
    os.environ["CONDA_DLL_SEARCH_MODIFICATION_ENABLE"] = "1"
    os.environ["PYTHONNOUSERSITE"] = "1"
    os.environ["QT_PLUGIN_PATH"] = os.path.join(ame, "win64")
    if hasattr(os, "add_dll_directory"):
        for p in (os.path.join(ame, "win64"), module_path, os.path.join(module_path, "win64")):
            os.add_dll_directory(p)


def _load_ame_api():
    _prepare_ame_environment()
    import ame_apy  # noqa: WPS433  AMESim 自带模块，只能在 AMESim 的 Python 里导入

    return ame_apy


ame = None  # 在 main() 中加载；导入失败时服务直接退出，不再带病运行
app = create_app(SERVICE_NAME)


def _api():
    if ame is None:
        raise ApiError("AMESim API 未加载", 503)
    return ame


def _model_file(name, suffixes) -> Path:
    """只允许访问模型目录下的文件，文件名不能带路径。"""
    name = (name or "").strip()
    if not name or name != os.path.basename(name) or name in (".", ".."):
        raise ValueError(f"文件名不合法：{name!r}（只能是模型目录下的文件名）")
    if not name.lower().endswith(suffixes):
        raise ValueError(f"文件类型必须是 {', '.join(suffixes)}：{name}")
    model_dir = get_settings().amesim_model_dir
    path = (model_dir / name).resolve()
    if path.parent != model_dir:
        raise ValueError(f"文件名不合法：{name}")
    return path


def _param(data: dict):
    if "parameter" not in data or "value" not in data:
        raise ValueError("缺少 parameter 或 value")
    return str(data["parameter"]), data["value"]


def _ok(**extra):
    return jsonify({"success": True, **extra})


@app.post("/api/init")
def init_api():
    _api().AMEInitAPI()
    return _ok()


@app.post("/api/model/open")
def open_model():
    path = _model_file(json_body().get("filePath"), MODEL_SUFFIXES)
    if not path.is_file():
        raise ApiError(f"模型文件不存在：{path.name}", 404)
    _api().AMEOpenAmeFile(str(path))
    return _ok(model=path.name)


@app.post("/api/model/close")
def close_model():
    _api().AMECloseCircuit(False)
    return _ok()


@app.post("/api/close")
def close_api():
    _api().AMECloseAPI()
    return _ok()


@app.get("/api/model/parameters")
def get_parameters():
    api = _api()
    run = {name: api.AMEGetRunParameter(name) for name in ("stop_time_s", "interval_s")}
    global_params = {name: api.AMEGetGlobalParameterValue(name) for name in api.AMEGetGlobalParameterNames()}
    comp = {}
    for compline in api.AMECreateCompLineIteration(api.ame_compline_comp):
        for parvar in api.AMECreateParVarIteration(compline, api.ame_parvar_all):
            if api.AMEIsParameter(parvar):
                comp[api.AMECopyDataPath(parvar)] = api.AMEGetParameterValue(parvar)
    return _ok(data={"runParameter": run, "globalParameter": global_params, "compParameter": comp})


@app.put("/api/model/parameters/run")
def set_run_parameter():
    name, value = _param(json_body())
    _api().AMESetRunParameter(name, value)
    return _ok()


@app.put("/api/model/parameters/global")
def set_global_parameter():
    name, value = _param(json_body())
    _api().AMESetGlobalParameterValue(name, value)
    return _ok()


@app.put("/api/model/parameters/component")
def set_component_parameter():
    name, value = _param(json_body())
    _api().AMESetParameterValue(name, str(value))
    return _ok()


@app.post("/api/simulation/run")
def run_simulation():
    logger.info("开始仿真")
    _api().AMERunSimulation()
    return _ok()


@app.get("/api/simulation/variable")
def get_variable():
    path = (request.args.get("path") or "").strip()
    if not path:
        raise ValueError("缺少参数 path")
    api = _api()
    info = api.AMEGetVariableInfos(path)
    return _ok(data={
        "variableInfo": {"path": path, "title": info[2], "unit": info[3]},
        "variableValue": dict(api.AMEGetVariableValues(path)),
    })


@app.post("/api/simulation/results")
def get_simulation_results():
    """{variables: {别名: 变量路径}} → 以第一个变量的时间点为时间轴的结果表。缺失的值为 null。"""
    variables = json_body().get("variables")
    if not isinstance(variables, dict) or not variables:
        raise ValueError("variables 必须是非空对象，如 {\"speed\": \"qout@pump01\"}")
    api = _api()
    values = {alias: dict(api.AMEGetVariableValues(path)) for alias, path in variables.items()}
    times = sorted(next(iter(values.values())).keys())
    rows = []
    for t in times:
        row = {"时间(s)": round(float(t), 3)}
        for alias in variables:
            v = values[alias].get(t)
            row[alias] = None if v is None else round(float(v), 3)
        rows.append(row)
    return _ok(data=rows)


@app.get("/api/simulation/data-file")
def read_data_file():
    path = _model_file(request.args.get("fileName"), DATA_SUFFIXES)
    if not path.is_file():
        raise ApiError(f"仿真数据文件不存在：{path.name}", 404)
    return _ok(data=path.read_text(encoding="utf-8"))


@app.post("/api/simulation/input-data")
def write_input_data():
    """把一组 Y 值写成 AMESim 一维表格文件 input.data（X 从 0.1 开始，步长 0.1）。"""
    values = json_body().get("data")
    if not isinstance(values, list) or not values:
        raise ValueError("data 必须是非空数组")
    try:
        ys = [float(v) for v in values]
    except (TypeError, ValueError):
        raise ValueError("data 中只能包含数字") from None
    lines = ["# Table format: 1D", "# axis1_title = X", "# axis2_title = Y"]
    lines += [f"     {(i + 1) * INPUT_X_STEP:.16e}      {y:.14e}" for i, y in enumerate(ys)]
    target = _model_file(INPUT_DATA_FILE, DATA_SUFFIXES)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return _ok(points=len(ys))


def main() -> None:
    global ame
    settings = get_settings()
    setup_logging(SERVICE_NAME)
    try:
        ame = _load_ame_api()
    except Exception:
        logger.exception("加载 AMESim API 失败，请确认使用 AMESim 自带的 Python 启动，且已设置 AME 环境变量")
        sys.exit(1)
    settings.amesim_model_dir.mkdir(parents=True, exist_ok=True)
    logger.info("AMESim 服务启动：http://%s:%s，模型目录：%s", settings.bind_host, settings.amesim_service_port,
                settings.amesim_model_dir)
    # AMESim API 不是线程安全的，必须单线程运行
    app.run(host=settings.bind_host, port=settings.amesim_service_port, threaded=False)


if __name__ == "__main__":
    main()
