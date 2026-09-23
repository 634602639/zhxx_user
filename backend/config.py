import os
import sys
from urllib.parse import quote_plus

if getattr(sys, "frozen", False):
    # PyInstaller 打包后：可写数据（uploads/exports/data/log）放在 exe 同级目录
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _postgresql_uri():
    """PostgreSQL（驱动：psycopg2；Qt 场景下对应 databaseType=QPSQL）。"""
    host = os.environ.get("PGHOST", "127.0.0.1")
    port = os.environ.get("PGPORT", "5432")
    name = os.environ.get("PGDATABASE", "zonghexinxi_suojian")
    user = os.environ.get("PGUSER", "postgres")
    password = os.environ.get("PGPASSWORD", "123456")
    safe = quote_plus(password)
    return f"postgresql+psycopg2://{quote_plus(user)}:{safe}@{host}:{port}/{name}"


def _dm_uri():
    """达梦 DM8（驱动：dmPython；方言：sqlalchemy_dm，注册名 dm）。"""
    host = os.environ.get("DMHOST", "127.0.0.1")
    port = os.environ.get("DMPORT", "5236")
    user = os.environ.get("DMUSER", "ZHXX_SUO_JIAN")
    password = os.environ.get("DMPASSWORD", "123456789")
    return f"dm+dmPython://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}"


# 数据库后端：dm（默认，达梦）| postgresql（回退）。可用环境变量 DB_BACKEND 切换。
DB_BACKEND = os.environ.get("DB_BACKEND", "dm").lower()


class Config:
    SECRET_KEY = "zhxhfwzxyy-secret-2026"
    SQLALCHEMY_DATABASE_URI = _dm_uri() if DB_BACKEND == "dm" else _postgresql_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
    EXPORT_DIR = os.path.join(BASE_DIR, "exports")
    LOG_FILE = os.path.join(BASE_DIR, "data", "app.log")
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024
    # 内网 OpenAI 兼容大模型。优先用页面保存的 data/llm_config.json，其次环境变量。
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
    LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
    LLM_MODEL = os.environ.get("LLM_MODEL", "")
