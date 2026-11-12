import sqlite3
import time

import pytest

from pump_test_bench.app.diagnosis.engine import ALGORITHM_VERSION
from pump_test_bench.tests.conftest import SAMPLE_XLSX


@pytest.fixture()
def task_client(sample_dir):
    from pump_test_bench.app.db import tasks
    from pump_test_bench.app.services.task_service import app
    tasks.init_db()
    return app.test_client()


@pytest.fixture()
def file_client(sample_dir):
    from pump_test_bench.app.services.file_service import app
    return app.test_client()


def auth(token):
    return {"X-Token": token}


def test_requires_login(task_client, file_client):
    assert task_client.get("/tasks").status_code == 401
    assert file_client.get("/files?path=x").status_code == 401
    assert task_client.get("/health").status_code == 200


def test_login(task_client):
    bad = task_client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401
    ok = task_client.post("/auth/login", json={"username": "admin", "password": "pass123"})
    assert ok.status_code == 200
    token = ok.get_json()["token"]
    assert task_client.get("/auth/me", headers=auth(token)).get_json() == {"username": "admin"}


def test_task_lifecycle(task_client, sample_dir, token):
    created = task_client.post("/tasks", headers=auth(token),
                               json={"path": str(sample_dir), "file_name": SAMPLE_XLSX, "mode": "file"})
    assert created.status_code == 201
    task_id = created.get_json()["task_id"]
    assert created.get_json()["status"] == "Created"

    assert task_client.get(f"/tasks/{task_id}/report", headers=auth(token)).status_code == 404

    diag = task_client.post(f"/tasks/{task_id}/diagnose", headers=auth(token), json={"density": 850})
    assert diag.status_code == 200, diag.get_json()
    assert diag.get_json()["result"] in ("normal", "warning", "abnormal", "inconclusive")
    assert diag.get_json()["algorithm"]["version"] == ALGORITHM_VERSION

    task = task_client.get(f"/tasks/{task_id}", headers=auth(token)).get_json()
    assert task["status"] == "Completed" and task["result"] == diag.get_json()["result"]

    docx = task_client.get(f"/tasks/{task_id}/report.docx", headers=auth(token))
    assert docx.status_code == 200 and docx.data[:2] == b"PK"

    listing = task_client.get("/tasks?page=1&page_size=10&status=Completed", headers=auth(token)).get_json()
    assert listing["total"] == 1 and listing["items"][0]["task_id"] == task_id
    assert "report_json" not in listing["items"][0]

    deleted = task_client.post("/tasks/delete", headers=auth(token), json={"task_ids": [task_id]})
    assert deleted.get_json() == {"deleted": 1}


def _write_healthy(path, **kwargs):
    from pump_test_bench.tests.test_diagnosis import healthy_frame
    healthy_frame(**kwargs).to_csv(path, index=False)
    return path


def test_simulation_comparison_is_attached_to_report(task_client, sample_dir, token):
    _write_healthy(sample_dir / "ok.csv")
    task_id = task_client.post("/tasks", headers=auth(token),
                               json={"path": str(sample_dir), "file_name": "ok.csv"}).get_json()["task_id"]
    resp = task_client.post(f"/tasks/{task_id}/preliminary", headers=auth(token), json={
        "experiment_data": {"v": [1.0, 1.0]}, "simulation_data": {"v": [1.02]}})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["preliminary"]["is_abnormal"] is False
    assert body["report"]["simulation"]["total_compared"] == 1
    assert task_client.get(f"/tasks/{task_id}", headers=auth(token)).get_json()["result"] == "normal"


def test_failed_diagnosis_marks_task(task_client, sample_dir, token):
    import pandas as pd
    pd.DataFrame({"压力": [1.0]}).to_excel(sample_dir / "empty.xlsx", index=False)
    task_id = task_client.post("/tasks", headers=auth(token),
                               json={"path": str(sample_dir), "file_name": "empty.xlsx"}).get_json()["task_id"]
    resp = task_client.post(f"/tasks/{task_id}/diagnose", headers=auth(token), json={})
    assert resp.status_code == 400
    task = task_client.get(f"/tasks/{task_id}", headers=auth(token)).get_json()
    assert task["status"] == "Failed" and "流量计列" in task["error"]


def test_paths_outside_data_roots_are_rejected(task_client, file_client, tmp_path, token):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.xlsx").write_bytes(b"x")
    assert file_client.get(f"/files?path={outside}", headers=auth(token)).status_code == 400
    r = task_client.post("/tasks", headers=auth(token), json={"path": str(outside), "file_name": "a.xlsx"})
    assert r.status_code == 400
    r = file_client.get(f"/files/page?path={tmp_path / 'data'}&file_name=../outside/a.xlsx", headers=auth(token))
    assert r.status_code == 400


def test_file_listing_and_paging(file_client, sample_dir, token):
    files = file_client.get(f"/files?path={sample_dir}", headers=auth(token)).get_json()["files"]
    assert SAMPLE_XLSX in files
    page = file_client.get(f"/files/page?path={sample_dir}&file_name={SAMPLE_XLSX}&page=0&page_size=100",
                           headers=auth(token)).get_json()
    assert page["has_more"] is True and len(page["columns"]["回油流量1-1"]) == 100


def test_live_monitor_endpoints(file_client, sample_dir, token, monkeypatch):
    import pump_test_bench.app.services.file_service as fs
    monkeypatch.setattr(fs, "_monitor", None)  # 用本测试的配置重新创建
    watch_dir = sample_dir / "live"
    sub = watch_dir / "36-38摄氏度"
    sub.mkdir(parents=True)
    from pump_test_bench.app.db import tasks as repo
    repo.init_db()
    resp = file_client.post("/watch", headers=auth(token), json={"path": str(watch_dir)}).get_json()
    assert resp["auto_diagnose"] is True
    assert resp["path"] == str(watch_dir) and resp["state"] == "waiting"
    monitor = fs.get_monitor()
    monitor.stop()  # 测试中手动调用 scan，避免与后台线程交错

    target = sub / "run.txt"
    target.write_bytes("时间\t回油流量1-1\t\n\n\n".encode("gbk"))
    lines = [f"10:00:{i // 10:02d}.{i % 10}00\t{150 + i}\t\n" for i in range(25)]
    with target.open("ab") as f:
        f.write("".join(lines[:12]).encode("gbk"))
    monitor.scan(now=100)
    live = file_client.get("/live/status", headers=auth(token)).get_json()
    assert live["state"] == "live" and live["file"] == "36-38摄氏度/run.txt"
    frames = file_client.get("/live/frames?since=0", headers=auth(token)).get_json()
    assert [f["time"] for f in frames["frames"]] == ["10:00:00"]  # 第 1 秒已完整，第 2 秒还在累积
    assert frames["frames"][0]["stats"]["回油流量1-1"]["avg"] == 154.5

    with target.open("ab") as f:
        f.write("".join(lines[12:]).encode("gbk"))
    monitor.scan(now=101)
    monitor.scan(now=105)  # 安静超过 settle 时间：视为写完
    later = file_client.get(f"/live/frames?since={frames['latest_seq']}", headers=auth(token)).get_json()
    assert [f["time"] for f in later["frames"]] == ["10:00:01", "10:00:02"]
    events = file_client.get("/watch/events?since=0", headers=auth(token)).get_json()["events"]
    assert [(e["type"], e["file_name"]) for e in events] == [("created", "36-38摄氏度/run.txt")]

    # 写完后自动诊断：后台建任务（mode=auto）。只有一只流量计，无法互校 → 无法判定
    from pump_test_bench.app.db import tasks as repo
    fs.auto_diagnoser.drain()
    for _ in range(50):
        auto = repo.list_tasks(mode="auto")["items"]
        if auto and auto[0]["status"] != "Created":
            break
        time.sleep(0.1)
    assert auto[0]["file_name"] == "36-38摄氏度/run.txt" and auto[0]["result"] == "inconclusive"

    # 子目录中的文件可以直接分页读取
    page = file_client.get("/files/page", headers=auth(token),
                           query_string={"path": str(watch_dir), "file_name": "36-38摄氏度/run.txt"}).get_json()
    assert page["total_rows"] == 25
    listed = file_client.get(f"/files?path={watch_dir}&recursive=1", headers=auth(token)).get_json()["files"]
    assert "36-38摄氏度/run.txt" in listed


def test_data_dirs_registered_from_frontend(file_client, env, tmp_path, token):
    outside = tmp_path / "bench_share"  # 不在 DATA_ROOTS 内
    outside.mkdir()
    (outside / "a.txt").write_text("时间\t值\n10:00:00\t1\n", encoding="utf-8")
    h = auth(token)
    assert file_client.get(f"/files?path={outside}", headers=h).status_code == 400  # 未登记

    for bad, reason in (("/", "根目录"), ("/etc", "系统目录"), (str(tmp_path / "nope"), "不存在"), ("rel/dir", "完整路径")):
        resp = file_client.post("/data-dirs", headers=h, json={"path": bad})
        assert resp.status_code == 400 and reason in resp.get_json()["error"], bad

    assert file_client.post("/data-dirs", headers=h, json={"path": str(outside)}).status_code == 200
    dirs = file_client.get("/data-dirs", headers=h).get_json()
    assert dirs["registered"] == [str(outside)] and dirs["preset"] == [str(env)]
    assert file_client.get(f"/files?path={outside}", headers=h).get_json()["files"] == ["a.txt"]

    assert file_client.delete(f"/data-dirs?path={outside}", headers=h).status_code == 200
    assert file_client.get(f"/files?path={outside}", headers=h).status_code == 400


def test_file_names_cannot_escape_data_dir(file_client, sample_dir, token):
    for bad in ("../x.txt", "..\\x.txt", "/etc/passwd.txt", "C:/x.txt", "a/../../x.txt"):
        resp = file_client.get("/files/page", headers=auth(token),
                               query_string={"path": str(sample_dir), "file_name": bad})
        assert resp.status_code == 400, bad


def test_frontend_logs_are_sanitised(task_client, token):
    resp = task_client.post("/logs", headers=auth(token),
                            json={"source": "x", "logs": [{"level": "error", "message": "a\nFAKE LINE"}]})
    assert resp.get_json() == {"saved": 1}


def test_legacy_table_is_migrated(env):
    from shared.config import get_settings
    db = get_settings().db_path
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE fault_diagnosis_tasks_2 (id INTEGER PRIMARY KEY, task_id TEXT, type TEXT, "
                 "files TEXT, status TEXT, path TEXT, report_data BLOB, report_json TEXT)")
    conn.execute("INSERT INTO fault_diagnosis_tasks_2 (task_id, type, files, status, path, report_json) "
                 "VALUES ('176280000000012345', '1', 'a.xlsx', 'Completed', 'D:/d', "
                 "'{\"diagnosis\": {\"fault_name\": \"涡轮流量计状态异常\"}}')")
    conn.commit()
    conn.close()
    from pump_test_bench.app.db import tasks
    tasks.init_db()
    task = tasks.get_task("176280000000012345")
    assert task["status"] == "Completed" and task["result"] == "abnormal"
    assert task["created_at"] == 1762800000000 and task["mode"] == "file"


def test_diagnosis_settings(task_client, token):
    assert task_client.get("/diagnosis/settings", headers=auth(token)).get_json()["fuel_density_20"] is None
    r = task_client.put("/diagnosis/settings", headers=auth(token), json={"fuel_density_20": 0.79})
    assert r.status_code == 400  # 单位填成 g/cm³
    r = task_client.put("/diagnosis/settings", headers=auth(token), json={"fuel_density_20": 801.5, "fuel_note": "批次 A"})
    assert r.get_json() == {"fuel_density_20": 801.5, "fuel_note": "批次 A"}
    assert task_client.get("/diagnosis/settings", headers=auth(token)).get_json()["fuel_density_20"] == 801.5


def test_history_splits_mass_zero_drift(task_client, sample_dir, token):
    """质量流量计零点漂移：多次不同流量的诊断后，历史分析能判断是零点而不是标定。"""
    from pump_test_bench.tests.test_diagnosis import healthy_frame
    report = None
    for flow in (150, 300, 500):
        df = healthy_frame(flow=flow, seed=flow)
        df["回油质量流量2"] = df["回油质量流量2"] + 12.0
        df.to_csv(sample_dir / f"mz{flow}.csv", index=False)
        task_id = task_client.post("/tasks", headers=auth(token), json={
            "path": str(sample_dir), "file_name": f"mz{flow}.csv", "mode": "file"}).get_json()["task_id"]
        report = task_client.post(f"/tasks/{task_id}/diagnose", headers=auth(token), json={}).get_json()
        assert report["result"] == "abnormal"
    split = report["history"]["mass_split"]
    assert split["kind"] == "零点漂移" and abs(split["zero_kg_h"] - 12) < 2
    assert "零点漂移" in report["summary"]
    hist = task_client.get("/diagnosis/history?source=file", headers=auth(token)).get_json()
    assert [round(i["flow"], -1) for i in hist["items"]] == [150, 300, 500]
    assert task_client.get("/diagnosis/history?source=live", headers=auth(token)).get_json()["items"] == []
