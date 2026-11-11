"""试验数据文件读取。

支持的格式：
- Excel（.xlsx / .xls）：第 1 行为列名，读取第一个工作表；
- 文本（.txt / .csv，试验台导出的“曲线数据”）：编码、分隔符、表头等由 table_parser 自动识别，
  兼容没有表头、行尾多余分隔符、最后一行没写完等情况；
- TDMS：仅供大模型分析使用，按通道读取为矩阵。

解析后的表格按 (路径, 修改时间, 大小) 缓存，分页读取同一个文件时只解析一次。
"""
import math
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

import pandas as pd

from pump_test_bench.app.core.table_parser import TEXT_SUFFIXES, normalize_column, read_text_table

TABLE_SUFFIXES = (".xlsx", ".xls") + TEXT_SUFFIXES
TDMS_SUFFIXES = (".tdms",)

_CACHE_SIZE = 4
_cache: "OrderedDict[Tuple[str, float, int, Optional[str]], pd.DataFrame]" = OrderedDict()
_cache_lock = threading.Lock()


def _to_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """数值列转为浮点；整列都不是数值的（如“时间”）保留原文本。列名统一规范化。"""
    out = {}
    for col in df.columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().any() or df[col].isna().all():
            out[col] = converted
        else:
            out[col] = df[col]
    result = pd.DataFrame(out)
    result.columns = [normalize_column(str(c))[0] for c in result.columns]
    return result


def _read_text(path: Path) -> pd.DataFrame:
    layout, rows, _ = read_text_table(path)
    df = pd.DataFrame(rows, columns=layout.columns, dtype=str)
    return df.replace("", None)


def iter_excel_sheets(path: Path) -> Iterator[Tuple[str, pd.DataFrame]]:
    with pd.ExcelFile(path) as xl:
        for sheet in xl.sheet_names:
            yield sheet, _to_numeric(xl.parse(sheet, dtype=object))


def read_table(path: Path, sheet: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
    """读取整张表，返回 (工作表名, DataFrame)。文本文件的工作表名固定为 "data"。"""
    stat = path.stat()
    key = (str(path), stat.st_mtime, stat.st_size, sheet)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            sheet_name, df = _cache[key].attrs["sheet"], _cache[key]
            return sheet_name, df

    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        sheet_name, df = "data", _to_numeric(_read_text(path))
    elif suffix in (".xlsx", ".xls"):
        with pd.ExcelFile(path) as xl:
            if not xl.sheet_names:
                raise ValueError(f"文件 {path.name} 中没有工作表")
            sheet_name = sheet if sheet is not None else xl.sheet_names[0]
            if sheet_name not in xl.sheet_names:
                raise ValueError(f"文件 {path.name} 中没有工作表 {sheet_name}")
            df = _to_numeric(xl.parse(sheet_name, dtype=object))
    else:
        raise ValueError(f"不支持的文件类型：{path.name}")

    df.attrs["sheet"] = sheet_name
    with _cache_lock:
        _cache[key] = df
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return sheet_name, df


def _json_value(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):  # numpy 标量
        value = value.item()
        if isinstance(value, float) and math.isnan(value):
            return None
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def read_page(path: Path, page: int, page_size: int) -> Dict:
    """按行分页读取，返回 {sheet, page, page_size, total_rows, has_more, columns: {列名: [值...]}}。"""
    if page < 0:
        raise ValueError("page 不能小于 0")
    if not 1 <= page_size <= 5000:
        raise ValueError("page_size 必须在 1 到 5000 之间")
    sheet, df = read_table(path)
    start = page * page_size
    chunk = df.iloc[start:start + page_size]
    columns = {col: [_json_value(v) for v in chunk[col].tolist()] for col in chunk.columns}
    total = len(df)
    return {
        "file_name": path.name,
        "sheet": sheet,
        "page": page,
        "page_size": page_size,
        "total_rows": total,
        "has_more": start + page_size < total,
        "columns": columns,
    }


def find_column(columns: List[str], keyword: str) -> Optional[str]:
    """返回第一个包含关键字的列名。"""
    for col in columns:
        if keyword in str(col):
            return col
    return None


def read_tdms_matrix(path: Path):
    """读取 TDMS 文件的全部通道，返回 (二维数组[样本, 通道], 通道名列表)。"""
    import numpy as np
    from nptdms import TdmsFile  # 只有大模型分析需要，按需导入

    tdms = TdmsFile.read(str(path))
    series, names = [], []
    for group in tdms.groups():
        for channel in group.channels():
            series.append(np.asarray(channel[:], dtype=float))
            names.append(f"{group.name}_{channel.name}")
    if not series:
        raise ValueError(f"文件 {path.name} 中没有任何通道数据")
    length = max(len(s) for s in series)
    padded = [np.pad(s, (0, length - len(s)), constant_values=np.nan) for s in series]
    return np.column_stack(padded), names
