# 本地部署与数据管理

## 架构与入口

`workbench_ui/` 是最新 Motto 本地界面；`motto-site/` 是旧副本，未纳入发布。首页直接渲染 MottoStockAnalysis。Python 服务由 `research_api.py`、`motto_core/`、`research_core/` 构成，原有双轨脚本独立保留。

界面依赖本地 Vinext/Cloudflare Vite 插件的 D1/R2 模拟。`/api/cloud/*` 是历史接口命名；本地运行无需云端部署。`.openai/hosting.json` 仅保留 DB/ARTIFACTS 的绑定名称，未携带原项目 ID。只保留工作台实际使用的四个服务路由：workspace、analysis、provider/test、rich/context；移除旧网页的登录、制品、独立执行器和 Vibe 页面路由。

## 安装

使用根目录 README 中的 setup_local.ps1。基础安装包括 API、离线测试与因子分析所需的 pandas/numpy；`-FullModelStack` 追加树模型、PyTorch、SHAP 等依赖。Python 模型栈沿用原项目版本范围，未锁定所有传递依赖；换环境训练或读取旧权重需另行验证。前端 pnpm-lock.yaml 固定依赖解析。

手动安装等价步骤：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt pandas numpy
Copy-Item .env.example .env  # 仅首次，已有配置不要覆盖
cd workbench_ui
pnpm install --frozen-lockfile
```

Windows 为本次整理目标。保留的 start_backend.command 是历史后端入口；macOS/Linux 未在本次验收。

## 数据路径

- `.env`：后端密钥及配置，不上传。LLM 模型名按账户实际权限填写。
- `AB_Test_Reports/`：原始日报输出，本次后端启动器默认读取这里。
- `.motto-runtime/live-data/`：后端任务/模型注册等运行数据。
- `.motto-cache/`、`.dash_state.json`：行情缓存和状态；保留本机版本，不上传。
- `workbench_ui/.wrangler/`：本地工作区存储；不属于可随意删除的构建缓存。
- `models*`：原始权重留在本机，仓库只保留占位目录。
- `output/backtests/`：本机历史研究，不复制到公共包。

启动器优先使用进程中设置的 RESEARCH_DATA_DIR / RESEARCH_REPORTS_DIR；如需自定义路径，在启动前设置这些环境变量。脚本预设值优先于 Python 后续加载的 .env。停止本地服务后再做状态备份。

## 启动与验收

后端固定监听 127.0.0.1:8910，前端 127.0.0.1:5899。检查 `/api/health` 表示进程存活；`/api/ready` 可能在冷启动、网络失败、缓存过期时返回 503，不能把 health 200 当行情完整。

首次打开应检查 MARKET、MY DESK、RESEARCH、REFERENCE，确认数据来源/时点，保存自选并刷新检查持久化。模型连接中仅会话内保存 API Key。可以不配置 LLM，先验证确定性指标与模型归档。

`scripts/watch_backend.ps1` 保留监控能力，但不会自动注册系统任务。没有训练权重时，实时市场模块与历史模型预测是否可用应分别判断。

## 安全与更新

默认只供本机访问，不要把此启动方式直接绑定 0.0.0.0 或作为公网部署。新回测保持禁用。更新源码前备份 .env、模型、日报、.wrangler 与运行数据库；覆盖源码不应覆盖这些状态。本次包不会迁移或重置现有本地工作台。
