"""故障隔离的数学部分：用“假设检验 + 数据协调”找出对一组观测最简洁、最一致的解释。

每个观测量是某个信号相对健康预期的相对偏离 y_i（如 实测/模型预期 − 1），测量模型为

    y_i = a_i·s + Σ_k 原因 k 对观测 i 的影响·θ_k + ε_i ,   ε_i ~ N(0, σ_i²)

s 是“实际流量相对模型预期的偏移”（自由参数，a_i 为该观测对实际流量的灵敏度，如流量计为 1、
压力 ≈ 0.8）。不依赖任何流量计的参照（锚点，y = 0、a = 1）给 s 一个先验，用来区分“各表一致偏移”与
“实际流量变化”。

候选假设由不超过 max_causes 个原因组合而成，原因由调用方给出（见 hypotheses.py）：每个原因有一个或几个
参数，参数对各观测的影响系数与符号约束。每个假设用加权最小二乘拟合，
得分 = χ² + Σ 原因的先验代价（简约性惩罚），得分越低越可信，相对概率 ∝ exp(−得分/2)。

本模块只做数学，不涉及信号含义、阈值与报告文字。
"""
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

FREE, NON_NEGATIVE, NON_POSITIVE = 0, 1, -1


@dataclass(frozen=True)
class Observation:
    key: str
    value: float          # 相对偏离 y
    sigma: float          # 噪声标准差
    level: float = 1.0    # 对实际流量偏移 s 的灵敏度


@dataclass(frozen=True)
class Options:
    max_causes: int = 2


@dataclass(frozen=True)
class Cause:
    """一个故障原因。effects 每项对应一个参数：{观测量: 系数}；signs 为参数的符号约束。"""
    kind: str
    keys: Tuple[str, ...]
    effects: Tuple[Dict[str, float], ...]
    signs: Tuple[int, ...]
    cost: float

    @property
    def id(self) -> str:
        return f"{self.kind}:{'+'.join(self.keys)}"


@dataclass
class Fit:
    causes: Tuple[Cause, ...]
    params: Dict[str, List[float]]       # 原因 id → 各参数估计值（被约束为 0 的参数也在内）
    level: float                         # s：实际流量相对模型预期的偏移
    residuals: Dict[str, float]          # 观测量 → 拟合残差
    chi2: float
    score: float
    probability: float = 0.0

    @property
    def ids(self) -> Tuple[str, ...]:
        return tuple(c.id for c in self.causes)

    def magnitude(self, cause: Cause) -> float:
        """原因的主要大小（第一个参数），如表的偏差、泄漏比例。"""
        return self.params[cause.id][0]

    def explained(self, obs: Observation) -> float:
        """该观测被各原因解释掉的部分（不含实际流量偏移）。"""
        return sum(v * cause.effects[j].get(obs.key, 0.0)
                   for cause in self.causes for j, v in enumerate(self.params[cause.id]))


@dataclass
class Isolation:
    observations: List[Observation]
    ranked: List[Fit] = field(default_factory=list)   # 按得分从好到差

    @property
    def best(self) -> Fit:
        return self.ranked[0]

    def alternatives(self, min_probability: float = 0.05, limit: int = 3) -> List[Fit]:
        """与最优解释不同、概率不可忽略的其他解释。"""
        return [f for f in self.ranked[1:] if f.probability >= min_probability][:limit]

    def probability_of(self, predicate) -> float:
        """满足条件的解释的概率之和，如“回油流量1-2 有问题”的总可能性。"""
        return float(sum(f.probability for f in self.ranked if predicate(f)))


def _solve(obs: Sequence[Observation], columns: List[List[float]],
           strict: bool = True) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """加权最小二乘。返回 (参数, 标准化残差)；不可辨识（秩不足，或 strict 时没有剩余自由度）时返回 None。"""
    w = np.array([1.0 / o.sigma for o in obs])
    y = np.array([o.value for o in obs]) * w
    X = np.column_stack(columns) * w[:, None]
    if X.shape[1] > len(obs) or (strict and X.shape[1] == len(obs)) or np.linalg.matrix_rank(X) < X.shape[1]:
        return None
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta, y - X @ beta


def fit(obs: Sequence[Observation], causes: Tuple[Cause, ...], strict: bool = True) -> Optional[Fit]:
    """拟合一个假设；违反符号约束的参数固定为 0 后重拟合，某个原因的参数全为 0 时该假设不成立。
    strict=False 时允许没有剩余自由度（只求参数，不用于比较假设）。"""
    level_col = [o.level for o in obs]
    fixed = set()   # (原因序号, 参数序号)
    for _ in range(4):
        columns, index = [level_col], []
        for i, cause in enumerate(causes):
            for j, effect in enumerate(cause.effects):
                if (i, j) not in fixed:
                    columns.append([effect.get(o.key, 0.0) for o in obs])
                    index.append((i, j))
        if any(all((i, j) in fixed for j in range(len(c.effects))) for i, c in enumerate(causes)):
            return None
        solved = _solve(obs, columns, strict)
        if solved is None:
            return None
        beta, resid_w = solved
        violated = {idx for idx, b in zip(index, beta[1:]) if causes[idx[0]].signs[idx[1]] * b < 0}
        if not violated:
            break
        fixed |= violated
    else:
        return None

    params = {c.id: [0.0] * len(c.effects) for c in causes}
    for (i, j), b in zip(index, beta[1:]):
        params[causes[i].id][j] = float(b)
    chi2 = float(resid_w @ resid_w)
    residuals = {o.key: float(r * o.sigma) for o, r in zip(obs, resid_w)}
    return Fit(causes, params, float(beta[0]), residuals, chi2, chi2 + sum(c.cost for c in causes))


def isolate(obs: Sequence[Observation], pool: Sequence[Cause], opts: Options = Options()) -> Optional[Isolation]:
    """对候选原因的所有组合（不超过 max_causes 个）打分排序；观测量不足两个时返回 None。"""
    obs = list(obs)
    if len(obs) < 2:
        return None
    fits: List[Fit] = []
    for n in range(opts.max_causes + 1):
        for causes in combinations(pool, n):
            f = fit(obs, causes)
            if f is not None:
                fits.append(f)
    if not fits:
        return None
    fits.sort(key=lambda f: f.score)
    best = fits[0].score
    weights = np.exp(-(np.array([f.score for f in fits]) - best) / 2)
    for f, p in zip(fits, weights / weights.sum()):
        f.probability = float(p)
    return Isolation(obs, fits)
