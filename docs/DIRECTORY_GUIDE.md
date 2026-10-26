# 文件功能索引

## 研究与运行文件

| 文件 | 功能 |
|---|---|
| `research_api.py` | HTTP 研究接口与任务编排。 |
| `research_mcp_server.py` | 只读 MCP 工具入口。 |
| `ab_test.py` | 火山方舟双轨对照日报。 |
| `ab_test_DeepSeek.py` | DeepSeek 双轨对照日报。 |
| `daily_agent_tx.py` | TX 日频特征与集成预测。 |
| `daily_agent_bs.py` | BS 日频特征与集成预测。 |
| `train_tx.py` | 科技成长 TX 模型训练。 |
| `train_advanced.py` | 科技成长 BS 模型训练。 |
| `train_mainboard_tx.py` | 主板 TX 模型训练。 |
| `train_mainboard_bs.py` | 主板 BS 模型训练。 |
| `factor_analysis_tx.py` | TX 因子解释与 SHAP 报告。 |
| `batch_factor_report.py` | BS 批量因子报告。 |
| `factor_backtest.py` | 因子计算、统计及回测。 |
| `walk_forward_backtest.py` | 科技成长滚动前推研究。 |
| `walk_forward_mainboard_T5.py` | 主板 T+5 滚动前推研究。 |
| `llm_DeepSeek_tx.py` | TX 文字报告模板。 |
| `llm_DeepSeek_bs.py` | BS 文字报告模板。 |
| `volcengine_llm.py` | 火山方舟报告辅助。 |
| `volcengine_llmtx.py` | 火山方舟 TX 报告辅助。 |
| `sentiment_radar.py` | 新闻情绪研究工具。 |
| `workbench-config.json` | 公开标的与工作台配置。 |
| `requirements-core.txt` | API 基础依赖。 |
| `requirements-models.txt` | 训练与科学计算依赖。 |
| `requirements-dev.txt` | 测试依赖。 |
| `requirements.txt` | 完整 Python 依赖入口。 |
| `workbench_core/config.py` | 工作台配置与默认标的。 |
| `workbench_core/service.py` | 聚合行情和研究结果。 |
| `workbench_core/providers.py` | 腾讯行情与标的搜索。 |
| `workbench_core/public_providers.py` | 宏观及其他数据源。 |
| `workbench_core/analytics.py` | 指标、趋势与条件判断。 |
| `workbench_core/cache.py` | 缓存与最后可用数据。 |
| `workbench_core/contracts.py` | 数据结构与数值规范。 |
| `workbench_core/http_cache.py` | ETag 条件响应。 |
| `workbench_core/market_clock.py` | 市场时段与交易日历。 |
| `workbench_core/state.py` | 条件状态持久化。 |
| `workbench_core/research_registry.py` | 因子版本与模型注册。 |
| `research_core/config.py` | 环境变量和模型配置。 |
| `research_core/llm_client.py` | 兼容模型请求与错误处理。 |
| `research_core/schemas.py` | 预测归一化与双轨比较。 |
| `research_core/tools.py` | 研究工具定义和执行。 |
| `research_core/vibe_client.py` | 可选 Vibe 服务适配。 |
| `scripts/setup_local.ps1` | 安装本地环境。 |
| `scripts/start_backend.ps1` | 启动研究后端。 |
| `scripts/start_workbench.ps1` | 启动本地界面。 |
| `scripts/stop_backend.ps1` | 停止当前目录后端。 |
| `scripts/watch_backend.ps1` | 监控后端并受限重启。 |
| `scripts/start_backend.command` | 类 Unix 后端入口。 |
| `scripts/reproduce_historical_dual_horizon.py` | 指定历史双周期研究。 |
| `workbench_ui/app/page.tsx` | 页面入口。 |
| `workbench_ui/app/layout.tsx` | 页面元信息。 |
| `workbench_ui/app/globals.css` | 全局样式。 |
| `workbench_ui/app/_components/LocalWorkbench.tsx` | 工作台交互界面。 |
| `workbench_ui/app/_components/LocalWorkbench.module.css` | 工作台组件样式。 |
| `workbench_ui/db/workspace.ts` | 本地工作区存储。 |
| `workbench_ui/lib/workspace.ts` | 工作区结构与模型预设。 |
| `workbench_ui/lib/server-security.ts` | 请求校验与模型连接。 |
| `workbench_ui/lib/access-control.ts` | 访问检查与兼容权限逻辑。 |
| `workbench_ui/lib/cloud-owner.ts` | 本地工作区身份。 |
| `workbench_ui/vite.config.ts` | 本地构建和运行配置。 |
| `workbench_ui/worker/index.ts` | 本地运行入口。 |

## 其他目录

| 路径 | 功能 |
|---|---|
| workbench_ui/app/api/cloud/workspace/route.ts | 工作区读写。 |
| workbench_ui/app/api/cloud/analysis/route.ts | 文字分析。 |
| workbench_ui/app/api/cloud/provider/test/route.ts | 模型连接测试。 |
| workbench_ui/app/api/cloud/rich/context/route.ts | 研究服务转发。 |
| workbench_ui/tests/ | 界面契约测试。 |
| tests/ | 后端单元测试。 |
| workbench_ui/public/ | 图标、PWA 和离线外壳。 |
| workbench_ui/package.json、pnpm-lock.yaml | 前端依赖与脚本。 |
| workbench_ui/types/、tsconfig.json | 类型声明和检查配置。 |
| workbench_ui/.openai/hosting.json | 本地存储绑定名称。 |
| models*、AB_Test_Reports、factor_reports* | 本机研究产物占位目录。 |

原始训练脚本和模型目录名称保留兼容。数据格式、缓存键与数据库名不因展示名称改变。
