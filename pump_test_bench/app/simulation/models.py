"""仿真模型。统一接口：run(工况) → {输出名: 预期值}。

- SurrogateModel（数据代理模型）：用正常数据拟合的二次响应面。AMESim 模型接入之前，用它把整套流程跑通；
  它只“记住”了健康数据的规律，能发现偏离健康规律的情况，但不能模拟没见过的部件故障。
- FormulaModel：内置数学公式（如涡轮流量计公式），见 formulas.py；
- AmesimModel：通过 AMESim 服务（AMESim_server）设置参数、运行仿真、读取变量，取末段稳态值。
"""
import logging
from typing import Callable, Dict, Iterable, List, Optional

import numpy as np

from pump_test_bench.app.simulation.config import input_names, output_names

logger = logging.getLogger(__name__)


class SimulationModel:
    kind = ""
    label = ""

    def run(self, condition: Dict[str, float]) -> Dict[str, float]:
        raise NotImplementedError

    def describe(self) -> Dict:
        return {"type": self.kind, "label": self.label}


# --------------------------------------------------------------------------- 数据代理模型
class SurrogateModel(SimulationModel):
    """y = Σ c·[1, z_i, z_i², z_i·z_j]，z 为按网格归一化的输入。"""
    kind = "surrogate"
    label = "数据代理模型（由正常数据拟合）"

    def __init__(self, inputs: List[str], centers: List[float], scales: List[float], coef: Dict[str, List[float]],
                 fit_info: Optional[Dict] = None):
        self.inputs, self.centers, self.scales, self.coef = inputs, centers, scales, coef
        self.fit_info = fit_info or {}

    @staticmethod
    def _features(z: np.ndarray) -> np.ndarray:
        n = z.shape[1]
        cols = [np.ones(len(z))] + [z[:, i] for i in range(n)] + [z[:, i] ** 2 for i in range(n)]
        cols += [z[:, i] * z[:, j] for i in range(n) for j in range(i + 1, n)]
        return np.column_stack(cols)

    def _z(self, rows: Iterable[Dict[str, float]]) -> np.ndarray:
        return np.array([[(r[name] - c) / s for name, c, s in zip(self.inputs, self.centers, self.scales)]
                         for r in rows], dtype=float)

    @classmethod
    def fit(cls, samples: List[Dict], cfg: Dict) -> "SurrogateModel":
        """samples：[{"condition": {输入: 值}, "outputs": {输出: 值}}]，至少要比待定系数多。"""
        names = input_names(cfg)
        centers, scales = [], []
        for spec in cfg["inputs"]:
            grid = spec["grid"]
            centers.append((max(grid) + min(grid)) / 2)
            scales.append(max((max(grid) - min(grid)) / 2, 1e-9))
        model = cls(names, centers, scales, {})
        usable = [s for s in samples if all(n in s["condition"] for n in names)]
        X = cls._features(model._z(s["condition"] for s in usable))
        if len(usable) < X.shape[1] + 3:
            raise ValueError(f"可用于拟合的正常数据只有 {len(usable)} 个工况，至少需要 {X.shape[1] + 3} 个")
        for out in output_names(cfg):
            rows = [(i, s["outputs"][out]) for i, s in enumerate(usable) if s["outputs"].get(out) is not None]
            if len(rows) < X.shape[1] + 3:
                continue
            idx = [i for i, _ in rows]
            y = np.array([v for _, v in rows])
            c, *_ = np.linalg.lstsq(X[idx], y, rcond=None)
            model.coef[out] = [float(v) for v in c]
        model.fit_info = {"samples": len(usable)}
        return model

    def run(self, condition: Dict[str, float]) -> Dict[str, float]:
        x = self._features(self._z([condition]))[0]
        return {out: float(np.dot(c, x)) for out, c in self.coef.items()}

    def to_dict(self) -> Dict:
        return {"type": self.kind, "inputs": self.inputs, "centers": self.centers, "scales": self.scales,
                "coef": self.coef, "fit_info": self.fit_info}

    @classmethod
    def from_dict(cls, d: Dict) -> "SurrogateModel":
        return cls(d["inputs"], d["centers"], d["scales"], d["coef"], d.get("fit_info"))


# --------------------------------------------------------------------------- 数学公式
class FormulaModel(SimulationModel):
    kind = "formula"

    def __init__(self, cfg: Dict):
        from pump_test_bench.app.simulation.formulas import FORMULAS
        name = cfg["engine"].get("formula", "")
        if name not in FORMULAS:
            raise ValueError(f"未知的公式：{name}（可用：{'、'.join(FORMULAS)}）")
        self.fn = FORMULAS[name]
        self.label = f"数学公式（{cfg['name']}）"

    def run(self, condition: Dict[str, float]) -> Dict[str, float]:
        return self.fn(condition)


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


def make_model(cfg: Dict, kind: Optional[str] = None, surrogate: Optional[Dict] = None,
               samples_fn: Optional[Callable[[], List[Dict]]] = None) -> SimulationModel:
    kind = kind or cfg.get("engine", {}).get("type", "surrogate")
    if kind == "amesim":
        return AmesimModel(cfg)
    if kind == "formula":
        return FormulaModel(cfg)
    if kind == "surrogate":
        if surrogate:
            return SurrogateModel.from_dict(surrogate)
        if samples_fn is None:
            raise ValueError("数据代理模型需要正常数据来拟合")
        return SurrogateModel.fit(samples_fn(), cfg)
    raise ValueError(f"未知的模型类型：{kind}（surrogate、formula 或 amesim）")
