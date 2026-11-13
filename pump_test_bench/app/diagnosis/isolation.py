"""故障隔离：用“假设检验 + 数据协调”找出对一组流量读数最简洁、最一致的解释。

同一路油上串联的各流量计测的是同一个流量（回油侧可能因泄漏少一部分）。把每只表的读数换算成
相对读数 y = 读数（扣除固有偏差）/ 参考水平 − 1 后，测量模型为

    y_i = s − λ·[i 在回油侧] + Σ 故障对 i 的影响 + ε_i ,   ε_i ~ N(0, σ_i²)

s 是真实流量相对参考水平的偏移（自由参数），λ 是泄漏比例。可选的“锚点”是仿真模型按工况
（转速、油温）给出的真实供油流量，它不依赖任何流量计，用来区分各表一致偏移与实际流量变化。

候选假设由不超过 max_causes 个“原因”组合而成：
- meter          某只表偏离（锚点偏离 = 实际流量与模型预期不符，如被试泵出力变化）；
- leak           回油侧（体积、质量流量计）整体少了同一个比例，λ ≥ 0；
- aeration       回油夹气：回油涡轮表多计（≥ 0），科氏质量流量计少计（≤ 0）；
- supply_group   供油侧各表一致偏移（共因）；
- return_group   回油侧体积流量计一致偏低（共因，偏高归入夹气）；
- volume_group   所有体积流量计一致偏移（油品粘度变化等共模因素）。

每个假设用加权最小二乘拟合，得分 = χ² + Σ 原因的先验代价（简约性惩罚，代价按“原因”而不是参数个数计，
一个物理原因可以同时影响几只表）。得分越低越可信，相对概率 ∝ exp(−得分/2)。
本模块只做数学，不涉及数据文件、阈值与报告文字。
"""
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

SUPPLY, RETURN = "supply", "return"
VOLUME, MASS, ANCHOR = "volume", "mass", "anchor"

METER, LEAK, AERATION = "meter", "leak", "aeration"
SUPPLY_GROUP, RETURN_GROUP, VOLUME_GROUP = "supply_group", "return_group", "volume_group"

_FREE, _NON_NEGATIVE, _NON_POSITIVE = 0, 1, -1


@dataclass(frozen=True)
class Observation:
    key: str        # 测点列名（锚点用模型 id）
    side: str       # SUPPLY / RETURN
    kind: str       # VOLUME / MASS / ANCHOR
    value: float    # 相对读数 y
    sigma: float    # 噪声标准差（相对）


@dataclass(frozen=True)
class Options:
    cause_cost: float = 9.0      # 每个原因的先验代价（约等于 3σ 的显著性）
    group_cost: float = 3.0      # 共因（多只表同时偏）比单一原因少见，额外的代价
    max_causes: int = 2


@dataclass
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
    level: float                         # s：真实流量相对参考水平的偏移
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

    def true_level(self, side: str) -> float:
        """协调后某一侧的真实流量偏移（回油侧扣除泄漏）。"""
        leak = sum(self.params[c.id][0] for c in self.causes if c.kind == LEAK)
        return self.level - (leak if side == RETURN else 0.0)


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


# --------------------------------------------------------------------------- 候选原因
def candidate_causes(obs: Sequence[Observation], opts: Options) -> List[Cause]:
    c, g = opts.cause_cost, opts.group_cost
    sup_vol = [o.key for o in obs if o.side == SUPPLY and o.kind == VOLUME]
    ret_vol = [o.key for o in obs if o.side == RETURN and o.kind == VOLUME]
    ret_all = [o.key for o in obs if o.side == RETURN and o.kind in (VOLUME, MASS)]
    mass = [o.key for o in obs if o.kind == MASS]
    vols = sup_vol + ret_vol
    has_anchor = any(o.kind == ANCHOR for o in obs)

    def group(kind: str, keys: List[str], sign: int, cost: float) -> Cause:
        return Cause(kind, tuple(keys), ({k: 1.0 for k in keys},), (sign,), cost)

    out = [Cause(METER, (o.key,), ({o.key: 1.0},), (_FREE,), c) for o in obs]
    if ret_all and (sup_vol or has_anchor):
        out.append(Cause(LEAK, tuple(ret_all), ({k: -1.0 for k in ret_all},), (_NON_NEGATIVE,), c))
    if ret_vol and mass and sup_vol:
        out.append(Cause(AERATION, tuple(ret_vol + mass), ({k: 1.0 for k in ret_vol}, {mass[0]: 1.0}),
                         (_NON_NEGATIVE, _NON_POSITIVE), c + g))
    if len(sup_vol) >= 2 and (ret_all or has_anchor):
        out.append(group(SUPPLY_GROUP, sup_vol, _FREE, c + g))
    if len(ret_vol) >= 2:
        out.append(group(RETURN_GROUP, ret_vol, _NON_POSITIVE, c + g))
    if len(vols) >= 2 and (mass or has_anchor):
        out.append(group(VOLUME_GROUP, vols, _FREE, c + g))
    return out


def _overlapping(causes: Tuple[Cause, ...]) -> bool:
    """同一只表被两个原因同时解释时无法区分各自的大小（单表 + 含该表的共因除外，那是不同的物理情形）。"""
    meters = [c.keys[0] for c in causes if c.kind == METER]
    return len(meters) != len(set(meters))


# --------------------------------------------------------------------------- 拟合
def _solve(obs: Sequence[Observation], columns: List[Dict[str, float]]) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """加权最小二乘。返回 (参数, 标准化残差)；不可辨识（秩不足或没有剩余自由度）时返回 None。"""
    w = np.array([1.0 / o.sigma for o in obs])
    y = np.array([o.value for o in obs]) * w
    X = np.column_stack([np.ones(len(obs))] + [[col.get(o.key, 0.0) for o in obs] for col in columns]) * w[:, None]
    if X.shape[1] >= len(obs) or np.linalg.matrix_rank(X) < X.shape[1]:
        return None
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta, y - X @ beta


def fit(obs: Sequence[Observation], causes: Tuple[Cause, ...]) -> Optional[Fit]:
    """拟合一个假设；违反符号约束的参数固定为 0 后重拟合，某个原因的参数全为 0 时该假设不成立。"""
    fixed = set()   # (原因序号, 参数序号)
    for _ in range(4):
        columns, index = [], []
        for i, cause in enumerate(causes):
            for j, effect in enumerate(cause.effects):
                if (i, j) not in fixed:
                    columns.append(effect)
                    index.append((i, j))
        if any(all((i, j) in fixed for j in range(len(cause.effects))) for i, cause in enumerate(causes)):
            return None
        solved = _solve(obs, columns)
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


def isolate(obs: Sequence[Observation], opts: Options = Options()) -> Optional[Isolation]:
    """对所有候选假设打分排序；观测量不足两个时返回 None。"""
    obs = list(obs)
    if len(obs) < 2:
        return None
    pool = candidate_causes(obs, opts)
    fits: List[Fit] = []
    for n in range(opts.max_causes + 1):
        for causes in combinations(pool, n):
            if _overlapping(causes):
                continue
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
