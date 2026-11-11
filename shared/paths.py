"""数据目录管理与路径校验。

允许访问的数据目录有两个来源：
1. ``.env`` 的 ``DATA_ROOTS``（可选，部署时预置）；
2. 在前端登记的目录（工作台“数据目录”、自动诊断配置页），保存在
   ``<DB_PATH 所在目录>/data_dirs.json``，所有后端服务共用，修改后立即生效。

前端传来的目录和文件名都必须落在这些目录之内，防止通过接口读取服务器上的任意文件。
登记目录时要求目录真实存在，且不能是磁盘根目录或系统目录。
"""
import json
import os
import threading
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from shared.config import get_settings


class PathNotAllowed(ValueError):
    pass


# 不允许登记的系统目录（及其子目录）
_FORBIDDEN_WINDOWS = ("windows", "program files", "program files (x86)", "programdata")
_FORBIDDEN_POSIX = ("/bin", "/boot", "/dev", "/etc", "/lib", "/lib64", "/proc", "/root", "/run",
                    "/sbin", "/sys", "/usr", "/var/lib", "/var/run")

_lock = threading.Lock()
_cache: Dict[str, Tuple[float, List[Path]]] = {}


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([str(path), str(root)]) == str(root)
    except ValueError:  # Windows 上不同盘符
        return False


# --------------------------------------------------------------------------- 登记的目录
def _store_file() -> Path:
    return get_settings().db_path.parent / "data_dirs.json"


def registered_dirs() -> List[Path]:
    """前端登记的目录（按文件修改时间缓存，其他服务登记后这里自动看到）。"""
    store = _store_file()
    try:
        mtime = store.stat().st_mtime
    except OSError:
        return []
    with _lock:
        cached = _cache.get(str(store))
        if cached and cached[0] == mtime:
            return list(cached[1])
        try:
            paths = [Path(p) for p in json.loads(store.read_text(encoding="utf-8")).get("dirs", [])]
        except (OSError, ValueError):
            paths = []
        _cache[str(store)] = (mtime, paths)
        return list(paths)


def _save_registered(paths: List[Path]) -> None:
    store = _store_file()
    store.parent.mkdir(parents=True, exist_ok=True)
    tmp = store.with_suffix(".tmp")
    tmp.write_text(json.dumps({"dirs": [str(p) for p in paths]}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, store)


def allowed_roots() -> List[Path]:
    roots = list(get_settings().data_roots)
    for p in registered_dirs():
        if p not in roots:
            roots.append(p)
    return roots


def _check_registrable(path: Path) -> None:
    if path.drive.startswith("\\\\") or str(path).startswith("//"):
        return  # 网络共享（\\主机\共享名）本身就是一个目录，允许
    if path == Path(path.anchor):
        raise PathNotAllowed(f"不能使用磁盘根目录：{path}，请选择具体的数据目录")
    if os.name == "nt":
        parts = [p.lower() for p in path.parts[1:2]]
        if parts and parts[0] in _FORBIDDEN_WINDOWS:
            raise PathNotAllowed(f"不能使用系统目录：{path}")
    else:
        if any(_is_within(path, Path(f)) for f in _FORBIDDEN_POSIX):
            raise PathNotAllowed(f"不能使用系统目录：{path}")


def register_data_dir(directory: Optional[str]) -> Path:
    """登记一个数据目录（必须是已存在的绝对路径）。已在允许范围内的目录不重复登记。"""
    if not directory or not str(directory).strip():
        raise PathNotAllowed("请填写数据目录")
    path = Path(str(directory).strip()).expanduser()
    if not path.is_absolute():
        raise PathNotAllowed(f"请填写完整路径（如 D:/试验数据 或 //主机名/共享名）：{directory}")
    path = path.resolve()
    if not path.is_dir():
        raise PathNotAllowed(f"目录不存在或无法访问：{directory}")
    _check_registrable(path)
    if any(_is_within(path, root) for root in allowed_roots()):
        return path
    with _lock:
        _cache.clear()
    dirs = registered_dirs()
    # 新目录包含了已登记的子目录时，子目录不再单独保留
    dirs = [d for d in dirs if not _is_within(d, path)] + [path]
    _save_registered(dirs)
    with _lock:
        _cache.clear()
    return path


def unregister_data_dir(directory: Optional[str]) -> None:
    path = Path(str(directory or "").strip()).expanduser()
    dirs = registered_dirs()
    remaining = [d for d in dirs if str(d) != str(path) and str(d) != str(path.resolve())]
    if len(remaining) == len(dirs):
        raise PathNotAllowed(f"该目录不是在前端登记的目录：{directory}")
    _save_registered(remaining)
    with _lock:
        _cache.clear()


# --------------------------------------------------------------------------- 路径解析
def resolve_data_dir(directory: Optional[str]) -> Path:
    """把用户给出的目录解析为绝对路径，并确认它在允许的数据目录内且存在。"""
    if not directory or not str(directory).strip():
        raise PathNotAllowed("缺少目录参数 path")
    roots = allowed_roots()
    path = Path(str(directory).strip()).expanduser()
    if not path.is_absolute():
        if not roots:
            raise PathNotAllowed(f"请填写完整路径：{directory}")
        path = roots[0] / path
    path = path.resolve()
    if not any(_is_within(path, root) for root in roots):
        raise PathNotAllowed(f"目录尚未登记为数据目录：{directory}（请先在“数据目录”中添加）")
    if not path.is_dir():
        raise PathNotAllowed(f"目录不存在：{directory}")
    return path


def resolve_data_file(directory: Optional[str], file_name: Optional[str], allowed_suffixes: Iterable[str]) -> Path:
    """解析目录下的一个文件。

    file_name 可以是相对于该目录的子路径（如 “36-38摄氏度/S1295-P0.10.txt”，正反斜杠均可），
    但不能是绝对路径、不能含 “..”，解析后必须仍在该目录内。
    """
    base = resolve_data_dir(directory)
    name = (file_name or "").strip().replace("\\", "/")
    if not name:
        raise PathNotAllowed("缺少文件名参数 file_name")
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if not parts or name.startswith("/") or ":" in name or any(p == ".." for p in parts):
        raise PathNotAllowed(f"文件名不合法：{file_name}")
    suffixes = tuple(s.lower() for s in allowed_suffixes)
    if not parts[-1].lower().endswith(suffixes):
        raise PathNotAllowed(f"不支持的文件类型：{parts[-1]}（支持 {', '.join(suffixes)}）")
    path = base.joinpath(*parts).resolve()
    if not _is_within(path, base):
        raise PathNotAllowed(f"文件名不合法：{file_name}")
    if not path.is_file():
        raise PathNotAllowed(f"文件不存在：{name}")
    return path
