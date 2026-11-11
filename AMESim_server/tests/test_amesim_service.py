"""用假的 ame_apy 模块测试 AMESim 服务的接口逻辑（不需要安装 AMESim）。"""
import types

import pytest

from pump_test_bench.tests.conftest import env, token  # noqa: F401  复用公共夹具


class FakeAme(types.SimpleNamespace):
    def __init__(self):
        super().__init__(calls=[], params={})

    def AMEOpenAmeFile(self, path):
        self.calls.append(("open", path))

    def AMESetParameterValue(self, name, value):
        self.params[name] = value

    def AMEGetVariableValues(self, path):
        return {"a@x": [(0.0, 1.0), (0.1, 2.0)], "b@x": [(0.0, 5.0)]}[path]


@pytest.fixture()
def client(env, tmp_path, monkeypatch):  # noqa: F811
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "pump.ame").write_text("x")
    (model_dir / "flow.data").write_text("# t\n1 2\n", encoding="utf-8")
    monkeypatch.setenv("AMESIM_MODEL_DIR", str(model_dir))
    from shared.config import get_settings
    get_settings.cache_clear()
    from AMESim_server.src import AmeSimuSessionServer as server
    fake = FakeAme()
    monkeypatch.setattr(server, "ame", fake)
    return server.app.test_client(), fake, model_dir


def test_requires_token(client):
    c, _, _ = client
    assert c.post("/api/init").status_code == 401


def test_model_and_data_files_are_confined_to_model_dir(client, token):  # noqa: F811
    c, fake, model_dir = client
    h = {"X-Token": token}
    assert c.post("/api/model/open", headers=h, json={"filePath": "pump.ame"}).status_code == 200
    assert fake.calls == [("open", str(model_dir / "pump.ame"))]
    for bad in ("../pump.ame", "C:/x/pump.ame", "pump.txt"):
        assert c.post("/api/model/open", headers=h, json={"filePath": bad}).status_code == 400
    assert c.get("/api/simulation/data-file?fileName=flow.data", headers=h).get_json()["data"].startswith("# t")
    assert c.get("/api/simulation/data-file?fileName=../../etc.data", headers=h).status_code == 400


def test_results_keep_missing_values_as_null(client, token):  # noqa: F811
    c, _, _ = client
    rows = c.post("/api/simulation/results", headers={"X-Token": token},
                  json={"variables": {"a": "a@x", "b": "b@x"}}).get_json()["data"]
    assert rows == [{"时间(s)": 0.0, "a": 1.0, "b": 5.0}, {"时间(s)": 0.1, "a": 2.0, "b": None}]


def test_write_input_data(client, token):  # noqa: F811
    c, _, model_dir = client
    resp = c.post("/api/simulation/input-data", headers={"X-Token": token}, json={"data": [1, 2.5]})
    assert resp.get_json() == {"success": True, "points": 2}
    lines = (model_dir / "input.data").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# Table format: 1D" and len(lines) == 5
    assert c.post("/api/simulation/input-data", headers={"X-Token": token}, json={"data": ["x"]}).status_code == 400
