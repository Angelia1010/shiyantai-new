"""仿真模型（健康参考模型）：给定工况，给出健康系统各测点的预期值。

- config.py      读取 config/simulation.json
- models.py      模型：数据代理模型（surrogate，由正常数据拟合）与 AMESim 模型（amesim）
- table.py       仿真基准表：在工况网格上运行模型，在线诊断时插值
- calibration.py 用正常数据标定“模型 vs 实测”的固有偏差与离散
- check.py       诊断时的模型残差检查
"""
