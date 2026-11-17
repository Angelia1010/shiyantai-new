"""试验台诊断（只使用 config/bench.json 中的 9 个信号）。

- config.py          诊断配置（信号、阈值、隔离与二级诊断参数），来自 pump_test_bench/config/bench.json
- bench_signals.py   诊断信号及其在管路中的角色
- signals.py         时间轴、稳定段识别
- checks.py          基础统计与发现的格式
- sensor_checks.py   单信号自检（卡死、冻结、掉零、超量程、噪声、毛刺、P1 偏离设定）
- expectation.py     各信号健康时的预期值（仿真模型 + 固有偏差）
- changepoint.py     稳定段内的突变 / 渐变检测
- isolation.py       故障隔离的数学部分（假设检验 + 加权最小二乘）
- hypotheses.py      标准台的故障假设目录（每种原因让哪些信号怎样变化）与描述
- turbine_check.py   涡轮流量计二级诊断（用涡轮流量计模型复核被怀疑的流量计）
- flow_diagnosis.py  主油路流量诊断的流程：变点 → 隔离 → 二级诊断 → 发现与管路摘要
- section_checks.py  分段检查：供油段压差（P9）、温升（回油温度）
- causes.py          原因推断：把现象归并为故障原因
- history.py         诊断历史：长期漂移
- baseline.py        健康基准：各观测量的健康离散、两表固有差异、涡轮流量计模型标定、密度模型
- engine.py          诊断入口：读文件 → 稳定段 → 自检 → 模型预期 → 隔离 → 分段检查 → 汇总结论
- faults.py          简单的故障注入（验证诊断是否有效；按机理的完整注入见 tools/generate_fault_data.py）
"""
