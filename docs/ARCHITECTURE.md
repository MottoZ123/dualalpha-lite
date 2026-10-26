# 系统架构

## 组件分工

| 组件 | 职责 | 状态/数据 |
|---|---|---|
| workbench_ui | 页面、工作区设置、模型连接、受限后端转发 | 浏览器缓存、本地 D1 模拟存储 |
| research_api.py | HTTP 接口、任务开关、任务编排、模型版本操作 | 任务与研究注册数据库 |
| workbench_core | 行情适配、市场时钟、指标、缓存、条件状态 | 行情缓存、条件状态文件 |
| research_core | 配置、预测归一化、双轨比较、LLM 与 Vibe 适配 | 读取环境配置和日报归档 |
| 根目录训练/预测脚本 | 因子加工、四模型训练、融合与每日预测 | models*、AB_Test_Reports |
| research_mcp_server.py | 通过标准输入输出提供只读研究工具 | 复用 research_core |

## 请求与数据流

1. 浏览器从 5899 加载页面；界面连接 8910 研究服务。
2. 市场请求进入 FastAPI，workbench_core 根据缓存状态读取数据源并计算指标。
3. 完整面板通过 `/api/all` 返回；高频更新通过 `/api/realtime` 返回局部数据。
4. 双轨页面读取已有日频归档，标明归档日期；它不会把日频预测当作盘中模型结果。
5. 用户请求 AI 分析时，结构化指标进入独立解释层；密钥来自后端环境或当前界面会话。
6. 训练/回测任务只有在对应开关开启且用户提交时才运行；任务结果与原有模型分开保存，模型晋级/回滚使用注册记录。

## 前端服务

保留四个本地路由，历史 `cloud` 路径名称用于接口兼容，并不表示已经发布云服务。

| 路由 | 功能 |
|---|---|
| GET/PUT/DELETE `/api/cloud/workspace` | 读取、保存、重置工作区 |
| POST `/api/cloud/provider/test` | 验证模型连接 |
| POST `/api/cloud/analysis` | 请求文字分析 |
| POST `/api/cloud/rich/context` | 按白名单转发研究服务请求 |

本地工作区由 `db/workspace.ts` 在首次访问时建表。`workbench_ui/.wrangler/` 是运行数据，不是可以随意删除的编译缓存。旧网站界面、演示数据、邀请页面和未使用路由已移除。

## 后端接口

| 接口组 | 示例 | 用途 |
|---|---|---|
| 运行状态 | `/api/health`、`/api/ready`、`/api/config/status` | 存活、数据就绪、脱敏配置 |
| 市场 | `/api/all`、`/api/realtime`、`/api/kline`、`/api/intraday` | 行情与指标 |
| 个人研究 | `/api/instruments/search`、`/api/llm/stock-analysis` | 自选检索与证据解释 |
| 双轨归档 | `/api/predictions/tx`、`/api/comparison`、`/api/research/dual-track/latest` | 预测读取与对比 |
| 因子/历史 | `/api/research/factors`、`/api/research/factor-presets`、`/api/research/backtests` | 因子定义和历史案例 |
| 任务/模型 | `/api/jobs`、`/api/jobs/{id}`、`/api/research/models` | 异步研究与模型版本 |

完整请求结构以运行中的 `/docs` 为准。持仓接口仅保留能力契约，Mode A 不写入持仓。Vibe-Research 为默认关闭的独立可选服务。

## 缓存与故障处理

- 行情包携带来源、市场时点、抓取时点、新鲜度与降级状态。
- 内存缓存与磁盘最后可用数据共同减少上游波动；缺失值不填成零。
- 完整包使用指纹和 ETag；条件请求可返回 304。
- `/api/health` 成功只表示进程存活；`/api/ready` 要求关键数据有效，冷启动或过期时可能返回 503。
- 后端启动器使用独占锁；监控脚本达到连续失败阈值后才尝试重启，并设冷却期。

## 数据边界

源码、研究产物和运行状态分别管理。`.env`、models*、AB_Test_Reports、运行数据库、`.wrangler` 和行情缓存均不随公共源码提交。历史 `.motto-runtime`、`.motto-cache`、数据库名和浏览器缓存键保留兼容；产品展示名称与这些存储键无关。

预测质量、实时行情完整性、软件构建和页面交互分别验收。测试通过不代表模型已经获得稳定收益。
