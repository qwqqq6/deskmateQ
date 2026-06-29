"""DeskMate - 桌面效率小部件。

分层架构:
    core         基础设施: 配置、路径、数据库连接与迁移
    repositories 数据访问层: 每个领域一个仓储, 仅依赖 core
    services     业务服务: 备份/恢复、开机自启、周报生成
    ui           表现层: 无边框桌面小部件与各功能面板
"""

__version__ = "1.2.0"
__app_name__ = "DeskMateQ"
