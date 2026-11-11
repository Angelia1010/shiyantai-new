"""数据路径校验。

前端传来的目录和文件名都必须落在 ``DATA_ROOTS`` 配置的数据根目录之内，
防止通过接口读取、列举或修改服务器上的任意文件。
"""
import os
from pathlib import Path
from typing import Iterable, Optional

from shared.config import get_settings


class PathNotAllowed(ValueError):
    pass


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([str(path), str(root)]) == str(root)
    except ValueError:  # Windows 上不同盘符
        return False


def resolve_data_dir(directory: Optional[str]) -> Path:
    """把用户给出的目录解析为绝对路径，并确认它在数据根目录内且存在。"""
    if not directory or not str(directory).strip():
        raise PathNotAllowed("缺少目录参数 path")
    path = Path(str(directory).strip()).expanduser()
    if not path.is_absolute():
        path = get_settings().data_roots[0] / path
    path = path.resolve()
    if not any(_is_within(path, root) for root in get_settings().data_roots):
        raise PathNotAllowed(f"目录不在允许的数据目录范围内：{directory}")
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
