# Motto 本地工作台界面

使用根目录 README 的安装和启动命令。运行端口为 127.0.0.1:5899，Python 后端为 8910。

app/page.tsx → MottoStockAnalysis 是唯一页面入口。保留工作区存储、模型测试、模型分析、后端转发四个 API；历史 /api/cloud 名称仅为兼容接口命名。D1/R2 通过本地 Miniflare 模拟，不绑定原 Sites 项目。

旧 CloudStudio、InviteGate 页面、示例数据、公开网站手册、独立云部署与不使用的路由均未进入此包。
