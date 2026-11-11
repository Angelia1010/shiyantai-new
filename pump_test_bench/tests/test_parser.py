"""数据文件容错解析与增量读取。"""
from pump_test_bench.app.core.data_reader import read_table
from pump_test_bench.app.core.known_headers import HEADER_V1
from pump_test_bench.app.core.live_monitor import FrameAggregator
from pump_test_bench.app.core.table_parser import TailReader, parse_time, read_text_table
from pump_test_bench.tests.conftest import SAMPLES

STANDARD_SAMPLES = SAMPLES / "标准台样例"


def test_parse_time_formats():
    assert parse_time("16:58:50.131") == 16 * 3600 + 58 * 60 + 50.131
    assert parse_time("17:3:36.243") == 17 * 3600 + 3 * 60 + 36.243  # 分钟不补零
    assert parse_time("14:36.842") == 14 * 60 + 36.842  # 分:秒
    assert parse_time("2026-11-02 17:03:36.5") == 17 * 3600 + 3 * 60 + 36.5
    assert parse_time("12.5") == 12.5
    assert parse_time("abc") is None and parse_time("") is None


def test_standard_bench_samples():
    layout, rows, stats = read_text_table(STANDARD_SAMPLES / "S1295-P0.10.txt")
    assert layout.encoding == "gb18030" and layout.delimiter == "\t"
    assert layout.width == 66 and len(rows) == 300 and stats.short_rows == 0

    # 表头被试验台软件覆盖掉的文件：从同目录文件借用表头，残留的表头碎片作为不完整行丢弃
    layout, rows, stats = read_text_table(STANDARD_SAMPLES / "S2990-P0.10-无表头.txt")
    assert layout.header_source == "sibling:S1295-P0.10.txt"
    assert rows[0][0] == "17:6:11.852" and stats.short_rows == 1

    _, df = read_table(STANDARD_SAMPLES / "S1295-P0.10-末行未写完.txt")
    assert len(df) == 150 and df["回油质量流量1"].dtype.kind == "f"


def test_csv_with_bom_units_blank_and_repeated_header(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes("\ufeff时间,供油压力1-1(MPa),回油流量1-1（L/h）,\n\n"
                  "10:00:00.0,0.1,150,\n10:00:00.5,0.2,,\n"
                  "时间,供油压力1-1(MPa),回油流量1-1（L/h）,\n10:00:01.0,0.3,151,\n10:00:01".encode("utf-8"))
    layout, rows, stats = read_text_table(p)
    assert layout.columns == ["时间", "供油压力1-1", "回油流量1-1"]
    assert layout.units == {"供油压力1-1": "MPa", "回油流量1-1": "L/h"}
    assert rows == [["10:00:00.0", "0.1", "150"], ["10:00:00.5", "0.2", ""], ["10:00:01.0", "0.3", "151"]]
    assert stats.short_rows == 1


def test_headerless_file_falls_back_to_known_header(tmp_path):
    row = "\t".join(["14:36.842"] + ["1.0"] * 64) + "\t\n"
    p = tmp_path / "solo.txt"
    p.write_bytes((row * 3).encode("gbk"))
    layout, rows, _ = read_text_table(p)
    assert layout.header_source == "known" and layout.columns == HEADER_V1 and len(rows) == 3


def test_whitespace_delimited(tmp_path):
    p = tmp_path / "b.txt"
    p.write_bytes("时间   转速   压力\n00:01.0  100  0.1\n00:01.1  101  0.2\n".encode("gbk"))
    layout, rows, _ = read_text_table(p)
    assert layout.delimiter is None and layout.columns == ["时间", "转速", "压力"] and len(rows) == 2


def test_tail_reader_handles_partial_writes(tmp_path):
    p = tmp_path / "tail.txt"
    header = "时间\t压力\t温度\t\n".encode("gbk")
    p.write_bytes(header[:5])  # 中文字符被拆成两次写入
    reader = TailReader(p)
    assert reader.read_new() == []
    with p.open("ab") as f:
        f.write(header[5:] + b"\n10:00:00.0\t0.1\t20\t\n10:00:00.1\t0.")
    assert reader.read_new() == [["10:00:00.0", "0.1", "20"]]
    with p.open("ab") as f:
        f.write(b"2\t21\t\n10:00:00.2\t0.3\t22")
    assert reader.read_new() == [["10:00:00.1", "0.2", "21"]]
    assert reader.read_new(final=True) == [["10:00:00.2", "0.3", "22"]]
    p.write_bytes(header + b"10:00:05\t9\t9\t\n")  # 文件被重写（变小）：从头读
    assert reader.read_new() == [["10:00:05", "9", "9"]]


def test_frame_aggregator_windows_and_time_wrap(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("时间\t值\n59:59.5\t1\n59:59.9\t3\n00:00.2\t5\n", encoding="utf-8")  # 分:秒 过整点
    layout, rows, _ = read_text_table(p)
    agg = FrameAggregator(layout, window=1.0)
    frames = agg.add(rows)
    assert len(frames) == 1 and frames[0]["stats"]["值"] == {"avg": 2.0, "min": 1.0, "max": 3.0}
    last = agg.flush()
    assert last["rows"] == 1 and last["t"] == 3600.0
