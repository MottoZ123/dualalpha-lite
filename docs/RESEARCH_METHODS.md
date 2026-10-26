# 双轨因子与模型实现说明

原始设计把趋势/价格与成本/量价两套信息分开建模，再比较同日预测。科技成长和主板使用不同因子，见 FACTOR_CATALOG.md。

| 训练脚本 | 输出目录 |
|---|---|
| train_tx.py | models_tx |
| train_advanced.py | models |
| train_mainboard_tx.py | models_tx_v7 |
| train_mainboard_bs.py | models_bs_v6 |

基础模型为 XGBoost、LightGBM、CatBoost 与 PyTorch Transformer；逻辑回归融合四类输出。以 train_tx.py 为例，StandardScaler 在前 80% 样本拟合，基模型在这一段训练；后段预测用于 meta model 拟合。代码注释称 OOF，但此实现是时间保留段 stacking，不能把同一 meta 训练段作为最终独立测试。新数据上的校准、泛化与因子增量价值仍需独立评估。

`daily_agent_tx.py` / `daily_agent_bs.py` 按板块加载 scaler 和对应模型，`ab_test_DeepSeek.py` 生成结构化双轨归档与可选文字报告。53% 一致性阈值沿用旧研究设置，不是已证明有效的交易阈值。

`factor_backtest.py` 的因子研究和历史双周期案例与原始四模型预测不是同一个实验，不能混用其性能结论。T+1 关注命中率不等价于每日可成交收益；T+5 需明确持有间隔和成本。历史审计已发现 T+1 整体未形成稳定跑赢优势，T+5 回撤较大。本次仅保留代码，不重新运行或推广这些结果。

SHAP 图说明模型对特征的依赖，不直接证明因果作用。原始权重、训练数据和个人报告不随公共源码交付。
