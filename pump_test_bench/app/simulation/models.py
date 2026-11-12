"""仿真引擎（在工况网格上逐点运行、得到 grid 产物的模型）。统一接口：run(工况) → {输出名: 预期值}。

- AmesimModel：通过 AMESim 服务（AMESim_server）设置参数、运行仿真、读取变量，取末段稳态值。
数据代理模型不在这里：它由正常数据拟合出公式（见 surrogate.py 与 builders/），诊断时直接计算。

接入新的仿真软件（如 Simulink、FMU、自研求解器）：继承 SimulationModel 实现 run()（及需要时 open/close），
然后 register_engine("类型", 类, "显示名")；模型配置 engine.type 写该类型即可，建表、标定、诊断无需改动。
"""
import logging
from typing import Callable, Dict, Iterable, List, Optional

import numpy as np


logger = logging.getLogger(__name__)


class SimulationModel:
    kind = ""
    label = ""

    def run(self, condition: Dict[str, float]) -> Dict[str, float]:
        raise NotImplementedError

    def describe(self) -> Dict:
        return {"type": self.kind, "label": self.label}


# --------------------------------------------------------------------------- AMESim 模型
class AmesimModel(SimulationModel):
    kind = "amesim"
    label = "AMESim 模型"

    def __init__(self, cfg: Dict, client=None):
        self.cfg = cfg
        self.ame = cfg.get("amesim") or {}
        self.client = client
        self.opened = False

    def _client(self):
        if self.client is None:
            from AMESim_server.src.client import AMESimClient
            from shared.auth import issue_token
            self.client = AMESimClient(issue_token("simulation"), base_url=self.ame.get("url", "http://127.0.0.1:5003"))
        return self.client

    def open(self) -> None:
        client = self._client()
        missing = [k for k, v in self.ame.get("variables", {}).items() if "待填写" in str(v)]
        if "待填写" in str(self.ame.get("model_file", "")) or missing:
            raise ValueError(f"模型配置 {self.cfg['id']}.json 的 amesim 段还有“待填写”项（模型文件、变量路径），请先按模型补全")
        client.init_api()
        client.open_model(self.ame["model_file"])
        if self.ame.get("stop_time_s"):
            client.set_run_parameter("stop_time_s", str(self.ame["stop_time_s"]))
        self.opened = True

    def close(self) -> None:
        if self.opened:
            try:
                self._client().close_model()
            except Exception:  # 关闭失败不影响结果
                logger.warning("关闭 AMESim 模型失败", exc_info=True)
            self.opened = False

    def _apply(self, condition: Dict[str, float]) -> None:
        client = self._client()
        for p in self.ame.get("parameters", []):
            value = condition.get(p["input"])
            if value is None:
                continue
            if p.get("derive"):  # 由输入换算的介质物性：temperature / density / viscosity
                from pump_test_bench.app.signals import DERIVE
                value = DERIVE[p["derive"]](value)
            if p["kind"] == "input_table":
                client.write_input_data([value] * int(p.get("points", 150)))
                continue
            values = [value] * len(p["params"])
            if p.get("lookup"):
                level = min(p["lookup"], key=lambda k: abs(float(k) - value))
                v = p["lookup"][level]
                values = v if isinstance(v, list) else [v] * len(p["params"])
            setter = client.set_comp_parameter if p["kind"] == "component" else client.set_global_parameter
            for name, v in zip(p["params"], values):
                setter(name, str(v))

    def run(self, condition: Dict[str, float]) -> Dict[str, float]:
        if not self.opened:
            self.open()
        self._apply(condition)
        client = self._client()
        client.run_simulation()
        rows = client.get_simulation_results(self.ame["variables"])["data"]
        if not rows:
            raise RuntimeError("AMESim 没有返回结果")
        t_end = rows[-1]["时间(s)"]
        tail = [r for r in rows if r["时间(s)"] >= t_end - float(self.ame.get("steady_tail_s", 5))]
        out = {}
        for name in self.ame["variables"]:
            vals = [r[name] for r in tail if r.get(name) is not None]
            if vals:
                out[name] = float(np.mean(vals))
        return out


ENGINES: Dict[str, Callable[[Dict], SimulationModel]] = {}
ENGINE_LABELS: Dict[str, str] = {}


def register_engine(kind: str, factory: Callable[[Dict], SimulationModel], label: str) -> None:
    ENGINES[kind] = factory
    ENGINE_LABELS[kind] = label


register_engine("amesim", AmesimModel, "AMESim 模型")


def make_model(cfg: Dict, kind: Optional[str] = None) -> SimulationModel:
    kind = kind or cfg.get("engine", {}).get("type")
    if kind not in ENGINES:
        raise ValueError(f"未知的仿真引擎：{kind}（可用：{'、'.join(ENGINES)}）")
    return ENGINES[kind](cfg)
