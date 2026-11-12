"""数据代理模型的“构建器”接口。

一个构建器负责：给定一批正常数据（各变量的值、某个输出的实测值），给出这个输出的公式与系数。
交叉验证、误差统计、异常样本、标定、诊断都由通用代码完成（surrogate.py、calibration.py），
所以新增一种建模方法（如基于大模型分析的代理模型构建）只需要实现 fit()，并注册到 builders/__init__.py。

约定：
- 结果一律是“公式 + 系数”（FitResult），可以显示、可以转为自定义公式手工修改，诊断时直接计算；
- fit() 只用传入的数据，不读文件、不访问网络之外的状态；交叉验证时会在每一折上再调用它；
  代价高的构建器（如需要调用大模型）可以在结果里给出 refit：交叉验证时改用 refit 指定的方式只重估系数，
  例如 {"method": "formula", "expression": ..., "coefficients": {...}, "fit": [...]}。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


@dataclass
class FitData:
    """一个输出的建模数据。variables 的每个数组与 y、groups 等长（一个元素 = 一个正常数据文件的稳定段均值）。"""
    variables: Dict[str, np.ndarray]
    y: np.ndarray
    groups: np.ndarray                      # 分组（数据目录，如油温段），交叉验证按组留出
    output: Dict                            # 输出配置（name、unit、kind、method、formula、autofit…）
    inputs: List[Dict]                      # 模型的变量配置（name、unit、role…）
    files: List[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.y)

    def subset(self, mask: np.ndarray) -> "FitData":
        return FitData({k: v[mask] for k, v in self.variables.items()}, self.y[mask], self.groups[mask],
                       self.output, self.inputs, [f for f, m in zip(self.files, mask) if m])


@dataclass
class FitResult:
    expression: str                         # 公式文本，变量名 + 系数名
    coefficients: Dict[str, float]          # 系数值
    info: Dict = field(default_factory=dict)  # 说明：选用的项、拟合迭代、提示等（会显示在页面上）
    refit: Optional[Dict] = None            # 交叉验证时的重估方式（见模块说明），None 表示用同一构建器重新 fit


@dataclass
class OptionSpec:
    """构建器的可调选项（前端按此生成表单）。type：number / select / text / formula / coefficients。"""
    key: str
    label: str
    type: str = "number"
    default: object = None
    choices: Optional[List[Dict]] = None    # select：[{value, label}]
    help: str = ""
    min: Optional[float] = None
    max: Optional[float] = None

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class SurrogateBuilder:
    """构建器基类。子类设置 kind、label、description、options，实现 fit()。"""
    kind = ""
    label = ""
    description = ""
    options: List[OptionSpec] = []

    def available(self) -> bool:
        """是否可用（例如需要外部服务的构建器在未配置时返回 False，页面上置灰）。"""
        return True

    def validate(self, output: Dict, inputs: List[Dict]) -> None:
        """保存模型配置时检查该输出的设置，有问题抛 ValueError（面向用户的说明）。"""

    def fit(self, data: FitData) -> FitResult:
        raise NotImplementedError

    def describe(self) -> Dict:
        return {"kind": self.kind, "label": self.label, "description": self.description,
                "options": [o.to_dict() for o in self.options], "available": self.available()}
