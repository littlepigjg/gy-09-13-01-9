"""全局配置"""
import os


class Config:
    # MySQL 连接配置（root 账号密码为 root）
    DB_HOST = os.getenv("AUDIT_DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("AUDIT_DB_PORT", "3306"))
    DB_USER = os.getenv("AUDIT_DB_USER", "root")
    DB_PASSWORD = os.getenv("AUDIT_DB_PASSWORD", "root")
    DB_NAME = os.getenv("AUDIT_DB_NAME", "audit_db")
    DB_CHARSET = "utf8mb4"

    # 连接池
    DB_POOL_SIZE = int(os.getenv("AUDIT_DB_POOL_SIZE", "10"))

    # 检测引擎
    MAX_WINDOW_SECONDS = int(os.getenv("AUDIT_MAX_WINDOW_SECONDS", "3600"))
    BASELINE_HISTORY_SIZE = int(os.getenv("AUDIT_BASELINE_HISTORY", "288"))


config = Config()
