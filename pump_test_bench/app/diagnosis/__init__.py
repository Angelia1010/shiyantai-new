"""试验台诊断。

- config.py    诊断配置（管路与测点对应关系、阈值、密度模型），来自 pump_test_bench/config/bench.json
- signals.py   时间轴、稳定段识别
- checks.py    各项检查：传感器自检、流量计冗余比对、供回油平衡、质量-体积校核、零点、经验模型
- baseline.py  健康基准：用正常数据统计每个流量计的固有偏差与波动、拟合密度-温度关系
- engine.py    诊断入口：读文件 → 稳定段 → 各项检查 → 汇总结论
- faults.py    故障注入（验证诊断是否有效）
"""
