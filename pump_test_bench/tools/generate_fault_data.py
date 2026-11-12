"""在正常（健康）数据上做故障注入，生成异常数据文件，并用诊断引擎逐个验证。

生成的文件与试验台原始文件格式完全一致（同编码、同表头、同分隔符、同时间列），
只改动被注入故障的那几列，可以直接放进数据目录做实时监控 / 自动诊断测试。

用法：
    python -m pump_test_bench.tools.generate_fault_data 健康数据目录 --out 输出目录
    python -m pump_test_bench.tools.generate_fault_data 健康数据目录 --out 输出目录 --no-diagnose

输出：
    输出目录/F01_涡轮磨损偏低/36-38℃_S4975-P0.15_明显5%.txt ...
    输出目录/故障清单.csv   （文件、故障、注入参数、预期诊断、实际诊断）
"""
import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from pump_test_bench.app.core.table_parser import decode_bytes, parse_time

RETURN_METERS = ["回油流量1-1", "回油流量1-2"]
MASS = "回油质量流量2"
TEMP = "供油温度1-1"

# ---------------------------------------------------------------------------
# 时间曲线：故障从什么时候、以什么方式出现。g(t) ∈ [0, 1]，1 表示故障完全出现
# ---------------------------------------------------------------------------


def profile(kind: str, t: np.ndarray, at: float = 0.4) -> np.ndarray:
    span = max(float(t[-1] - t[0]), 1e-9)
    x = (t - t[0]) / span
    if kind == "const":       # 整个文件都有故障（开机前就已存在）
        return np.ones_like(x)
    if kind == "step":        # 在 at 处突然出现（断线、卡死、零点跳变）
        return (x >= at).astype(float)
    if kind == "ramp":        # 从 0 线性发展到 1（磨损、渐进泄漏）
        return x
    raise ValueError(kind)


PROFILE_LABEL = {"const": "全程", "step": "中途突发", "ramp": "逐渐发展"}

# ---------------------------------------------------------------------------
# 故障模型：f(列数据字典, g, rng, 参数) -> 修改后的列数据字典（只返回改动的列）
# ---------------------------------------------------------------------------
Cols = Dict[str, np.ndarray]


def k_factor(cols: Cols, g, rng, col: str, ratio: float) -> Cols:
    """涡轮流量计 K 系数漂移：读数按比例偏移。磨损 → 偏低，沉积/流道变窄 → 偏高。"""
    return {col: cols[col] * (1 + ratio * g)}


def bearing_drag(cols: Cols, g, rng, col: str, loss: float, jitter: float = 0.01) -> Cols:
    """轴承阻滞：克服摩擦要消耗一部分流量，读数少一个固定量（L/h），小流量时百分比更大，并伴随转速抖动。"""
    v = cols[col]
    j = rng.normal(0, jitter, len(v)) * v
    return {col: np.maximum(v - loss * g + j * g, 0.0)}


def freeze(cols: Cols, g, rng, col: str) -> Cols:
    """叶轮卡滞 / 变送器死机：从故障时刻起读数冻结在当时的值。"""
    v = cols[col].copy()
    on = np.flatnonzero(g > 0.5)
    if len(on):
        v[on] = v[on[0]]
    return {col: v}


def drop_zero(cols: Cols, g, rng, col: str) -> Cols:
    """信号线断开 / 叶轮卡死不转：从故障时刻起读数为 0（带少量零点噪声）。"""
    v = cols[col].copy()
    on = g > 0.5
    v[on] = np.abs(rng.normal(0, 0.05, on.sum()))
    return {col: v}


def emi_noise(cols: Cols, g, rng, col: str, ratio: float) -> Cols:
    """电磁干扰 / 屏蔽接地不良：脉冲信号上叠加干扰，读数随机抖动。"""
    v = cols[col]
    return {col: v + rng.normal(0, ratio, len(v)) * float(np.nanmean(v)) * g}


def pulse_loss(cols: Cols, g, rng, col: str, ratio: float, depth: float = 0.5) -> Cols:
    """脉冲丢失：接插件松动、前置放大器门限偏高，偶发漏计脉冲 → 向下的毛刺。"""
    v = cols[col].copy()
    idx = np.flatnonzero(g > 0.5)
    hit = rng.choice(idx, max(1, int(len(idx) * ratio)), replace=False)
    v[hit] *= 1 - rng.uniform(0.15, depth, len(hit))
    return {col: v}


def mass_zero(cols: Cols, g, rng, col: str, offset: float) -> Cols:
    """科氏质量流量计零点漂移：测量管应力、安装振动或未做零点标定，读数多一个固定量（kg/h）。"""
    return {col: cols[col] + offset * g}


def leak(cols: Cols, g, rng, ratio: float) -> Cols:
    """供油流量计之后、回油流量计之前泄漏（或内漏旁通）：回油侧所有表（含质量流量计）同时少 ratio。"""
    return {c: cols[c] * (1 - ratio * g) for c in RETURN_METERS + [MASS]}


def aeration(cols: Cols, g, rng, ratio: float) -> Cols:
    """回油夹气 / 气穴：气泡占体积，涡轮表读的是混合物体积 → 偏高且抖动；科氏表两相解耦 → 偏低且抖动。"""
    out = {}
    for c in RETURN_METERS:
        v = cols[c]
        out[c] = v * (1 + ratio * g) + rng.normal(0, 0.02, len(v)) * v * g
    v = cols[MASS]
    out[MASS] = v * (1 - 0.5 * ratio * g) + rng.normal(0, 0.04, len(v)) * v * g
    return out


def temp_offset(cols: Cols, g, rng, col: str, offset: float) -> Cols:
    """温度传感器偏移：热电阻老化、接线电阻、安装不到位（未插到油里）。"""
    return {col: cols[col] + offset * g}


def temp_open(cols: Cols, g, rng, col: str, value: float = 157.595) -> Cols:
    """热电阻断路：变送器输出满量程，读数固定在约 157.6 ℃（与本批数据中 T6/T7 的表现一致）。"""
    v = cols[col].copy()
    v[g > 0.5] = value
    return {col: v}


# ---------------------------------------------------------------------------
# 故障清单
# ---------------------------------------------------------------------------


@dataclass
class Fault:
    code: str
    folder: str
    name: str
    target: str
    fn: Callable
    kwargs: Dict
    profile: str
    severity: str
    expect: str                     # 期望诊断结论：normal / warning / abnormal
    expect_text: str
    conditions: Sequence[str] = field(default_factory=lambda: ("B",))
    at: float = 0.4
    expect_by: Dict[str, str] = field(default_factory=dict)   # 个别工况的预期结论不同时


# 代表性工况（健康源文件）：低温中流量 / 中温中流量 / 高温大流量 / 中温小流量
CONDITIONS = {
    "A": ("20261102数据（15-25摄氏度）", "S250-P0.10.txt", "16℃_S250-P0.10"),
    "B": ("36-38摄氏度", "S4975-P0.15.txt", "36℃_S4975-P0.15"),
    "C": ("45-50摄氏度", "S9980-P0.10.txt", "46℃_S9980-P0.10"),
    "D": ("27-30摄氏度", "S1295-P0.15.txt", "27℃_S1295-P0.15"),
}

FAULTS: List[Fault] = [
    Fault("F01", "F01_涡轮磨损偏低", "涡轮流量计K系数漂移（磨损，读数偏低）", "回油流量1-2", k_factor,
          {"col": "回油流量1-2", "ratio": -0.02}, "const", "轻微2%", "warning",
          "回油流量计1-2 偏离（预警）", ("A", "B", "C")),
    Fault("F01", "F01_涡轮磨损偏低", "涡轮流量计K系数漂移（磨损，读数偏低）", "回油流量1-2", k_factor,
          {"col": "回油流量1-2", "ratio": -0.05}, "const", "明显5%", "abnormal",
          "回油流量计1-2 偏离（异常）", ("A", "B", "C")),
    Fault("F02", "F02_涡轮沉积偏高", "涡轮流量计K系数漂移（沉积/流道变窄，读数偏高）", "供油流量1-1", k_factor,
          {"col": "供油流量1-1", "ratio": 0.04}, "const", "明显4%", "abnormal",
          "供油流量计1-1 偏离（异常）", ("B", "C")),
    Fault("F03", "F03_渐进磨损", "涡轮流量计渐进磨损（测试中由 0 发展到 -8%）", "回油流量1-1", k_factor,
          {"col": "回油流量1-1", "ratio": -0.08}, "ramp", "末端8%", "abnormal",
          "回油流量计1-1 偏离 + 偏差持续变化", ("A", "B")),
    Fault("F04", "F04_轴承阻滞", "涡轮流量计轴承阻滞（少计固定流量，伴随抖动）", "供油流量1-2", bearing_drag,
          {"col": "供油流量1-2", "loss": 12.0}, "const", "少计12L/h", "abnormal",
          "小流量时供油流量计1-2 偏离明显（异常），大流量时偏离较小（预警）", ("D", "C"),
          expect_by={"C": "warning"}),
    Fault("F05", "F05_叶轮卡滞冻结", "流量计读数冻结（叶轮卡滞/变送器死机）", "回油流量1-1", freeze,
          {"col": "回油流量1-1"}, "step", "40%处冻结", "abnormal",
          "回油流量计1-1 读数冻结", ("A", "B", "C")),
    Fault("F06", "F06_断线归零", "流量计信号断线（读数归零）", "供油流量1-1", drop_zero,
          {"col": "供油流量1-1"}, "step", "50%处断线", "abnormal",
          "供油流量计1-1 读数掉零", ("B", "C"), 0.5),
    Fault("F07", "F07_电磁干扰", "电磁干扰/接地不良（读数随机抖动）", "回油流量1-2", emi_noise,
          {"col": "回油流量1-2", "ratio": 0.04}, "const", "抖动4%", "warning",
          "回油流量计1-2 波动过大", ("A", "B")),
    Fault("F08", "F08_脉冲丢失", "脉冲丢失（偶发漏计，向下毛刺）", "齿轮流量计", pulse_loss,
          {"col": "齿轮流量计", "ratio": 0.01}, "const", "1%点丢失", "warning",
          "齿轮流量计有毛刺", ("B", "C")),
    Fault("F09", "F09_质量计零漂", "科氏质量流量计零点漂移（+12 kg/h）", MASS, mass_zero,
          {"col": MASS, "offset": 12.0}, "const", "+12kg/h", "abnormal",
          "小流量时质量-体积不一致明显，大流量时较小", ("D", "C")),
    Fault("F10", "F10_质量计标定漂移", "科氏质量流量计标定系数漂移（+5%）", MASS, k_factor,
          {"col": MASS, "ratio": 0.05}, "const", "明显5%", "abnormal",
          "质量流量与体积流量不一致（异常）", ("A", "B")),
    Fault("F11", "F11_泄漏", "供回油之间泄漏（回油侧整体减少）", "回油侧", leak,
          {"ratio": 0.015}, "const", "轻微1.5%", "warning",
          "供回油不平衡（预警），各流量计本身正常", ("B",)),
    Fault("F11", "F11_泄漏", "供回油之间泄漏（回油侧整体减少）", "回油侧", leak,
          {"ratio": 0.04}, "const", "明显4%", "abnormal",
          "供回油不平衡（异常），各流量计本身正常", ("A", "B", "C")),
    Fault("F12", "F12_渐进泄漏", "泄漏逐渐扩大（由 0 发展到 6%）", "回油侧", leak,
          {"ratio": 0.06}, "ramp", "末端6%", "abnormal",
          "供回油不平衡 + 差值持续扩大", ("B", "C")),
    Fault("F13", "F13_回油夹气", "回油夹气/气穴（涡轮偏高、质量计偏低，均抖动）", "回油侧", aeration,
          {"ratio": 0.04}, "const", "含气约4%", "abnormal",
          "回油比供油多（不可能是泄漏）+ 回油侧波动", ("B", "C")),
    Fault("F14", "F14_油温传感器偏移", "油温传感器偏移（密度修正被带偏）", TEMP, temp_offset,
          {"col": TEMP, "offset": 4.0}, "const", "+4℃", "warning",
          "同位置两只温度传感器不一致（预警）", ("B",)),
    Fault("F14", "F14_油温传感器偏移", "油温传感器偏移（密度修正被带偏）", TEMP, temp_offset,
          {"col": TEMP, "offset": 8.0}, "const", "+8℃", "abnormal",
          "同位置两只温度传感器不一致（异常）", ("B", "C")),
    Fault("F15", "F15_油温传感器断路", "油温热电阻断路（读数固定约157.6℃）", TEMP, temp_open,
          {"col": TEMP}, "step", "30%处断路", "abnormal",
          "供油温度1-1 超出量程（异常）", ("B",), 0.3),
]

# ---------------------------------------------------------------------------
# 原样读写：只替换被改动列的文本，其余字节不变
# ---------------------------------------------------------------------------


@dataclass
class RawFile:
    text_lines: List[str]
    encoding: str
    header: List[str]
    data_idx: List[int]          # 数据行在 text_lines 中的下标
    fields: List[List[str]]      # 数据行拆分后的字段
    t: np.ndarray


def read_raw(path: Path) -> RawFile:
    text, encoding = decode_bytes(path.read_bytes())
    lines = text.split("\n")
    header = lines[0].rstrip("\r").split("\t")
    width = len([h for h in header if h.strip()])
    if parse_time(header[0]) is not None:
        raise ValueError(f"{path.name} 没有表头，请换一个带表头的健康文件")
    idx, fields, times = [], [], []
    for i, line in enumerate(lines[1:], start=1):
        parts = line.rstrip("\r").split("\t")
        if len([p for p in parts if p.strip()]) < width:
            continue
        tt = parse_time(parts[0])
        if tt is None:
            continue
        idx.append(i)
        fields.append(parts)
        times.append(tt)
    t = np.array(times, dtype=float)
    t = np.where(t < t[0] - 1, t + 86400, t)  # 跨零点
    return RawFile(lines, encoding, header, idx, fields, t)


def column(raw: RawFile, name: str) -> np.ndarray:
    j = raw.header.index(name)
    return np.array([float(f[j]) for f in raw.fields])


def write_raw(raw: RawFile, changed: Dict[str, np.ndarray], path: Path) -> None:
    lines = list(raw.text_lines)
    js = {raw.header.index(c): v for c, v in changed.items()}
    for k, i in enumerate(raw.data_idx):
        parts = list(raw.fields[k])
        for j, v in js.items():
            parts[j] = f"{v[k]:.3f}"
        cr = "\r" if lines[i].endswith("\r") else ""
        lines[i] = "\t".join(parts) + cr
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes("\n".join(lines).encode(raw.encoding))


def _slug(text: str) -> str:
    return re.sub(r"[\\/:*?\"<>|\s]+", "", text)


def generate(src_root: Path, out: Path, seed: int = 2026) -> List[Dict]:
    rows = []
    cache: Dict[str, RawFile] = {}
    for n, fault in enumerate(FAULTS):
        for key in fault.conditions:
            folder, name, label = CONDITIONS[key]
            src = src_root / folder / name
            raw = cache.setdefault(key, read_raw(src))
            needed = {fault.kwargs.get("col")} if "col" in fault.kwargs else set(RETURN_METERS + [MASS])
            cols = {c: column(raw, c) for c in needed}
            g = profile(fault.profile, raw.t, fault.at)
            rng = np.random.default_rng(seed + n * 10 + ord(key))
            changed = fault.fn(cols, g, rng, **fault.kwargs)
            dst = out / fault.folder / f"{label}_{_slug(fault.severity)}.txt"
            write_raw(raw, changed, dst)
            onset = raw.t[0] + (raw.t[-1] - raw.t[0]) * fault.at if fault.profile == "step" else None
            rows.append({
                "文件": str(dst.relative_to(out)), "故障编号": fault.code, "故障": fault.name,
                "注入位置": fault.target, "程度": fault.severity, "出现方式": PROFILE_LABEL[fault.profile],
                "出现时刻(s)": f"{onset - raw.t[0]:.1f}" if onset is not None else "",
                "源文件": f"{folder}/{name}", "预期结论": fault.expect_by.get(key, fault.expect), "预期诊断": fault.expect_text,
            })
    return rows


def diagnose(out: Path, rows: List[Dict]) -> None:
    import json
    from pump_test_bench.app.core.data_reader import read_table
    from pump_test_bench.app.diagnosis.baseline import DEFAULT_BASELINE
    from pump_test_bench.app.diagnosis.engine import diagnose_frame
    baseline = json.loads(Path(DEFAULT_BASELINE).read_text(encoding="utf-8"))
    for r in rows:
        _, df = read_table(out / r["文件"])
        rep = diagnose_frame(df, None, None, baseline)
        res = rep.get("result") or rep.get("diagnosis_result")
        r["实际结论"] = res
        r["实际诊断"] = "；".join(c["name"] for c in rep.get("causes", [])) or rep.get("summary", "")
        r["是否符合"] = "是" if res == r["预期结论"] else ("偏严" if res == "abnormal" else "否")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path, help="健康数据目录（含 15-25 / 27-30 / 36-38 / 45-50 摄氏度子目录）")
    ap.add_argument("--out", type=Path, required=True, help="输出目录")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--no-diagnose", action="store_true", help="只生成，不跑诊断")
    args = ap.parse_args(argv)
    rows = generate(args.src, args.out, args.seed)
    if not args.no_diagnose:
        diagnose(args.out, rows)
    with open(args.out / "故障清单.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r["文件"], r.get("实际结论", ""), r.get("是否符合", ""), r.get("实际诊断", ""), sep=" | ")
    if not args.no_diagnose:
        ok = sum(r["是否符合"] == "是" for r in rows)
        print(f"\n{ok}/{len(rows)} 与预期一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
