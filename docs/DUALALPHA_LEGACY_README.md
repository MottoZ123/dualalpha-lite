# DualAlpha-Lite

## 基于 TX/BS 双轨集成学习的轻量级股票预测系统

一个轻量级 A 股双轨预测与复盘系统。项目把技术形态、资金流、成本偏离、量价共振、机器学习融合模型和可选 LLM 研报串在一起，用于生成每日候选股票的 TX/BS 双引擎预测、A/B 对撞报告、历史结算和回测结果。

> 风险提示：本项目仅用于量化研究和工程学习，不构成投资建议。A 股交易存在高风险，任何真实交易都需要自行判断并承担后果。

## 适用场景

- 日线级股票池复盘。
- 收盘后或晚间生成次日观察清单。
- 对固定股票池做多模型集成学习实验。
- 对 TX/BS 两套不同因子逻辑做 A/B 对撞。
- 用 LLM 把结构化量化结果整理成更易读的研报。

本系统更适合“研究、复盘、候选池筛选”，不适合作为自动交易或盘中高频决策系统。

## 核心原理

系统由两条相互独立的预测链路组成：

- **TX 引擎**：偏趋势、资金流、K 线形态和纯价格反转。科技股使用 `models_tx`，主板股使用 `models_tx_v7`。
- **BS 引擎**：偏成本偏离、换手、VWAP、量价共振和左侧修复。科技股使用 `models`，主板股使用 `models_bs_v6`。

每条链路都使用四类底层模型：

- XGBoost
- LightGBM
- CatBoost
- Transformer

训练阶段会再用一个逻辑回归 meta model 学习四类底层模型的权重，最终输出 `raw_prob`。这个值可以理解为系统判断该股票下一阶段取得超额收益的概率。

LLM 只负责把结构化预测解释成文字报告，不是预测本身。没有配置 API key 时，系统仍可生成原始预测 JSON，但 LLM 文字报告会被跳过。

## 劣势与适用边界

这套系统是轻量级研究工具，不是全功能交易平台。主要限制如下：

- **不适合盘中实时计算**：脚本主要拉取日线数据，按收盘后复盘/次日计划设计，不适合分钟级、秒级或盘口级交易。
- **依赖第三方数据源稳定性**：`akshare`、`baostock` 等数据接口偶尔会因为网络、限流、字段变化导致拉取失败。
- **股票池较小且偏固定**：当前逻辑围绕固定候选池训练和预测，换股票后需要重新训练对应模型。
- **模型文件不随仓库发布**：开源仓库默认不包含 `.pkl`、`.pth`、`.cbm` 等训练结果，首次使用需要自行训练或准备模型。
- **样本和特征存在过拟合风险**：固定股票池、短窗口特征、T+1/T+5 标签都可能对历史数据过度适配。
- **不能替代基本面和风控**：系统主要基于量价与技术特征，不直接理解公司基本面、公告、政策、突发新闻和流动性冲击。
- **LLM 只负责解释，不负责预测**：DeepSeek/火山引擎输出的是文字分析，它可能夸大确定性，因此应优先看 `tx_raw_preds.json` 和 `bs_raw_preds.json` 的结构化数据。
- **不包含自动下单能力**：项目没有券商接口、订单管理、仓位管理和真实交易风控模块。

如果要用于真实交易研究，建议加入更严格的数据校验、样本外验证、滑点/手续费模型、仓位约束、回撤控制和人工复核流程。

## 项目结构

主要入口：

- `ab_test_DeepSeek.py`：每日 A/B 双轨运行入口，生成 raw JSON、TX 报告、BS 报告和对撞裁决报告。
- `daily_agent_tx.py`：TX 引擎每日预测脚本。
- `daily_agent_bs.py`：BS 引擎每日预测脚本。
- `llm_DeepSeek_tx.py`：TX 报告的 DeepSeek 调用层。
- `llm_DeepSeek_bs.py`：BS 报告的 DeepSeek 调用层。

训练与特征分析：

- `train_tx.py`：科技阵营 TX 模型训练。
- `train_advanced.py`：科技阵营 BS/基础模型训练。
- `train_mainboard_tx.py`：主板阵营 TX 模型训练，并生成 TX 主板 SHAP 图。
- `train_mainboard_bs.py`：主板阵营 BS 模型训练，并生成 BS 主板 SHAP 图。
- `factor_analysis_tx.py`：TX 科技阵营因子分析与 SHAP 报告。
- `batch_factor_report.py`：BS/基础科技阵营批量因子报告。

回测：

- `walk_forward_backtest.py`：科技阵营 walk-forward 回测。
- `walk_forward_mainboard_T5.py`：主板阵营 T+5 walk-forward 回测。
- `ab_test.py`：早期 A/B 测试入口，保留作对照版本。

生成目录：

- `models/`：BS 科技阵营模型输出目录。
- `models_tx/`：TX 科技阵营模型输出目录。
- `models_bs_v6/`：BS 主板阵营模型输出目录。
- `models_tx_v7/`：TX 主板阵营模型输出目录。
- `AB_Test_Reports/`：每日 A/B 报告输出目录。
- `factor_reports_*`：特征分析和 SHAP 图输出目录。

## 安装

建议使用 Python 3.10。

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

如果安装 `torch` 较慢或需要 GPU 版本，建议按 PyTorch 官网命令单独安装对应 CUDA/CPU 版本。

## 操作指南

### 1. 配置 API Key

复制 `.env.example` 里的变量名，在系统环境变量或当前终端中设置。项目不会读取仓库里的真实密钥，也不建议把 `.env` 提交到 GitHub。

PowerShell 示例：

```powershell
$env:DEEPSEEK_API_KEY="your_deepseek_api_key"
$env:DEEPSEEK_MODEL="deepseek-chat"
$env:DEEPSEEK_URL="https://api.deepseek.com/chat/completions"

$env:VOLCENGINE_API_KEY="your_volcengine_api_key"
$env:VOLCENGINE_MODEL="your_volcengine_endpoint_id"
$env:VOLCENGINE_URL="https://ark.cn-beijing.volces.com/api/v3/chat/completions"
```

`VOLCENGINE_API_KEY` 和 `VOLCENGINE_MODEL` 是可选项。未配置时，火山引擎初筛会跳过。

### 2. 训练模型

首次运行每日预测前，需要先训练或准备模型文件。

```powershell
python train_advanced.py
python train_tx.py
python train_mainboard_bs.py
python train_mainboard_tx.py
```

训练完成后应得到以下目录中的模型文件：

- `models/*.pkl`, `models/*.json`, `models/*.cbm`, `models/*.pth`
- `models_tx/*`
- `models_bs_v6/*`
- `models_tx_v7/*`

### 3. 生成因子分析

```powershell
python batch_factor_report.py
python factor_analysis_tx.py
```

主板训练脚本也会在训练过程中生成部分 `factor_reports_bs_v6` 和 `factor_reports_tx_v7` 输出。

### 4. 运行每日 AB 测试

```powershell
python ab_test_DeepSeek.py
```

脚本会询问当前持仓，可以直接回车跳过。输出会写入：

```text
AB_Test_Reports/yyyyMMdd/
├── tx_raw_preds.json
├── bs_raw_preds.json
├── 1_TX_Full_Report.md
├── 2_BS_Full_Report.md
└── 3_AB_Comparison_Verdict.md
```

### 5. 运行回测

科技阵营：

```powershell
python walk_forward_backtest.py
```

主板 T+5：

```powershell
python walk_forward_mainboard_T5.py
```

回测会动态拉取历史行情并滚动训练/验证。运行时间取决于网络、股票池和机器性能。

## 自定义与优化选项

### 更换股票代码

股票池主要写在以下脚本的 `TECH_TICKERS`、`MAIN_TICKERS` 或 `TICKERS_RAW` 中：

- `daily_agent_tx.py`
- `daily_agent_bs.py`
- `train_tx.py`
- `train_advanced.py`
- `train_mainboard_tx.py`
- `train_mainboard_bs.py`
- `walk_forward_backtest.py`
- `walk_forward_mainboard_T5.py`

如果你只想修改每日预测池，优先改：

```python
TECH_TICKERS = ["300308", "300502", "688008"]
MAIN_TICKERS = ["600522", "601899"]
TICKERS_RAW = TECH_TICKERS + MAIN_TICKERS
```

注意：训练脚本和每日预测脚本的股票池最好保持一致，否则每日预测会找不到对应模型文件。

### 更换自己的 API Key

不要把 Key 写进源码。推荐用环境变量：

```powershell
$env:DEEPSEEK_API_KEY="your_new_key"
$env:VOLCENGINE_API_KEY="your_new_key"
```

如果你使用 `.env` 文件，请确认 `.gitignore` 已经排除了 `.env`。

### 更换其他 LLM

本项目使用的是 OpenAI 兼容的 chat-completions 调用格式。只要服务商兼容类似接口，通常只需要改环境变量：

```powershell
$env:DEEPSEEK_URL="https://your-provider.example.com/v1/chat/completions"
$env:DEEPSEEK_MODEL="your-model-name"
$env:DEEPSEEK_API_KEY="your-provider-api-key"
```

如果响应结构不是 `choices[0].message.content`，需要修改：

- `llm_DeepSeek_tx.py`
- `llm_DeepSeek_bs.py`
- `ab_test_DeepSeek.py` 中 `ask_ab_comparison_agent` 的响应解析部分

### 修改 Prompt

Prompt 主要在以下位置：

- `llm_DeepSeek_tx.py`：TX 单独报告风格。
- `llm_DeepSeek_bs.py`：BS 单独报告风格。
- `ab_test_DeepSeek.py`：TX/BS 对撞裁决报告风格。

你可以修改 Prompt 的输出结构、语气、风险提示和交易周期。例如把激进表达改为更稳健的研报风格，或要求固定输出：

- 市场状态
- 共振标的
- 分歧标的
- 风险清单
- 次日观察条件
- 非投资建议声明

### 调整风控阈值

每日脚本里通常以 `0.53` 作为有效看多阈值，以 `0.58`、`0.65` 等作为更高档位。你可以在以下函数或逻辑中调整：

- `daily_agent_tx.py` 的 `get_position_tier`
- `daily_agent_bs.py` 的档位判断
- `ab_test_DeepSeek.py` 里生成共振表和仓位权重的逻辑

阈值越低，信号越多但噪声更大；阈值越高，信号更少但通常更保守。

### 增加或替换特征

特征列表主要在：

- `daily_agent_tx.py`
- `daily_agent_bs.py`
- `train_tx.py`
- `train_advanced.py`
- `train_mainboard_tx.py`
- `train_mainboard_bs.py`

例如：

```python
TECH_FEATURES = [
    "Relative_Strength",
    "Return_5",
    "BIAS_20",
    "Vol_Ratio",
]
```

如果修改特征，必须同步修改训练脚本和预测脚本，并重新训练模型。

### 发布训练好的模型

仓库默认不包含模型二进制。如果你想发布模型，有两个更稳的选择：

- 用 GitHub Releases 上传压缩包。
- 用 Git LFS 管理 `.pkl`、`.pth`、`.cbm`、`.json` 等模型文件。

不建议直接把大模型文件提交进普通 Git 历史。

## 上传到 GitHub

下面以 PowerShell 为例，假设你已经安装 Git，并且已经在 GitHub 创建了一个空仓库，例如：

```text
https://github.com/your-name/dualalpha-lite.git
```

### 1. 进入项目目录

```powershell
cd C:\Users\Motto\Documents\Codex\2026-06-24\d-workspace-sop-sop-ai-1-2\outputs\ai-stock-ab-system-open-source-20260624
```

### 2. 初始化 Git 仓库

```powershell
git init
git branch -M main
```

### 3. 检查将要提交的文件

```powershell
git status
```

确认没有 `.env`、真实 API key、历史报告和模型大文件。

### 4. 提交代码

```powershell
git add .
git commit -m "Initial open-source release"
```

### 5. 绑定 GitHub 远程仓库

```powershell
git remote add origin https://github.com/your-name/dualalpha-lite.git
```

如果你使用 SSH：

```powershell
git remote add origin git@github.com:your-name/dualalpha-lite.git
```

### 6. 推送到 GitHub

```powershell
git push -u origin main
```

### 7. 上传前再次检查密钥

可以用下面的命令做一次简单扫描：

```powershell
rg "sk-|ark-|API_KEY|api_key|SECRET|TOKEN|PASSWORD"
```

如果扫到的是 `.env.example` 里的占位说明，一般没问题；如果扫到真实 Key，必须删除并重新生成 Git 提交历史。

## 未放入仓库的内容

为了便于 GitHub 开源，本发布包没有包含：

- `.venv`、`.venv1` 虚拟环境
- `.idea` PyCharm 配置
- `__pycache__`
- 已训练模型二进制文件
- 历史实盘报告
- API key
- 私人测试文本、网络测试脚本、私募爬虫等与主流程无关的文件

## 开源前检查清单

- 确认没有提交 `.env` 或任何真实 API key。
- 确认没有提交个人历史交易报告。
- 确认没有提交超大模型二进制，或已使用 Git LFS/Release。
- 在干净环境中至少运行一次 `python -m py_compile *.py`。
- 在 README 中保留风险提示。
