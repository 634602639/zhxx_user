# ARM64 部署（达梦 DM 后端）

在 **x86 开发机交叉构建 arm64 镜像**，部署到 **ARM 信创主机**；
达梦数据库服务器（DM Server）跑在容器外的 ARM 服务器上，应用容器通过网络连过去。

## 组件与 ARM 适配一览

| 组件 | ARM 来源 | 说明 |
|---|---|---|
| `dmPython`（C 扩展 + 达梦客户端 .so） | PyPI `manylinux2014_aarch64` wheel | `pip install` 自动拉取，达梦客户端库已打包进 wheel，自包含 |
| `sqlalchemy_dm`（达梦方言） | 纯 Python，已 vendor 到 `backend/vendor/` | Dockerfile 拷入 site-packages，保留 dist-info 的 entry_points |
| `dm_compat.py`（自增主键回填补丁） | 纯 Python，`backend/` 内 | 启动时对 dm 方言生效 |
| 其余依赖（lxml/docx/pptx/reportlab…） | 均有 aarch64 wheel | 无需特殊处理 |
| DM Server | 容器外 ARM 信创机 | 由 `.env` 的 DMHOST/DMPORT 指定 |

> 基础镜像必须是 **glibc**（`python:3.12-slim`），不能用 alpine —— dmPython 是 manylinux2014(glibc 2.17) wheel。

## 一、前置（x86 构建机，Docker Desktop / Windows）

Docker Desktop 自带 buildx 与 QEMU 模拟器。若用纯 Linux 引擎且未装模拟器，先执行一次：

```powershell
docker run --privileged --rm tonistiigi/binfmt --install arm64
docker buildx create --name armbuilder --use   # 仅首次创建并切换
```

## 二、交叉构建 arm64 镜像并导出为 tar

在仓库根目录（含 Dockerfile）执行：

```powershell
docker buildx build --platform linux/arm64 `
  -t zhxx-suojian:arm64 `
  -o type=docker,dest=zhxx-suojian-arm64.tar .
```

- `--platform linux/arm64`：QEMU 模拟 arm64，pip 会拉取 aarch64 wheel
- `-o type=docker,dest=...tar`：导出可 `docker load` 的单架构镜像包

构建日志里应能看到 `sqlalchemy.dialects 已注册: ['dm', 'dm.dmPython', ...]`，说明达梦方言就位。

## 三、传输到 ARM 主机并载入

```bash
# 在 x86 机把 tar 传到 ARM 主机（scp / U 盘 / 内网共享均可）
scp zhxx-suojian-arm64.tar user@arm-host:/opt/zhxx/

# 在 ARM 主机
docker load -i /opt/zhxx/zhxx-suojian-arm64.tar
```

## 四、ARM 主机上运行

把仓库的 `docker-compose.yml` 和 `.env.example` 放到 ARM 主机同一目录：

```bash
cp .env.example .env
vi .env        # 填外部达梦服务器地址/账号密码
```

`.env` 示例：

```ini
DMHOST=10.0.0.21      # 外部 ARM 达梦服务器 IP
DMPORT=5236
DMUSER=suo_jian
DMPASSWORD=你的密码
```

因为镜像已 `docker load`，compose 直接用 `image: zhxx-suojian:arm64`，无需再 build：

```bash
docker compose up -d
docker compose logs -f app
```

> 若想直接在 ARM 主机上构建（不交叉编译），保留 compose 的 `build:` 段执行
> `docker compose up -d --build` 即可，第一、二步可跳过。

## 五、验证

```bash
curl http://localhost:5000/api/health        # 期望 {"code":0,"msg":"ok"}
```

健康检查与首页能访问，且日志无达梦连接错误即成功。

## 六、排错

- **`Can't load plugin: sqlalchemy.dialects:dm.dmPython`**
  vendor 未拷进 site-packages。确认 `backend/vendor/sqlalchemy_dm*` 在镜像内，
  且构建日志出现「sqlalchemy.dialects 已注册」。

- **`libdmdpi.so: cannot open` / `libaio.so.1 not found`**
  达梦客户端 .so 的系统依赖缺失。Dockerfile 已装 `libaio1 libstdc++6`；
  若仍报缺库，按报错补 `apt-get install` 对应包。

- **连不上达梦（timeout / refused）**
  容器内 `DMHOST` 要能路由到外部 ARM 服务器；确认达梦实例已放开远程连接、
  防火墙开放 5236、`SUO_JIAN` 用户允许从容器网段登录。

- **交叉构建拉 wheel 慢/失败**
  Dockerfile 已用清华源；公司内网可换成内部 PyPI 镜像。
