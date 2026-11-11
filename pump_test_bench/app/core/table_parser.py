"""文本数据文件（试验台导出的 .txt / .csv）的容错解析。

试验台不同版本、不同导出方式的文件格式并不统一，这里不假设固定格式，而是逐项识别：

- 编码：带 BOM 的 UTF-8 / UTF-16；否则先试 UTF-8，再用 GB18030（兼容 GBK/GB2312）；
- 分隔符：在前几行里比较制表符、逗号、分号、竖线，取“每行字段数最一致且大于 1”的那个；
  都不合适时按连续空白分隔；
- 表头：第一行非空行像不像列名（不是时间、大部分不是数字）。没有表头时：
  先在同目录的其他文件里找列数相同的表头（同一台试验台导出的文件格式一致），
  再按列数匹配 known_headers 中的标准表头，最后退回“列1、列2……”；
- 空行：任意位置的空行都跳过（不再假设“第 2、3 行固定为空”）；
- 列数：按分隔符个数判断。分隔符够数的行是完整行（行尾多余的分隔符截掉，空值保留为空）；
  分隔符不够的行视为没写完（文件正在写入时最后一行常见），丢弃并计数；
  多出来的列里有内容的行视为格式错误，丢弃并计数；
- 文件中间重复出现的表头行：跳过；
- 列名：全角转半角、去掉首尾空白，末尾括号里的单位单独记下（如“供油压力1-1(MPa)”）；
- 时间：支持 “时:分:秒.毫秒”“分:秒.毫秒”、不补零的写法（17:3:36.243）、带日期前缀，
  以及纯数字秒数，统一换算为“当天秒数”。

整文件读取（read_text_table）和增量读取（TailReader，用于实时监控正在写入的文件）共用同一套规则。
"""
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from pump_test_bench.app.core.known_headers import KNOWN_HEADERS

logger = logging.getLogger(__name__)

TEXT_SUFFIXES = (".txt", ".csv")
TIME_COLUMN_NAMES = ("时间", "time", "Time", "TIME", "时刻")
SNIFF_BYTES = 64 * 1024
_DELIMITERS = ("\t", ",", ";", "|")
_UNIT_RE = re.compile(r"^(.*?)\s*[\(\[（【]\s*([^\)\]）】]*)\s*[\)\]）】]\s*$")
_TIME_RE = re.compile(
    r"^(?:(?P<date>\d{4}[-/.]\d{1,2}[-/.]\d{1,2})[ T])?"
    r"(?:(?P<h>\d{1,2}):)?(?P<m>\d{1,2}):(?P<s>\d{1,2}(?:\.\d+)?)$"
)
_NUMBER_RE = re.compile(r"^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$")


# --------------------------------------------------------------------------- 基础识别
def decode_bytes(data: bytes, encoding: Optional[str] = None) -> Tuple[str, str]:
    """解码字节，返回 (文本, 编码)。传入 encoding 时直接使用（增量读取时保持一致）。"""
    if encoding:
        return data.decode(encoding, errors="replace"), encoding
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace"), "utf-16"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError as exc:
        # 截断位置可能正好落在多字节字符中间：只有最后几个字节出错时仍认为是 UTF-8
        if exc.start >= len(data) - 3:
            return data[:exc.start].decode("utf-8"), "utf-8"
    return data.decode("gb18030", errors="replace"), "gb18030"


def detect_delimiter(lines: Sequence[str]) -> Optional[str]:
    """返回分隔符；None 表示按连续空白分隔。"""
    sample = [ln for ln in lines if ln.strip()][:20]
    best, best_score = None, 0.0
    for delim in _DELIMITERS:
        counts = [len(ln.rstrip(delim).split(delim)) for ln in sample]
        if not counts or max(counts) < 2:
            continue
        most = max(set(counts), key=counts.count)
        score = counts.count(most) / len(counts) * min(most, 50)  # 一致性 × 列数
        if score > best_score:
            best, best_score = delim, score
    return best


def split_line(line: str, delimiter: Optional[str]) -> List[str]:
    line = line.rstrip("\r\n")
    fields = line.split(delimiter) if delimiter else line.split()
    fields = [f.strip() for f in fields]
    while fields and fields[-1] == "":  # 行尾多余的分隔符
        fields.pop()
    return fields


def is_number(text: str) -> bool:
    return bool(_NUMBER_RE.match(text.strip()))


def parse_time(text: str) -> Optional[float]:
    """把时间文本换算为当天秒数；纯数字按秒处理；无法识别返回 None。"""
    text = (text or "").strip()
    if not text:
        return None
    m = _TIME_RE.match(text)
    if m:
        h = int(m.group("h") or 0)
        return h * 3600 + int(m.group("m")) * 60 + float(m.group("s"))
    if is_number(text):
        return float(text)
    return None


def looks_like_header(fields: Sequence[str]) -> bool:
    if not fields:
        return False
    if parse_time(fields[0]) is not None and not is_number(fields[0]):
        return False  # 第一列是时间 → 数据行
    numeric = sum(1 for f in fields if is_number(f))
    return numeric <= len(fields) * 0.3


def normalize_column(name: str) -> Tuple[str, str]:
    """列名规范化，返回 (列名, 单位)。"""
    name = unicodedata.normalize("NFKC", name or "").replace("\ufeff", "").strip()
    name = re.sub(r"\s+", " ", name)
    unit = ""
    m = _UNIT_RE.match(name)
    if m and m.group(1):
        name, unit = m.group(1).strip(), m.group(2).strip()
    return name, unit


def _dedupe(columns: List[str]) -> List[str]:
    seen: Dict[str, int] = {}
    result = []
    for i, col in enumerate(columns):
        col = col or f"列{i + 1}"
        if col in seen:
            seen[col] += 1
            col = f"{col}_{seen[col]}"
        else:
            seen[col] = 0
        result.append(col)
    return result


# --------------------------------------------------------------------------- 格式识别
@dataclass
class Layout:
    encoding: str
    delimiter: Optional[str]
    columns: List[str]
    units: Dict[str, str] = field(default_factory=dict)
    has_header: bool = True
    header_source: str = "file"  # file / sibling:<文件名> / known / generic
    time_column: Optional[str] = None

    @property
    def width(self) -> int:
        return len(self.columns)


def _header_from_siblings(path: Path, width: int, delimiter: Optional[str]) -> Optional[Tuple[List[str], str]]:
    """在同目录（按修改时间从近到远）的其他文件里找列数相同的表头。"""
    try:
        siblings = sorted(
            (p for p in path.parent.iterdir()
             if p != path and p.is_file() and p.suffix.lower() in TEXT_SUFFIXES),
            key=lambda p: abs(p.stat().st_mtime - path.stat().st_mtime),
        )[:30]
    except OSError:
        return None
    for sib in siblings:
        try:
            with sib.open("rb") as f:
                text, _ = decode_bytes(f.read(8192))
        except OSError:
            continue
        first = next((ln for ln in text.splitlines() if ln.strip()), "")
        fields = split_line(first, delimiter)
        if len(fields) == width and looks_like_header(fields):
            return fields, sib.name
    return None


def infer_layout(path: Path, head: bytes) -> Optional[Layout]:
    """根据文件开头的字节识别格式；文件还没有完整的一行时返回 None。"""
    text, encoding = decode_bytes(head)
    lines = [ln for ln in text.splitlines()]
    if not head.endswith(b"\n") and lines:
        lines = lines[:-1]  # 最后一行可能没写完
    lines = [ln for ln in lines if ln.strip()]
    if not lines:
        return None
    delimiter = detect_delimiter(lines)
    first = split_line(lines[0], delimiter)

    if looks_like_header(first):
        raw, has_header, source = first, True, "file"
    else:
        width = max(len(split_line(ln, delimiter)) for ln in lines[:20])
        found = _header_from_siblings(path, width, delimiter)
        if found:
            raw, source = found[0], f"sibling:{found[1]}"
        else:
            known = next((h for h in KNOWN_HEADERS if len(h) == width), None)
            if known:
                raw, source = list(known), "known"
            else:
                raw = ["时间" if parse_time(first[0]) is not None else "列1"] + [f"列{i + 2}" for i in range(width - 1)]
                source = "generic"
        has_header = False
        logger.info("文件 %s 没有表头，使用 %s 的列名（%d 列）", path.name, source, width)

    columns, units = [], {}
    for name in raw:
        col, unit = normalize_column(name)
        columns.append(col)
        if unit:
            units[col] = unit
    columns = _dedupe(columns)
    time_col = next((c for c in columns if c in TIME_COLUMN_NAMES), None)
    return Layout(encoding, delimiter, columns, units, has_header, source, time_col)


# --------------------------------------------------------------------------- 行解析
@dataclass
class ParseStats:
    rows: int = 0
    short_rows: int = 0  # 列数不足（多为没写完的行）
    bad_rows: int = 0  # 列数超出且多余部分非空


def parse_lines(lines: Sequence[str], layout: Layout, stats: ParseStats) -> List[List[str]]:
    rows = []
    width = layout.width
    for line in lines:
        if not line.strip():
            continue
        line = line.rstrip("\r\n")
        raw = line.split(layout.delimiter) if layout.delimiter else line.split()
        if len(raw) < width:
            stats.short_rows += 1
            continue
        fields = [f.strip() for f in raw]
        if any(fields[width:]):
            stats.bad_rows += 1
            continue
        fields = fields[:width]
        if looks_like_header(fields):
            continue  # 表头行（文件开头或中途重复出现）
        rows.append(fields)
    stats.rows += len(rows)
    return rows


def read_text_table(path: Path) -> Tuple[Layout, List[List[str]], ParseStats]:
    """整文件读取，返回 (格式, 数据行, 统计)。"""
    data = path.read_bytes()
    layout = infer_layout(path, data[:SNIFF_BYTES] if len(data) > SNIFF_BYTES else data + b"\n")
    if layout is None:
        raise ValueError(f"文件 {path.name} 是空的")
    text, _ = decode_bytes(data, layout.encoding)
    stats = ParseStats()
    rows = parse_lines(text.splitlines(), layout, stats)
    if stats.short_rows or stats.bad_rows:
        logger.info("文件 %s：跳过 %d 个不完整行、%d 个格式错误行", path.name, stats.short_rows, stats.bad_rows)
    return layout, rows, stats


# --------------------------------------------------------------------------- 增量读取
class TailReader:
    """增量读取正在写入的文件：每次只读新增的完整行，没写完的半行留到下次。

    文件变小（被重写）时自动从头开始。UTF-16 文件不按字节切行，退化为整文件重读。
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.layout: Optional[Layout] = None
        self.offset = 0
        self._pending = b""
        self.stats = ParseStats()
        self._rows_seen = 0  # UTF-16 整文件重读时使用

    def read_new(self, final: bool = False) -> List[List[str]]:
        """读取新增的完整行。final=True 表示文件已写完，最后一行即使没有换行也一并解析。"""
        try:
            size = self.path.stat().st_size
        except OSError:
            return []
        if size < self.offset:  # 文件被截断或重写
            self.__init__(self.path)
        if self.layout is None:
            with self.path.open("rb") as f:
                head = f.read(SNIFF_BYTES)
            self.layout = infer_layout(self.path, head + (b"\n" if final else b""))
            if self.layout is None:
                return []
        if self.layout.encoding == "utf-16":
            return self._reread_all()
        if size == self.offset and not (final and self._pending):
            return []

        with self.path.open("rb") as f:
            f.seek(self.offset)
            chunk = f.read(size - self.offset)
        self.offset += len(chunk)
        data = self._pending + chunk
        cut = data.rfind(b"\n")
        if final:
            complete, self._pending = data, b""
        elif cut < 0:
            self._pending = data
            return []
        else:
            complete, self._pending = data[:cut + 1], data[cut + 1:]
        text = complete.decode(self.layout.encoding, errors="replace")  # utf-8-sig 会自动去掉 BOM
        return parse_lines(text.splitlines(), self.layout, self.stats)  # 表头行由 parse_lines 识别跳过

    def _reread_all(self) -> List[List[str]]:
        _, rows, stats = read_text_table(self.path)
        new = rows[self._rows_seen:]
        self._rows_seen = len(rows)
        self.stats = stats
        return new
