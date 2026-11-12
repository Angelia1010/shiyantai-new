"""仿真模型注册表。

- 内置模型：pump_test_bench/config/simulation/*.json（随代码提供，可用环境变量 SIM_CONFIG_DIR 指定目录）；
- 自定义模型：<DB_PATH 所在目录>/simulation_models/*.json，前端“仿真模型”页新建或修改的都保存在这里。
  与内置模型同 id 时覆盖内置配置（删除后恢复内置配置）。

加一个模型 = 加一份配置 + 建一张基准表，诊断代码不用改。按文件修改时间缓存。
"""
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_SIM_DIR = Path(__file__).resolve().parents[2] / "config" / "simulation"
ENGINES = ("surrogate", "amesim")
KINDS = {"flow": "流量", "pressure": "压力", "temperature": "温度", "torque": "扭矩", "speed": "转速", "other": "其他"}
DEFAULT_FLOORS = {  # 阈值下限：相对偏差（温度为绝对偏差 ℃）
    "flow": (0.025, 0.04), "pressure": (0.04, 0.07), "temperature": (3.0, 5.0), "torque": (0.15, 0.25),
    "speed": (0.03, 0.05), "other": (0.05, 0.08),
}
DEFAULT_ABS_FLOORS = {  # 绝对偏差的阈值下限（按单位）：近零的量（无流量管路、恒定压力）用绝对偏差比较
    "flow": (5.0, 10.0), "pressure": (0.02, 0.04), "temperature": (3.0, 5.0), "torque": (0.3, 0.6),
    "speed": (50.0, 100.0), "other": (1.0, 2.0),
}
_lock = threading.Lock()
_cache: Dict[str, Tuple[float, Dict]] = {}


def sim_config_dir() -> Path:
    value = os.environ.get("SIM_CONFIG_DIR", "").strip()
    return Path(value) if value else DEFAULT_SIM_DIR


def user_model_dir() -> Optional[Path]:
    try:
        from shared.config import get_settings
        return get_settings().db_path.parent / "simulation_models"
    except Exception:  # 没有服务配置（离线工具）时只有内置模型
        return None


def _load(path: Path) -> Dict:
    mtime = path.stat().st_mtime
    with _lock:
        cached = _cache.get(str(path))
        if cached and cached[0] == mtime:
            return cached[1]
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"仿真模型配置格式错误：{path.name}（{exc}）") from None
    for key in ("id", "name", "engine", "inputs", "outputs"):
        if not cfg.get(key):
            raise ValueError(f"仿真模型配置 {path.name} 缺少 {key}")
    with _lock:
        _cache[str(path)] = (mtime, cfg)
    return cfg


def _dir_models(d: Optional[Path]) -> Dict[str, Dict]:
    if not d or not d.exists():
        return {}
    return {m["id"]: m for m in (_load(p) for p in sorted(d.glob("*.json")))}


def list_models() -> List[Dict]:
    builtin = _dir_models(sim_config_dir())
    custom = _dir_models(user_model_dir())
    out = []
    for mid in dict.fromkeys(list(builtin) + list(custom)):
        if mid in custom:
            cfg = dict(custom[mid])
            cfg["_source"] = "override" if mid in builtin else "custom"
        else:
            cfg = dict(builtin[mid])
            cfg["_source"] = "builtin"
        out.append(cfg)
    return sorted(out, key=lambda m: (m.get("order", 99), m["id"]))


def load_model_cfg(model_id: str) -> Dict:
    for m in list_models():
        if m["id"] == model_id:
            return m
    raise ValueError(f"没有这个仿真模型：{model_id}")


def builtin_ids() -> List[str]:
    return list(_dir_models(sim_config_dir()))


def input_names(cfg: Dict) -> List[str]:
    return [i["name"] for i in cfg["inputs"]]


def output_names(cfg: Dict) -> List[str]:
    return [o["name"] for o in cfg["outputs"]]


def find_output(cfg: Dict, name: str) -> Optional[Dict]:
    return next((o for o in cfg["outputs"] if o["name"] == name), None)


def residual_mode(output: Dict) -> str:
    """relative：相对偏差（流量、压力）；absolute：绝对偏差（温度，零点没有物理意义）。"""
    return output.get("residual") or ("absolute" if output.get("kind") == "temperature" else "relative")


def signature(cfg: Dict) -> str:
    """影响基准表的配置（引擎、输入、输出）的摘要；配置改了而基准表没重建时，基准表作废。"""
    key = {"inputs": [{k: i.get(k) for k in ("name", "column", "columns", "derived", "temperature_column", "grid")}
                      for i in cfg["inputs"]],
           "outputs": [{k: o.get(k) for k in ("name", "columns", "kind", "residual")} for o in cfg["outputs"]]}
    return hashlib.sha1(json.dumps(key, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- 前端编辑：校验与保存
def _num_list(value, what: str) -> List[float]:
    if isinstance(value, str):
        value = [v for v in re.split(r"[,，\s]+", value.strip()) if v]
    try:
        nums = [float(v) for v in value or []]
    except (TypeError, ValueError):
        raise ValueError(f"{what} 只能填数字") from None
    return nums


def validate_model(data: Dict, existing_id: Optional[str] = None) -> Dict:
    """校验前端提交的模型配置，补全默认值，返回可保存的配置。"""
    if not isinstance(data, dict):
        raise ValueError("模型配置格式错误")
    cfg = {k: v for k, v in data.items() if not k.startswith("_") and k not in ("table", "setting", "engines")}
    mid = str(existing_id or cfg.get("id") or "").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,39}", mid):
        raise ValueError("模型编号只能用英文字母开头，由字母、数字、下划线、短横线组成（2–40 个字符）")
    cfg["id"] = mid
    cfg["name"] = str(cfg.get("name") or "").strip()
    if not cfg["name"]:
        raise ValueError("请填写模型名称")
    engine = (cfg.get("engine") or {}).get("type", "surrogate") if isinstance(cfg.get("engine"), dict) else cfg.get("engine")
    if engine not in ENGINES:
        raise ValueError("模型方式只能是数据代理模型（surrogate）或 AMESim 模型（amesim）")
    cfg["engine"] = {"type": engine}
    if cfg.get("default_mode", "decisive") not in ("decisive", "reference", "off"):
        raise ValueError("默认参与方式只能是 decisive、reference 或 off")
    cfg["components"] = [str(c) for c in cfg.get("components") or []]

    inputs = cfg.get("inputs") or []
    if not inputs:
        raise ValueError("至少要有一个输入（工况）")
    names = set()
    for k, i in enumerate(inputs, 1):
        i["name"] = str(i.get("name") or "").strip()
        if not i["name"] or i["name"] in names:
            raise ValueError(f"第 {k} 个输入的名称为空或重复")
        names.add(i["name"])
        if i.get("derived") == "density":
            if not i.get("temperature_column"):
                raise ValueError(f"输入“{i['name']}”由油温计算密度，请选择油温测点")
            i.pop("column", None), i.pop("columns", None)
        elif i.get("columns") and len(i["columns"]) > 1:
            i["aggregate"] = "median"
            i.pop("column", None), i.pop("derived", None)
        else:
            col = i.get("column") or (i.get("columns") or [None])[0]
            if not col:
                raise ValueError(f"输入“{i['name']}”请选择测点")
            i["column"] = col
            i.pop("columns", None), i.pop("derived", None)
        grid = sorted(set(_num_list(i.get("grid"), f"输入“{i['name']}”的网格")))
        if len(grid) < 2:
            raise ValueError(f"输入“{i['name']}”的网格至少要有 2 个点（覆盖正常数据的工况范围）")
        i["grid"] = grid
        if i.get("valid") not in (None, "", []):
            v = _num_list(i["valid"], f"输入“{i['name']}”的有效范围")
            if len(v) != 2 or v[0] >= v[1]:
                raise ValueError(f"输入“{i['name']}”的有效范围应为 下限,上限")
            i["valid"] = v
        else:
            i.pop("valid", None)
        i["fallback_columns"] = [c for c in i.get("fallback_columns") or [] if c]
        if not i["fallback_columns"]:
            i.pop("fallback_columns")
    n_feat = 1 + 2 * len(inputs) + len(inputs) * (len(inputs) - 1) // 2
    if engine == "surrogate" and len(inputs) > 4:
        raise ValueError(f"数据代理模型最多 4 个输入（每个输出要拟合 {n_feat} 个系数，需要足够多的正常数据）")

    outputs = cfg.get("outputs") or []
    if not outputs:
        raise ValueError("至少要有一个输出")
    onames = set()
    for k, o in enumerate(outputs, 1):
        o["name"] = str(o.get("name") or "").strip()
        if not o["name"] or o["name"] in onames or o["name"] in names:
            raise ValueError(f"第 {k} 个输出的名称为空、重复或与输入同名")
        onames.add(o["name"])
        if o.get("kind", "other") not in KINDS:
            raise ValueError(f"输出“{o['name']}”的类型无效")
        o["kind"] = o.get("kind", "other")
        o["columns"] = [c for c in o.get("columns") or [] if c]
        if not o["columns"]:
            raise ValueError(f"输出“{o['name']}”请选择对应的测点（同一处的多只表可以一起选）")
        if o.get("residual") not in (None, "", "relative", "absolute"):
            raise ValueError(f"输出“{o['name']}”的比较方式只能是 relative 或 absolute")
        o["residual"] = residual_mode(o)
        if o.get("single", "decisive") not in ("decisive", "notice"):
            raise ValueError(f"输出“{o['name']}”的单测点判定只能是 decisive 或 notice")

    rules = cfg.get("rules") or {}
    rule = rules.get("group_shift")
    if rule:
        targets = rule.get("outputs") or ([rule["output"]] if rule.get("output") else [])
        if not targets or any(t not in onames for t in targets):
            raise ValueError("整体偏移规则请选择模型中已有的输出")
        if rule.get("meaning", "pump") not in ("pump", "reference", "input"):
            raise ValueError("整体偏移的含义只能是 pump、reference 或 input")
        if rule.get("meaning") == "input" and rule.get("input") not in names:
            raise ValueError("整体偏移含义为“模型输入测点偏差”时，请选择对应的输入")
        rule["min_columns"] = int(rule.get("min_columns") or 3)
        if len(targets) == 1:
            rule["output"] = targets[0]
            rule.pop("outputs", None)
        else:
            rule["outputs"] = targets
            rule.pop("output", None)
        cfg["rules"] = {"group_shift": rule}
    else:
        cfg["rules"] = {}

    th = cfg.get("thresholds") or {}
    kinds = {o["kind"] for o in outputs}
    th["sigma_warn"] = float(th.get("sigma_warn") or 3)
    th["sigma_alarm"] = float(th.get("sigma_alarm") or 5)
    if th["sigma_alarm"] < th["sigma_warn"]:
        raise ValueError("异常倍数不能小于预警倍数")
    fw, fa = dict(th.get("floor_warn") or {}), dict(th.get("floor_alarm") or {})
    for kind in kinds:
        fw.setdefault(kind, DEFAULT_FLOORS[kind][0])
        fa.setdefault(kind, DEFAULT_FLOORS[kind][1])
    th["floor_warn"], th["floor_alarm"] = fw, fa
    cfg["thresholds"] = th

    ame = cfg.get("amesim") or {}
    if engine == "amesim":
        if not ame.get("model_file"):
            raise ValueError("AMESim 模型请填写模型文件名（放在 AMESim 服务的模型目录中）")
        variables = ame.get("variables") or {}
        missing = [o["name"] for o in outputs if not str(variables.get(o["name"]) or "").strip()]
        if missing:
            raise ValueError(f"AMESim 模型请填写输出的变量路径：{'、'.join(missing)}")
        for p in ame.get("parameters") or []:
            if p.get("input") not in names:
                raise ValueError(f"AMESim 参数映射引用了不存在的输入：{p.get('input')}")
            if p.get("derive") not in (None, "", "temperature", "density", "viscosity"):
                raise ValueError("AMESim 参数的换算只能是 temperature、density 或 viscosity")
            if p.get("kind") not in ("component", "global", "input_table"):
                raise ValueError("AMESim 参数的设置方式只能是 component、global 或 input_table")
            if p["kind"] != "input_table":
                p["params"] = [x for x in (p.get("params") or []) if x] if isinstance(p.get("params"), list) \
                    else [x.strip() for x in str(p.get("params") or "").split(",") if x.strip()]
                if not p["params"]:
                    raise ValueError(f"AMESim 参数映射（输入“{p['input']}”）请填写参数路径")
    cfg["amesim"] = ame
    conds = []
    for c in cfg.get("active_if") or []:
        if not c.get("column"):
            continue
        item = {"column": c["column"]}
        for key in ("min", "max"):
            if c.get(key) not in (None, ""):
                item[key] = float(c[key])
        if c.get("note"):
            item["note"] = str(c["note"])
        conds.append(item)
    cfg["active_if"] = conds
    return cfg


def save_user_model(cfg: Dict) -> Path:
    d = user_model_dir()
    if d is None:
        raise ValueError("没有服务配置，不能保存自定义模型")
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{cfg['id']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def delete_user_model(model_id: str) -> bool:
    d = user_model_dir()
    path = d / f"{model_id}.json" if d else None
    if path and path.exists():
        path.unlink()
        return True
    return False
