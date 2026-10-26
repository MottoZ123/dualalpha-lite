# DualAlpha-Lite · Motto 本地工作台

基于原有 TX/BS 双轨因子与机器学习预测系统，增加本地行情研究界面、FastAPI 服务、MCP 工具和结果追踪。原始预测核心由 XGBoost、LightGBM、CatBoost、Transformer 与逻辑回归融合层组成；大语言模型负责解释结构化证据。

本次为 **2026-10-26 本地源码整理版**，不是当天重新训练的模型或新收益验证。原有模型权重、个人自选状态、行情缓存和 API Key 不随源码发布。

## 原有双轨预测核心

| 系统 | 科技成长 | 主板 |
|---|---|---|
| TX | 趋势、资金流、形态；13 个特征；`models_tx/` | 价格结构、均值偏离与反转；10 个特征；`models_tx_v7/` |
| BS | 成本偏离、换手与量价关系；13 个特征；`models/` | VWAP、资金流与流动性；10 个特征；`models_bs_v6/` |

四类基础模型的预测输入逻辑回归 meta model，输出 `raw_prob`；双轨按同日结果比较概率和一致性。它是模型分数，不应直接当作已经校准的真实胜率。详见 [因子清单](docs/FACTOR_CATALOG.md) 和 [研究方法及边界](docs/RESEARCH_METHODS.md)。

保留四套训练入口、SHAP 因子解释、每日 A/B 对照、滚动前推研究及 T+1/T+5 历史分析代码。

## Motto 工作台

- MARKET：指数与板块、市场宽度、资金、分时与市场状态。
- MY DESK：自选搜索、技术条件观察和基于指标的 AI 解读。
- RESEARCH：TX/BS 归档对照、因子预设、模型注册与历史研究结果。
- REFERENCE：多市场资料、宏观、汇率及外部数据连接。
- 工程层：来源和时间标记、缓存与失效状态、ETag、健康/就绪检查、单实例启动与监控。

## Windows 本地启动

准备 Python 3.10+、Node.js 22.13+、pnpm。在仓库根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_local.ps1
```

该脚本建立 `.venv` 并安装依赖，不覆盖已有 `.env`。需要原始 ML 训练/预测全部依赖时加 `-FullModelStack`。

分别在两个终端执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_workbench.ps1
```

打开 **http://127.0.0.1:5899**；研究 API 为 **http://127.0.0.1:8910**。前端使用本地 Miniflare 模拟的存储绑定，无需 Cloudflare 账号或旧 Sites 项目。安装需要网络；行情和 LLM 调用也需要对应网络/API 权限。

详细步骤、环境变量、数据路径和故障排查见 [本地部署](docs/LOCAL_DEPLOYMENT.md)。

## 训练与日频预测

在仓库根目录按所需轨道运行。训练会更新相应模型目录，已有权重应先自行备份。

```powershell
.\.venv\Scripts\python.exe train_tx.py
.\.venv\Scripts\python.exe train_advanced.py
.\.venv\Scripts\python.exe train_mainboard_tx.py
.\.venv\Scripts\python.exe train_mainboard_bs.py
.\.venv\Scripts\python.exe ab_test_DeepSeek.py
```

每次训练后检查各股票的成功/失败日志及模型文件，不能仅凭进程退出码判断训练成功。日报写入 `AB_Test_Reports/`。未配置 LLM 凭证时查看原始预测；模型权重缺失时需先训练。本发布包不自动启用计划任务、训练 API 或新回测任务。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd workbench_ui
pnpm run build
node --test tests/local-workbench.test.mjs
```

前端既有测试主要检查源码/产品契约，不能替代真实浏览器交互和实时行情验收。本次实际结果见 [验证记录](docs/VALIDATION.md)。

## 范围

持仓保持 Mode A；不包含券商下单。新回测默认关闭，历史研究与接口保留。交易所 STEP/CME 正式源需要独立授权；无授权时明确展示降级来源。市场日历内置覆盖 2026 年。Vibe-Research 为可选适配器，默认关闭、独立安装，本包未复制其源码。

来源、许可状态见 [来源说明](docs/SOURCE_AND_LICENSE.md)；原始项目使用说明保存在 [历史 README](docs/DUALALPHA_LEGACY_README.md)。
