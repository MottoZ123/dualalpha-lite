# 本地部署

## 1. 环境与安装

目标环境为 Windows。需要 Python 3.10+、Node.js 22.13+、pnpm；使用 Git 克隆时安装 Git。先检查 `python --version`、`node --version`、`pnpm --version`。

```powershell
git clone https://github.com/MottoZ123/dualalpha-lite.git
cd dualalpha-lite
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_local.ps1
```

安装脚本创建 `.venv`，安装 API、离线测试、pandas/numpy 与前端依赖；已有 `.env` 不会被覆盖。需要训练和双轨预测时：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_local.ps1 -FullModelStack
```

模型栈包括 AKShare、BaoStock、XGBoost、LightGBM、CatBoost、PyTorch、scikit-learn、SHAP 等。Python 依赖沿用原项目范围，未锁定全部传递版本；旧权重跨版本加载需验证。前端使用 pnpm-lock.yaml。

安装和行情访问需要网络；源码包不附带权重、个人报告或依赖目录。macOS/Linux 仅保留历史后端命令，未在本轮验证。

## 2. 配置

首次安装会从 `.env.example` 创建 `.env`。按实际账户填写密钥，模型名以账户可调用版本为准。

| 配置 | 用途/默认行为 |
|---|---|
| DEEPSEEK_API_KEY / MODEL / BASE_URL | DeepSeek 文字报告 |
| VOLCENGINE_API_KEY / MODEL / BASE_URL | 火山方舟文字报告 |
| RESEARCH_API_KEY | 后端 Bearer Key；纯本机可留空 |
| RESEARCH_ALLOW_ORIGINS | 默认允许本机 5899 |
| ENABLE_MODEL_EXECUTION_API | 默认 0，关闭主动预测接口 |
| ENABLE_TRAINING_API | 默认 0，关闭训练接口 |
| ENABLE_BACKTEST_API | 默认 0，启动器继续强制关闭新回测 |
| RESEARCH_DATA_DIR | 任务/模型注册等研究数据目录 |
| RESEARCH_REPORTS_DIR | 日报读取目录 |
| TRAINING_RUNS_DIR | 独立训练任务目录 |

公共观察标的、刷新设置和 Vibe 开关位于 `workbench-config.json`。未启用 Vibe 时无需安装它。

界面“模型连接”支持多家兼容服务，API Key 仅用于当前页面会话。界面配置与根目录 `.env` 是两条独立配置路径，不会互相自动复制密钥。

## 3. 启动与验收

在仓库根目录的两个终端分别执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_workbench.ps1
```

浏览器访问 http://127.0.0.1:5899；后端 API 文档为 http://127.0.0.1:8910/docs。

首次检查：

1. `/api/health` 返回存活状态；等待数据预热后检查 `/api/ready`。
2. 首页能显示市场区块，并标明数据来源和时间。
3. 添加自选后刷新，确认工作区可以保存和回读。
4. 查看双轨归档日期；没有模型/报告时显示为空属于预期。
5. 需要 AI 时再填写模型连接并执行连接测试。

停止界面使用其终端的 Ctrl+C。停止后端可运行 `scripts/stop_backend.ps1`，它只结束当前目录锁记录中匹配的后端进程。监控脚本 `watch_backend.ps1` 应先停止，防止再次拉起服务。

## 4. 自定义路径与端口

启动器默认研究数据为 `.motto-runtime/live-data`，日报为 `AB_Test_Reports`。若要更改，在启动前设置进程变量：

```powershell
$env:RESEARCH_DATA_DIR='D:\research-data\workbench'
$env:RESEARCH_REPORTS_DIR='D:\research-data\reports'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1
```

启动器设置的进程值优先于 Python 后续加载的 `.env`。前端默认通过启动脚本连接 8910；手动执行 `pnpm run dev` 时，应先设置 `NEXT_PUBLIC_RESEARCH_API_URL=http://127.0.0.1:8910`。

如果更改前端端口，需要同时修改启动命令/配置和后端允许的 Origin；更改后端端口还要同步界面连接地址、监控脚本。默认部署建议沿用 5899/8910，端口占用时先确认占用进程。

## 5. 训练与每日预测

先安装 `-FullModelStack`。下列脚本在仓库根目录执行，会写入对应模型目录；已有模型先备份。

```powershell
.\.venv\Scripts\python.exe train_tx.py
.\.venv\Scripts\python.exe train_advanced.py
.\.venv\Scripts\python.exe train_mainboard_tx.py
.\.venv\Scripts\python.exe train_mainboard_bs.py
.\.venv\Scripts\python.exe ab_test_DeepSeek.py
```

各训练脚本与目录对应关系见 README。检查每只股票的训练日志和模型文件，不只看进程退出码。日报归档到 `AB_Test_Reports/日期/`；没有 LLM 凭证时优先查看原始预测。`ab_test.py` 是火山方舟对照入口。

本包不自动创建定时任务。计划任务应固定仓库工作目录和 `.venv\Scripts\python.exe`，并检查脚本的交互输入、网络和日志。原始模型训练与 `factor_backtest.py` 的因子实验属于不同研究流程，结果不应混用。

## 6. MCP

在支持标准输入输出 MCP 的客户端中，把 command 指向本仓库虚拟环境的 Python，args 指向 `research_mcp_server.py` 的绝对路径：

```json
{
  "command": "D:\\path\\dualalpha-lite\\.venv\\Scripts\\python.exe",
  "args": ["D:\\path\\dualalpha-lite\\research_mcp_server.py"],
  "env": {"RESEARCH_REPORTS_DIR": "D:\\path\\dualalpha-lite\\AB_Test_Reports"}
}
```

它提供归档预测、双轨比较和可选数据查询等只读工具。Vibe 查询需要另行运行该服务。

## 7. 更新、备份与清理

| 内容 | 处理方式 |
|---|---|
| 源码、workbench-config.json | 提交前检查差异，更新时保留自定义配置 |
| .env、models*、AB_Test_Reports | 本机备份，不上传 |
| workbench_ui/.wrangler | 本地工作区数据库，停服务后备份 |
| .motto-runtime、.motto-cache、.dash_state.json | 运行记录、缓存和状态，按用途保留 |
| node_modules、dist、__pycache__ | 可重建，不进入发布包 |

更新前停止服务并备份状态，再 `git pull --ff-only`。依赖变动时重跑安装脚本，之后执行测试和页面检查。本次 `motto_core` 改为 `workbench_core`，配置改为 `workbench-config.json`；自定义 Python 导入需同步。历史配置文件名提供读取回退，磁盘数据库和缓存名保持兼容。

## 8. 常见问题

| 现象 | 检查 |
|---|---|
| health 成功、ready 为 503 | 数据预热、上游网络、缓存过期；不要伪造就绪状态 |
| 页面没有行情 | 8910 是否启动、界面连接地址、Origin、数据源返回 |
| 双轨没有结果 | 是否已有四套权重、日报生成成功、报告读取路径正确 |
| 模型不存在/无权限 | 供应商账户实际模型名、Endpoint、Key 和网络 |
| 不能保存工作区 | 本地运行环境是否完整、.wrangler 是否可写 |
| 提示已有实例 | 查看锁中的进程，通过 stop_backend 停止自己的实例 |
| 交易日历越界 | 更新年度日历；当前内置覆盖 2026 年 |

默认只监听本机。公网身份认证、HTTPS、远程访问及授权行情订阅不属于此部署方式。
