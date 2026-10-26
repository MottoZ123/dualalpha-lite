# 原始双轨因子清单

从本次发布的 quant/predict_tx.py / quant/predict_bs.py 静态提取，未重新训练或改写因子。

| 轨道 | 板块 | 数量 | 特征名 |
|---|---|---:|---|
| TX | 科技成长 | 13 | Relative_Strength、Return_5、BIAS_20、BIAS_60、Vol_Ratio、Norm_ATR_14、Entity_Ratio、Boll_Width、Realized_Vol_20、PV_Corr_10、Overnight_Return、CMF_20、Trend_Strength_20 |
| TX | 主板 | 10 | Relative_Strength_20、MACD_Hist_Norm、Z_Score_20、ATR_Ratio_14_60、Price_EMA_Bias_20、Return_5、Return_20、Williams_R_14、CCI_14、Candle_Shape |
| BS | 科技成长 | 13 | Relative_Strength、Turn、Return_5、BIAS_20、BIAS_60、Vol_Ratio、Norm_ATR_14、Entity_Ratio、Price_Cost_Bias、Boll_Width、Realized_Vol_20、PV_Corr_10、Overnight_Return |
| BS | 主板 | 10 | Relative_Strength_20、MACD_Hist_Norm、Z_Score_20、ATR_Ratio_14_60、Vol_Surge_60、Price_VWAP_Bias、MFI_14、Amihud_Illiquidity、Return_5、Return_20 |
