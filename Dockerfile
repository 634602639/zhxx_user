# ---- 综合信息服务中心 / Flask + 静态前端（达梦 DM 后端） ----
# 多架构镜像：由 `docker buildx --platform` 决定 amd64 / arm64。
# 关键：用 glibc 基础镜像（非 alpine），因 dmPython 是 manylinux2014(glibc 2.17) wheel；
#       aarch64 wheel 由 PyPI 提供，达梦客户端 .so 已打包进 wheel，自包含。
# 钉到 bookworm：trixie(Debian 13) 把 libaio1 改名为 libaio1t64；bookworm 仍叫 libaio1，
# 且 glibc 2.36 满足 dmPython 的 manylinux2014(glibc 2.17) 要求。
FROM python:3.12-slim-bookworm

# 系统层运行时：
# - tzdata：容器内时间与宿主一致（日志 / occur_time）
# - libxml2 / libxslt1.1：lxml 运行时（python-docx / python-pptx 链上需要）
# - libaio1 / libstdc++6：达梦客户端 .so 的运行时依赖（dmPython 加载时 dlopen）
# - curl：HEALTHCHECK 用
RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata libxml2 libxslt1.1 libaio1 libstdc++6 curl vim \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DB_BACKEND=dm

# 达梦客户端通信加密模块在 dmPython 的 dmssl/ 目录，加入动态库搜索路径，
# 否则连接报 [CODE:-70089] Encryption module failed to load。
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/dmssl:/usr/local/lib/python3.12/site-packages/dmpython.libs

WORKDIR /app

# 先装依赖（利用 Docker 缓存：requirements 没动就不重装）
# dmPython 会按目标架构自动拉取对应 wheel（amd64 / aarch64 均有预编译）。
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
        -r /app/backend/requirements.txt \
        gunicorn==21.2.0

# 再拷代码（含 backend/vendor/sqlalchemy_dm 纯 Python 方言）
COPY backend /app/backend
COPY frontend /app/frontend

# 安装 vendor 的达梦方言：拷进 site-packages，保留 dist-info 的 entry_points，
# 以便 SQLAlchemy 解析 `dm+dmPython://` URI。构建期仅校验 entry_points 注册，
# 不建连接、不触发达梦客户端 .so 的 dlopen（留到运行时）。
RUN SP="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" \
    && cp -r /app/backend/vendor/sqlalchemy_dm "$SP/" \
    && cp -r /app/backend/vendor/sqlalchemy_dm-1.4.39.dist-info "$SP/" \
    && python -c "from importlib.metadata import entry_points as ep; g=ep(); s=(g.select(group='sqlalchemy.dialects') if hasattr(g,'select') else g.get('sqlalchemy.dialects',[])); n=sorted(e.name for e in s); assert 'dm' in n and 'dm.dmPython' in n, ('dm dialect entry_points 缺失: %r' % n); print('sqlalchemy.dialects 已注册:', n)"

# Flask 的 import 路径从 backend/ 起（routes、models、config、dm_compat 都相对它）
WORKDIR /app/backend

EXPOSE 5000

# 4 个 worker 够小并发使用；调大请看物理 CPU
CMD ["gunicorn", "-w", "4", "-k", "gthread", "--threads", "4", \
     "-b", "0.0.0.0:5000", "--timeout", "120", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "app:create_app()"]
