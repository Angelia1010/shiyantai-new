"""仿真模型（健康参考模型）：给定工况，给出健康系统各测点的预期值。

- config.py      模型配置（内置 config/simulation/*.json + 页面上新建/修改的）与校验
- condition.py   从稳定段取变量（测点、中位数、由油温算密度/黏度、常数，再做单位换算）
- builders/      数据代理模型的构建器注册表：autofit（按变量角色定结构）、formula（内置公式，仅后端配置），可扩展
- surrogate.py   数据代理模型的通用流程：拟合 → 留一组交叉验证 → 误差、异常样本、建议 → 公式产物
- formula.py     公式引擎：白名单解析、计算、系数拟合
- models.py      网格类仿真引擎（AMESim），可注册新引擎
- table.py       模型产物（grid 插值 / formula 直接计算）的读写与预测
- calibration.py 用正常数据标定“模型 vs 实测”的固有偏差与离散
- check.py       诊断时的模型残差检查
- service.py     对外接口的编排
扩展方式见 docs/扩展指南.md。
"""
