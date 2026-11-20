"""任务服务（默认端口 5001，前端代理前缀 /api/task）。

负责登录、诊断任务的增删查、执行诊断、提供报告，以及接收前端日志。

接口一览：
    POST   /auth/login                  登录，返回令牌
    GET    /auth/me                     当前用户
    GET    /tasks                       任务列表（分页；按关键字、状态、时间、mode 筛选）
    POST   /tasks                       创建任务 {path, file_name, mode}
    POST   /tasks/delete                批量删除 {task_ids: [...]}
    GET    /tasks/<id>                  任务详情
    POST   /tasks/<id>/diagnose         诊断 {density?, models?}（density：当前燃油 20 ℃ 密度；models：本次临时的诊断方案）
    GET    /tasks/<id>/report           报告（JSON）
    GET    /diagnosis/settings          诊断设置（当前燃油 20 ℃ 密度等）
    PUT    /diagnosis/settings          修改诊断设置 {fuel_density_20?, fuel_note?}
    GET    /diagnosis/history           历次诊断的关键指标（趋势图用）?days=&limit=
    GET    /diagnosis/plugins           已加载的诊断扩展插件（分析器、推理器）
    GET    /simulation/status           仿真模型列表：各模型配置、基准表与标定结果、诊断方案、重建任务状态
    POST   /simulation/models/<id>/table    后台重建该模型的基准表 {path: 正常数据目录, engine?: surrogate|amesim}
    DELETE /simulation/models/<id>/table    删除该模型重建的基准表，恢复默认表
    POST   /simulation/models/<id>/predict  工况试算 {condition: {输入名: 值}}
    POST   /simulation/models           新建仿真模型（配置见 config/simulation/*.json）
    PUT    /simulation/models/<id>      修改仿真模型配置
    DELETE /simulation/models/<id>      删除模型（内置模型删除后可恢复）；?restore=1 时只放弃对内置模型配置的修改
    POST   /simulation/models/<id>/restore  恢复已删除的内置模型
    POST   /simulation/preview          按提交的配置预览拟合（不保存）{config, path, outputs?}
    GET    /simulation/derived          派生测点（如涡轮转速 Hz）的换算
    PUT    /simulation/derived          修改派生测点换算 {items: [{name, source?, scale, offset, min?}]}
    GET    /simulation/columns          可选的测点列
    PUT    /simulation/profile          保存诊断方案 {models: {模型 id: {mode, sigma_warn?, sigma_alarm?}}}
    GET    /tasks/<id>/report.docx      报告（Word）
    POST   /logs                        前端日志 {source, logs: [{level, message}]}

启动：在仓库根目录执行 ``python -m pump_test_bench.app.services.task_service``
"""
import logging
from io import BytesIO
from typing import Dict, Optional

from flask import g, jsonify, request, send_file

from pump_test_bench.app.core.data_reader import TABLE_SUFFIXES
from pump_test_bench.app.db import tasks as repo
from pump_test_bench.app.diagnosis import settings as diag_settings
from pump_test_bench.app.diagnosis.runner import run_task_diagnosis
from pump_test_bench.app.simulation import service as sim_service
from shared.auth import check_credentials, issue_token
from shared.config import get_settings
from shared.flask_app import ApiError, create_app, json_body
from shared.logging_setup import setup_logging
from shared.paths import resolve_data_dir, resolve_data_file
from shared.serve import serve_app

SERVICE_NAME = "task_service"
logger = logging.getLogger(SERVICE_NAME)
frontend_logger = logging.getLogger("frontend")

app = create_app(SERVICE_NAME, public_paths=("/health", "/auth/login"))


# ---------------------------------------------------------------- 鉴权
@app.post("/auth/login")
def login():
    data = json_body()
    username = str(data.get("username", "")).strip()
    if not check_credentials(username, str(data.get("password", ""))):
        raise ApiError("用户名或密码错误", 401)
    return jsonify({"token": issue_token(username), "username": username})


@app.get("/auth/me")
def me():
    return jsonify({"username": g.user})


# ---------------------------------------------------------------- 任务
def _optional_int(name: str) -> Optional[int]:
    value = request.args.get(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"参数 {name} 必须是整数") from None


def _require_task(task_id: str) -> Dict:
    task = repo.get_task(task_id)
    if not task:
        raise ApiError(f"任务不存在：{task_id}", 404)
    return task


@app.get("/tasks")
def list_tasks():
    return jsonify(repo.list_tasks(
        page=_optional_int("page") or 1,
        page_size=_optional_int("page_size") or 20,
        keyword=request.args.get("keyword", "").strip() or None,
        status=request.args.get("status", "").strip() or None,
        start_time=_optional_int("start_time"),
        end_time=_optional_int("end_time"),
        mode=request.args.get("mode", "").strip() or None,
    ))


@app.post("/tasks")
def create_task():
    data = json_body()
    directory = resolve_data_dir(data.get("path"))
    file_path = resolve_data_file(str(directory), data.get("file_name"), TABLE_SUFFIXES)
    rel = file_path.relative_to(directory).as_posix()  # 可以是子目录中的文件
    task = repo.create_task(str(directory), rel, str(data.get("mode", "file")))
    return jsonify(task), 201


@app.post("/tasks/delete")
def delete_tasks():
    task_ids = json_body().get("task_ids")
    if not isinstance(task_ids, list) or not all(isinstance(t, str) for t in task_ids):
        raise ValueError("task_ids 必须是字符串数组")
    return jsonify({"deleted": repo.delete_tasks(task_ids)})


@app.get("/tasks/<task_id>")
def get_task(task_id: str):
    return jsonify(_require_task(task_id))


def _density(data: Dict) -> Optional[float]:
    return diag_settings.check_density(data.get("density"))


def _task_file(task: Dict):
    return resolve_data_file(task["path"], task["file_name"], TABLE_SUFFIXES)


@app.post("/tasks/<task_id>/diagnose")
def diagnose(task_id: str):
    task = _require_task(task_id)
    data = request.get_json(silent=True) or {}
    models = diag_settings.check_models(data.get("models")) if data.get("models") else None
    return jsonify(run_task_diagnosis(task, _task_file(task), g.user, density=_density(data), models=models))


@app.get("/tasks/<task_id>/report")
def get_report(task_id: str):
    _require_task(task_id)
    report = repo.get_report(task_id)
    if report is None:
        raise ApiError("该任务还没有诊断报告", 404)
    return jsonify(report)


@app.get("/tasks/<task_id>/report.docx")
def download_report(task_id: str):
    _require_task(task_id)
    content = repo.get_report_docx(task_id)
    if content is None:
        raise ApiError("该任务还没有诊断报告", 404)
    return send_file(BytesIO(content), as_attachment=True, download_name=f"{task_id}_诊断报告.docx",
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# ---------------------------------------------------------------- 诊断设置
@app.get("/diagnosis/settings")
def get_diagnosis_settings():
    return jsonify(diag_settings.load_settings())


@app.put("/diagnosis/settings")
def put_diagnosis_settings():
    saved = diag_settings.save_settings(json_body())
    logger.info("用户 %s 修改诊断设置：%s", g.user, saved)
    return jsonify(saved)


_HISTORY_SOURCES = {"live": ("auto", "realtime"), "file": ("file",), "all": None}


@app.get("/diagnosis/plugins")
def diagnosis_plugins():
    from pump_test_bench.app.diagnosis.plugins import list_plugins
    return jsonify({"plugins": list_plugins()})


@app.get("/diagnosis/history")
def diagnosis_history():
    """历次诊断的关键指标，按时间从早到晚。source=live（试验台实时/自动诊断，默认）| file | all。"""
    import time as _time
    from pump_test_bench.app.diagnosis.history import metrics
    days = float(request.args.get("days", "90") or 90)
    if not 0 < days <= 3650:
        raise ValueError("days 必须在 0 到 3650 之间")
    source = request.args.get("source", "live")
    if source not in _HISTORY_SOURCES:
        raise ValueError("source 只能是 live、file 或 all")
    modes = _HISTORY_SOURCES[source]
    since = int((_time.time() - days * 86400) * 1000)
    items = []
    for item in repo.list_reports(since=since, limit=1000):
        if modes and item["mode"] not in modes:
            continue
        m = metrics(item["report"])
        if not m:
            continue
        items.append({"task_id": item["task_id"], "file_name": item["file_name"], "mode": item["mode"],
                      "time": item["updated_at"], **m})
    return jsonify({"items": items, "days": days, "source": source})


# ---------------------------------------------------------------- 仿真模型
@app.get("/simulation/status")
def simulation_status():
    return jsonify(sim_service.status())


@app.post("/simulation/models/<model_id>/table")
def simulation_build(model_id: str):
    data = json_body()
    engine = data.get("engine") or sim_service.load_model_cfg(model_id)["engine"]["type"]
    if engine not in sim_service.ENGINE_LABELS:
        raise ValueError(f"engine 只能是 {'、'.join(sim_service.ENGINE_LABELS)}")
    directory, files = sim_service.resolve_source(data.get("path"))
    try:
        job = sim_service.start_build(model_id, files, engine, str(directory), g.user)
    except RuntimeError as exc:
        raise ApiError(str(exc), 409) from None
    return jsonify(job), 202


@app.delete("/simulation/models/<model_id>/table")
def simulation_reset(model_id: str):
    return jsonify({"removed": sim_service.reset_table(model_id), **sim_service.status()})


@app.post("/simulation/models/<model_id>/predict")
def simulation_predict(model_id: str):
    return jsonify(sim_service.try_predict(model_id, json_body().get("condition") or {}))


@app.post("/simulation/models")
def simulation_create():
    model = sim_service.save_model(json_body())
    logger.info("用户 %s 新建仿真模型 %s", g.user, model["id"])
    return jsonify(model), 201


@app.put("/simulation/models/<model_id>")
def simulation_update(model_id: str):
    model = sim_service.save_model(json_body(), model_id)
    logger.info("用户 %s 修改仿真模型 %s", g.user, model_id)
    return jsonify(model)


@app.delete("/simulation/models/<model_id>")
def simulation_delete(model_id: str):
    restore = request.args.get("restore") in ("1", "true")
    result = sim_service.delete_model(model_id, restore=restore)
    logger.info("用户 %s %s仿真模型 %s", g.user, "恢复内置配置：" if restore else "删除", model_id)
    return jsonify({**result, **sim_service.status()})


@app.post("/simulation/models/<model_id>/restore")
def simulation_restore(model_id: str):
    result = sim_service.restore_builtin(model_id)
    logger.info("用户 %s 恢复内置仿真模型 %s", g.user, model_id)
    return jsonify({**result, **sim_service.status()})


@app.post("/simulation/preview")
def simulation_preview():
    body = json_body()
    path = body.get("path")
    if not path:
        raise ValueError("请选择正常数据目录")
    return jsonify(sim_service.preview(body.get("config") or {}, path, body.get("outputs")))


@app.get("/simulation/derived")
def simulation_derived():
    return jsonify({"items": sim_service.derived_settings()})


@app.put("/simulation/derived")
def simulation_derived_save():
    items = sim_service.save_derived(json_body().get("items") or [])
    logger.info("用户 %s 修改派生测点换算", g.user)
    return jsonify({"items": items})


@app.get("/simulation/columns")
def simulation_columns():
    return jsonify({"columns": sim_service.known_columns()})


@app.put("/simulation/profile")
def simulation_profile():
    saved = diag_settings.save_settings({"models": json_body().get("models")})
    logger.info("用户 %s 修改诊断方案：%s", g.user, saved["models"])
    return jsonify(sim_service.status())


# ---------------------------------------------------------------- 前端日志
_LOG_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "success": logging.INFO,
               "warn": logging.WARNING, "warning": logging.WARNING, "error": logging.ERROR}
MAX_LOGS_PER_REQUEST = 200
MAX_LOG_LENGTH = 2000


@app.post("/logs")
def save_logs():
    data = json_body()
    logs = data.get("logs")
    if not isinstance(logs, list):
        raise ValueError("logs 必须是数组")
    source = str(data.get("source", "frontend"))[:50].replace("\n", " ")
    for entry in logs[:MAX_LOGS_PER_REQUEST]:
        if not isinstance(entry, dict):
            continue
        level = _LOG_LEVELS.get(str(entry.get("level", "info")).lower(), logging.INFO)
        message = str(entry.get("message", ""))[:MAX_LOG_LENGTH].replace("\r", " ").replace("\n", " ")
        frontend_logger.log(level, "[%s][%s] %s", g.user, source, message)
    return jsonify({"saved": min(len(logs), MAX_LOGS_PER_REQUEST)})


def main() -> None:
    settings = get_settings()
    setup_logging(SERVICE_NAME)
    repo.init_db()
    logger.info("任务服务启动：http://%s:%s", settings.bind_host, settings.task_service_port)
    serve_app(app, settings.bind_host, settings.task_service_port)


if __name__ == "__main__":
    main()
