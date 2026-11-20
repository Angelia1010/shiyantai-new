"""诊断所用信号（config/bench.json 的 signals）：按在管路中的角色（key）取用。

诊断只读这些信号对应的列；其他列（显示用的测点、已损坏的测点）不参与诊断。
"""
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

# 角色
CONTROL_PRESSURE, SUPPLY_TEMPERATURE, SUPPLY_FLOW = "control_pressure", "supply_temperature", "supply_flow"
INLET_PRESSURE, SPEED, OUTLET_PRESSURE = "inlet_pressure", "speed", "outlet_pressure"
RETURN_TEMPERATURE, RETURN_FLOW, BACK_PRESSURE = "return_temperature", "return_flow", "back_pressure"
REQUIRED = (SUPPLY_FLOW, RETURN_FLOW)


@dataclass(frozen=True)
class Signal:
    key: str
    column: str
    label: str
    unit: str
    kind: str                      # flow / pressure / temperature / speed
    component: Optional[str] = None
    position: str = ""
    checks: Tuple[str, ...] = ()
    setpoints: Tuple[float, ...] = ()

    @staticmethod
    def from_config(item: Dict) -> "Signal":
        return Signal(item["key"], item["column"], item.get("label", item["column"]), item.get("unit", ""),
                      item["kind"], item.get("component"), item.get("position", ""),
                      tuple(item.get("checks", ())), tuple(item.get("setpoints", ())))


@dataclass
class SignalSet:
    signals: List[Signal]
    _by_key: Dict[str, Signal] = field(init=False, repr=False)

    def __post_init__(self):
        self._by_key = {s.key: s for s in self.signals}

    @staticmethod
    def from_config(cfg: Dict) -> "SignalSet":
        return SignalSet([Signal.from_config(item) for item in cfg["signals"]])

    def __iter__(self) -> Iterator[Signal]:
        return iter(self.signals)

    def get(self, key: str) -> Optional[Signal]:
        return self._by_key.get(key)

    def column(self, key: str) -> Optional[str]:
        s = self._by_key.get(key)
        return s.column if s else None

    def by_column(self, column: str) -> Optional[Signal]:
        return next((s for s in self.signals if s.column == column), None)

    @property
    def columns(self) -> List[str]:
        return [s.column for s in self.signals]

    def present(self, columns) -> "SignalSet":
        """数据文件中存在的信号。"""
        cols = set(columns)
        return SignalSet([s for s in self.signals if s.column in cols])
