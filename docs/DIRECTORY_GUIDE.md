# 按功能整理的目录与命名

| 路径 | 功能 |
|---|---|
| workbench_ui/ | Motto 本地工作台界面与其必需 API |
| motto_core/ | 行情适配、指标、状态、缓存、研究注册 |
| research_core/ | 配置、预测结构、LLM 与 MCP 工具逻辑 |
| research_api.py | 本地 HTTP 研究服务 |
| research_mcp_server.py | 本地 MCP 服务 |
| train_*.py | 原始四套模型训练入口 |
| daily_agent_tx.py / daily_agent_bs.py | 双轨日频预测 |
| ab_test_DeepSeek.py / ab_test.py | DeepSeek / 火山双轨报告入口 |
| factor_*.py / batch_factor_report.py | 因子计算、解释与研究 |
| walk_forward*.py | 原始滚动前推研究 |
| scripts/setup_local.ps1 | 安装本地运行环境 |
| scripts/start_backend.ps1 | 启动 Python 研究服务 |
| scripts/start_workbench.ps1 | 启动 Motto 本地界面 |
| scripts/watch_backend.ps1 | 监控本地后端 |
| scripts/reproduce_historical_dual_horizon.py | 指定历史双周期研究入口，默认不执行 |
| docs/ | 部署、因子清单、研究边界、验证及来源说明 |
| tests/ | 后端测试 |

frontend → workbench_ui，启动/监控脚本按功能改名，相关引用同步更新。原始 Python 入口、models* 和报告目录属于既有接口，保留名称以兼容用户已有训练结果与调用方式。原项目 AI 活动目录不改名，避免破坏虚拟环境、IDE 和定时任务路径。
