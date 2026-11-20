"""公式引擎：解析、检查、计算用户填写的模型公式，并用数据拟合其中的系数。

写法（与 Excel / 计算器接近）：
    a + b * 质量流量 + c * 密度
    (质量流量 * 3600 / 密度 * 1000 - q0) / K
    if(油温 > 40, a1 * 电传转速, a2 * 电传转速) + c * exp(-油温 / 30)

- 名字：变量名（模型的输入）或系数名；中文、英文、数字、下划线，不能以数字开头。
- 运算：+ - * / ^（乘方，也可写 **），比较 > < >= <= == !=。
- 函数：exp log ln log10 sqrt abs min max clip(x, 下限, 上限) if(条件, 成立时, 不成立时)。
- 不是变量也不是函数的名字都当作系数，由系数表给值（固定或由数据拟合）。

只解析上面这些写法（白名单），不执行任何代码。计算按 numpy 向量进行，可一次算一批工况。
"""
import ast
import re
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

FUNCTIONS: Dict[str, Tuple[Callable, Tuple[int, int]]] = {
    # 名字: (函数, (最少参数个数, 最多参数个数))
    "exp": (np.exp, (1, 1)),
    "log": (np.log, (1, 1)),
    "ln": (np.log, (1, 1)),
    "log10": (np.log10, (1, 1)),
    "sqrt": (np.sqrt, (1, 1)),
    "abs": (np.abs, (1, 1)),
    "min": (lambda *a: np.minimum.reduce(np.broadcast_arrays(*a)), (2, 8)),
    "max": (lambda *a: np.maximum.reduce(np.broadcast_arrays(*a)), (2, 8)),
    "clip": (np.clip, (3, 3)),
    "where": (np.where, (3, 3)),  # 公式里写 if(...)
}
FUNCTION_HELP = {
    "exp": "e 的 x 次方", "log": "自然对数", "ln": "自然对数", "log10": "常用对数", "sqrt": "平方根",
    "abs": "绝对值", "min": "最小值 min(a, b, ...)", "max": "最大值 max(a, b, ...)",
    "clip": "限幅 clip(x, 下限, 上限)", "if": "条件 if(条件, 成立时, 不成立时)",
}
_BINOPS = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide, ast.Pow: np.power}
_CMPOPS = {ast.Gt: np.greater, ast.Lt: np.less, ast.GtE: np.greater_equal, ast.LtE: np.less_equal,
           ast.Eq: np.equal, ast.NotEq: np.not_equal}
NAME_RE = re.compile(r"^[A-Za-z_一-鿿][A-Za-z0-9_一-鿿]*$")


class FormulaError(ValueError):
    """公式写法有误；message 面向用户。"""


def is_valid_name(name: str) -> bool:
    return bool(NAME_RE.match(name or "")) and name not in FUNCTIONS and name != "if"


def _prepare(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^[^=<>!()]*?(?<![<>=!])=(?!=)", "", t, count=1).strip()  # 允许写成 “Y = ...”
    t = t.replace("^", "**").replace("×", "*").replace("÷", "/").replace("（", "(").replace("）", ")").replace("，", ",")
    t = t.replace("−", "-")
    return re.sub(r"\bif\s*\(", "where(", t)


class Expression:
    """一条已解析的公式。"""

    def __init__(self, text: str):
        self.text = (text or "").strip()
        if not self.text:
            raise FormulaError("公式为空")
        try:
            tree = ast.parse(_prepare(self.text), mode="eval")
        except SyntaxError as exc:
            raise FormulaError(f"公式写法有误（第 {exc.offset or '?'} 个字符附近）：请检查括号、运算符是否完整") from None
        self.names: List[str] = []
        self._fn = self._compile(tree.body)

    # ------------------------------------------------------------------ 编译成 numpy 计算
    def _compile(self, node) -> Callable[[Dict], np.ndarray]:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            v = float(node.value)
            return lambda env: v
        if isinstance(node, ast.Name):
            name = node.id
            if name in FUNCTIONS:
                raise FormulaError(f"{name} 是函数，应写成 {name}(...)")
            if name not in self.names:
                self.names.append(name)
            return lambda env: env[name]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            inner = self._compile(node.operand)
            return (lambda env: -inner(env)) if isinstance(node.op, ast.USub) else inner
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            op, a, b = _BINOPS[type(node.op)], self._compile(node.left), self._compile(node.right)
            return lambda env: op(a(env), b(env))
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMPOPS:
            op, a, b = _CMPOPS[type(node.ops[0])], self._compile(node.left), self._compile(node.comparators[0])
            return lambda env: op(a(env), b(env))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id
            if name not in FUNCTIONS:
                raise FormulaError(f"不支持的函数：{name}（可用：{'、'.join(k for k in FUNCTION_HELP)}）")
            fn, (lo, hi) = FUNCTIONS[name]
            shown = "if" if name == "where" else name
            if not lo <= len(node.args) <= hi:
                raise FormulaError(f"函数 {shown} 的参数个数不对（{FUNCTION_HELP[shown]}）")
            args = [self._compile(a) for a in node.args]
            return lambda env: fn(*[a(env) for a in args])
        raise FormulaError("公式中有不支持的写法（只能用数字、变量、系数、+ - * / ^、比较和函数）")

    # ------------------------------------------------------------------ 使用
    def coefficient_names(self, variables: Iterable[str]) -> List[str]:
        """公式里不是变量的名字 = 系数。"""
        vs = set(variables)
        return [n for n in self.names if n not in vs]

    def check(self, variables: Sequence[str], coefs: Dict[str, float]) -> None:
        """检查名字是否都有定义。"""
        for n in self.names:
            if n in variables or n in coefs:
                continue
            raise FormulaError(f"公式中的“{n}”既不是变量也不是系数：请在变量页添加，或在系数表中给出它的值")
        for n in self.names:
            if not is_valid_name(n):
                raise FormulaError(f"名字“{n}”不合法")

    def evaluate(self, env: Dict[str, object]) -> np.ndarray:
        with np.errstate(all="ignore"):
            out = self._fn(env)
        return np.asarray(out, dtype=float)


def evaluate(text: str, variables: Dict[str, object], coefs: Dict[str, float]) -> np.ndarray:
    return Expression(text).evaluate({**coefs, **variables})


# --------------------------------------------------------------------------- 系数拟合
def fit_coefficients(expr: Expression, variables: Dict[str, np.ndarray], y: np.ndarray,
                     coefs: Dict[str, float], free: Sequence[str], max_iter: int = 60) -> Tuple[Dict[str, float], Dict]:
    """最小二乘拟合 free 中的系数（其余固定），阻尼高斯-牛顿（Levenberg-Marquardt），初值为 coefs 中的值。
    系数线性出现时一两步即收敛。返回 (系数, 信息)。"""
    free = [c for c in free if c in coefs]
    p = np.array([float(coefs[c]) for c in free])
    fixed = {k: float(v) for k, v in coefs.items() if k not in free}
    y = np.asarray(y, dtype=float)
    if not free:
        return dict(coefs), {"iterations": 0, "converged": True}
    if len(y) < len(free) + 2:
        raise FormulaError(f"拟合 {len(free)} 个系数至少需要 {len(free) + 2} 个工况，现在只有 {len(y)} 个")

    def resid(q):
        env = {**fixed, **dict(zip(free, q)), **variables}
        r = expr.evaluate(env) - y
        return np.broadcast_to(r, y.shape)

    def jac(q, r0):
        cols = []
        for i in range(len(q)):
            h = 1e-6 * max(abs(q[i]), 1.0)
            qq = q.copy()
            qq[i] += h
            cols.append((resid(qq) - r0) / h)
        return np.column_stack(cols)

    r = resid(p)
    cost = float(np.nansum(r ** 2)) if np.all(np.isfinite(r)) else np.inf
    lam, converged, it = 1e-3, False, 0
    for it in range(1, max_iter + 1):
        J = jac(p, r)
        if not np.all(np.isfinite(J)):
            break
        A = J.T @ J
        g = J.T @ r
        d = np.sqrt(np.maximum(np.diag(A), 1e-300))
        improved = False
        for _ in range(12):
            try:
                step = np.linalg.solve(A + lam * np.diag(d ** 2), -g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            q = p + step
            rq = resid(q)
            cq = float(np.sum(rq ** 2)) if np.all(np.isfinite(rq)) else np.inf
            if cq < cost:
                rel = (cost - cq) / max(cost, 1e-300)
                p, r, cost, lam, improved = q, rq, cq, max(lam / 10, 1e-12), True
                if rel < 1e-12:
                    converged = True
                break
            lam *= 10
        if not improved or converged:
            converged = converged or not improved
            break
    if not np.isfinite(cost):
        raise FormulaError("用这批数据算不出有效结果（可能有除以 0、对负数开方或取对数），请检查公式和初值")
    out = dict(coefs)
    out.update({c: float(v) for c, v in zip(free, p)})
    return out, {"iterations": it, "converged": converged}


# --------------------------------------------------------------------------- 多项式展开（自动拟合的结果写成公式）
def polynomial_expression(terms: Dict[Tuple[int, ...], float], names: Sequence[str],
                          prefix: str = "k") -> Tuple[str, Dict[str, float]]:
    """{(各变量次数): 系数} → ("k0 + k1*x + k2*x^2*y ...", {k0: .., k1: ..})，按次数从低到高排列。"""
    items = sorted(((e, c) for e, c in terms.items() if c != 0 or not any(e)), key=lambda t: (sum(t[0]), t[0][::-1]))
    parts, coefs = [], {}
    for k, (exps, c) in enumerate(items):
        cname = f"{prefix}{k}"
        coefs[cname] = float(c)
        factors = [n if p == 1 else f"{n}^{p}" for n, p in zip(names, exps) if p]
        parts.append("*".join([cname] + factors))
    return (" + ".join(parts) if parts else "0"), coefs


def expand_standardized(terms: Dict[Tuple[int, ...], float], centers: Sequence[float],
                        scales: Sequence[float]) -> Dict[Tuple[int, ...], float]:
    """把 z_i = (x_i − c_i)/s_i 的多项式展开为 x 的多项式。"""
    from math import comb
    out: Dict[Tuple[int, ...], float] = {}
    n = len(centers)
    for exps, coef in terms.items():
        # ∏ ((x_i − c_i)/s_i)^p_i = ∏ Σ_k C(p,k) x^k (−c)^(p−k) / s^p
        partial = {tuple([0] * n): coef}
        for i, p in enumerate(exps):
            if not p:
                continue
            nxt: Dict[Tuple[int, ...], float] = {}
            for e, v in partial.items():
                for k in range(p + 1):
                    w = v * comb(p, k) * (-centers[i]) ** (p - k) / scales[i] ** p
                    ee = list(e)
                    ee[i] += k
                    nxt[tuple(ee)] = nxt.get(tuple(ee), 0.0) + w
            partial = nxt
        for e, v in partial.items():
            out[e] = out.get(e, 0.0) + v
    return out


def format_expression(text: str, coefs: Dict[str, float], digits: int = 7) -> str:
    """把系数值代入公式文本，用于展示。"""
    def fmt(v: float) -> str:
        s = f"{v:.{digits}g}"
        return f"({s})" if v < 0 else s

    names = sorted(coefs, key=len, reverse=True)
    if not names:
        return text
    pattern = re.compile(r"(?<![A-Za-z0-9_一-鿿])(" + "|".join(map(re.escape, names)) + r")(?![A-Za-z0-9_一-鿿])")
    out = pattern.sub(lambda m: fmt(coefs[m.group(1)]), text)
    out = re.sub(r"\+\s*\(-([^()]+)\)", r"- \1", out)
    out = re.sub(r"^\((-[^()]+)\)", r"\1", out.strip())
    return out


def safe_float(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None
