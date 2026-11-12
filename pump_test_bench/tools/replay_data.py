"""按真实速度回放试验数据，模拟试验台往共享目录里边测边写文件。

没有试验台时用来测试工作台的实时显示和自动诊断：把已有的数据文件一行一行
（按时间列的间隔）追加写入目标目录。

用法（在仓库根目录执行）：
    python -m pump_test_bench.tools.replay_data 源文件或目录 --to 目标目录 [--speed 2] [--loop]

    源为目录时依次回放其中（含子目录）的所有 .txt/.csv 文件，子目录结构保留；
    --speed  回放倍速，默认 1（真实速度）；
    --loop   放完从头再来；
    --gap    两个文件之间停顿的秒数，默认 5（让监控把上一个文件判定为“写完”）。

回放开始后，在工作台“数据目录”里填写目标目录的完整路径即可（会自动登记）。
"""
import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

from pump_test_bench.app.core.table_parser import (
    TEXT_SUFFIXES, decode_bytes, detect_delimiter, looks_like_header, parse_time, split_line,
)

WRITE_INTERVAL = 0.2  # 每 0.2 秒写一批，接近试验台的写盘节奏
FALLBACK_RATE = 100.0  # 没有时间列时按 100 行/秒


def _source_files(source: Path) -> List[Path]:
    if source.is_file():
        return [source]
    return sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES)


def _row_time(line: bytes, encoding: str, delimiter: Optional[str]) -> Optional[float]:
    fields = split_line(line.decode(encoding, errors="replace"), delimiter)
    return parse_time(fields[0]) if fields else None


def replay_file(src: Path, dest: Path, speed: float, quiet: bool = False) -> None:
    raw = src.read_bytes()
    text, encoding = decode_bytes(raw[:65536])
    delimiter = detect_delimiter(text.splitlines())
    lines = raw.split(b"\n")
    # 开头的表头和空行一次写出
    head_end = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        fields = split_line(stripped.decode(encoding, errors="replace"), delimiter)
        if not looks_like_header(fields):
            head_end = i
            break
    else:
        head_end = len(lines)

    dest.parent.mkdir(parents=True, exist_ok=True)
    data_lines = lines[head_end:]
    total = len(data_lines)
    if not quiet:
        print(f"回放 {src.name} → {dest}（{total} 行，{speed:g} 倍速）")
    with dest.open("wb") as f:
        f.write(b"\n".join(lines[:head_end]) + (b"\n" if head_end else b""))
        f.flush()
        start_wall = time.monotonic()
        first_t: Optional[float] = None
        batch: List[bytes] = []
        last_flush = start_wall
        for n, line in enumerate(data_lines):
            t = _row_time(line, encoding, delimiter) if line.strip() else None
            if t is not None:
                first_t = t if first_t is None else first_t
                offset = t - first_t
            else:
                offset = n / FALLBACK_RATE
            # 等到这一行“该写”的时刻
            wait = start_wall + max(offset, 0) / speed - time.monotonic()
            if wait > 0:
                if batch:
                    f.write(b"\n".join(batch) + b"\n")
                    f.flush()
                    batch = []
                time.sleep(wait)
            batch.append(line)
            if time.monotonic() - last_flush >= WRITE_INTERVAL:
                f.write(b"\n".join(batch) + b"\n")
                f.flush()
                batch = []
                last_flush = time.monotonic()
                if not quiet:
                    print(f"\r  {n + 1}/{total} 行", end="", flush=True)
        if batch:
            f.write(b"\n".join(batch).rstrip(b"\n") + b"\n")
    if not quiet:
        print(f"\r  完成，共 {total} 行，用时 {time.monotonic() - start_wall:.1f} 秒")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="按真实速度回放试验数据，模拟试验台边测边写文件")
    parser.add_argument("source", type=Path, help="源数据文件或目录")
    parser.add_argument("--to", dest="target", type=Path, required=True, help="目标目录（被监控的目录）")
    parser.add_argument("--speed", type=float, default=1.0, help="回放倍速，默认 1")
    parser.add_argument("--loop", action="store_true", help="循环回放")
    parser.add_argument("--gap", type=float, default=5.0, help="文件之间停顿秒数，默认 5")
    args = parser.parse_args(argv)

    files = _source_files(args.source)
    if not files:
        print(f"没有找到数据文件：{args.source}", file=sys.stderr)
        return 1
    if args.speed <= 0:
        print("--speed 必须大于 0", file=sys.stderr)
        return 1
    base = args.source if args.source.is_dir() else args.source.parent
    try:
        while True:
            for src in files:
                replay_file(src, args.target / src.relative_to(base), args.speed)
                time.sleep(args.gap)
            if not args.loop:
                break
    except KeyboardInterrupt:
        print("\n已停止")
    return 0


if __name__ == "__main__":
    sys.exit(main())
