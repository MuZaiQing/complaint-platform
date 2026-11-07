# 部署到其他物理主机

三种目标环境：Docker（推荐，跨平台一致）、Linux 裸机、Windows 裸机。三种方式跑起来的是同一个 FastAPI + 单文件 Vue3 大屏，数据来源都是 MySQL + `data/` 下的明细文件。

## 一、部署前须知

### 组成

| 组件 | 位置 | 说明 |
|---|---|---|
| 后端 + 前端 | `backend/` | `main.py` 提供 API，`index.html` 是全部页面 |
| 数据库结构 + 基础数据 | `db/complaint_analysis.sql` | 10 张表，532KB |
| 运行数据（必须） | `data/` 下 3 个 pkl + `mr_result/` | `complaints_clean.pkl`(566MB)、`ccdb_text.pkl`(2.1GB)、`fcc_consumer_complaints_clean.pkl`(283MB) |
| MR 输入 CSV（可选） | `data/complaints_clean.csv`、`fcc_..._clean.csv` | 要现场跑集群任务才需要，共 6.3GB |
| 未清洗原始数据（可选） | `未清洗前的源数据/CCDB/` | 6.5GB，只在 pkl 缺失时兜底 |
| 集群 jar 与源码 | `mr/jar包/`、`mr/src/` | 集群控制台运行任务时用 |
| 前端依赖 | `backend/vendor/` | Vue 3.5.13 / Element Plus 2.9.1 / ECharts 5.6 / three.js / 字体 / 美国州界 GeoJSON，全部本地托管 |
| 启停 / 入库脚本 | `scripts/` | `start/stop`、`export_db/import_db`，Windows 与 Linux 各一套 |

最小部署集约 **3GB**（代码 + SQL + 3 个 pkl + mr_result）。

### 代码怎么过去

```bash
git clone https://github.com/MuZaiQing/complaint-platform.git /opt/fqh
```

或使用 `dist/complaint-platform-src.zip`（离线环境，含全部代码与 SQL，不含大文件）。

### 数据怎么过去

大文件不进 git，用 scp / rsync / U 盘均可。示例（源机 → 目标机）：

```bash
# 最小集
rsync -av --progress data/complaints_clean.pkl data/ccdb_text.pkl \
      data/fcc_consumer_complaints_clean.pkl data/mr_result/ \
      user@target:/opt/fqh/data/

# 需要跑 MR 时追加
rsync -av --progress data/complaints_clean.csv data/fcc_consumer_complaints_clean.csv \
      user@target:/opt/fqh/data/
```

`data/`、`未清洗前的源数据/` 目录在目标机上要先建好（`mkdir -p`）。

## 二、方式 A：Docker（推荐）

目标机只要求 Docker 24+ 与 Compose v2。

```bash
git clone https://github.com/MuZaiQing/complaint-platform.git /opt/fqh && cd /opt/fqh
mkdir -p data 未清洗前的源数据
# 把 3 个 pkl 与 mr_result/ 拷进 data/（见上一节）
docker compose up -d --build
```

首次启动会自动完成建库建表：`db/complaint_analysis.sql` 被挂载到 MySQL 的 `/docker-entrypoint-initdb.d/`，容器初始化时执行。

验证：

```bash
docker compose ps                       # 两个服务都 running，mysql 为 healthy
curl -s http://127.0.0.1:8000/api/dashboard/overview | head -c 200
```

访问 `http://<目标机IP>:8000`。

关键环境变量（可直接写在项目根的 `.env` 供 compose 读取）：

| 变量 | 默认 | 作用 |
|---|---|---|
| `APP_PORT` | 8000 | 对外端口 |
| `MYSQL_ROOT_PASSWORD` | `Fqh112233!` | MySQL root 密码 |
| `DB_NAME` | `complaint_analysis` | 库名 |
| `CLUSTER_HOST/PORT/USER/PASSWORD` | 10.15.7.101 / 22 / hadoop / dsj123 | 集群控制台 SSH |
| `CLUSTER_MOCK` | 0 | 1 = 不连集群，用假数据联调 |

> 重置数据库：`docker compose down -v` 会删除数据卷，下次启动重新执行 initdb 脚本（**会丢现有数据**）。

## 三、方式 B：Linux 裸机

```bash
# 1. 依赖
sudo apt install -y python3 python3-pip mysql-server
python3 -m venv /opt/fqh/.venv
/opt/fqh/.venv/bin/pip install -r /opt/fqh/backend/requirements.txt

# 2. 配置（DB 与集群地址）
cp /opt/fqh/backend/.env.example /opt/fqh/backend/.env
vi /opt/fqh/backend/.env

# 3. 一键入库（--file 可省略，自动找 db/*.sql）
cd /opt/fqh && bash scripts/import_db.sh

# 4. 启停
PYTHON=/opt/fqh/.venv/bin/python bash scripts/start.sh
bash scripts/stop.sh
```

开机自启（可选）：

```ini
# /etc/systemd/system/fqh.service
[Unit]
Description=Complaint Platform
After=network.target mysql.service

[Service]
WorkingDirectory=/opt/fqh/backend
ExecStart=/opt/fqh/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

`sudo systemctl enable --now fqh` 后由 systemd 托管，不再用 `start.sh`。

## 四、方式 C：Windows 裸机

```powershell
git clone https://github.com/MuZaiQing/complaint-platform.git D:\fqh
cd D:\fqh
py -3 -m pip install -r backend\requirements.txt

copy backend\.env.example backend\.env   # 改 DB_PASSWORD / CLUSTER_HOST
.\scripts\import_db.bat                  # 自动查找 db\*.sql
.\scripts\start.bat
.\scripts\stop.bat
```

`start.bat` 会写 `backend\logs\app.pid` 与 `app.log`；`stop.bat` 先按 PID 停，再按 8000 端口兜底。

## 五、验证清单

| 项 | 命令 | 期望 |
|---|---|---|
| 页面可达 | `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/` | 200 |
| 总览接口 | `curl -s http://127.0.0.1:8000/api/dashboard/overview` | 非空 JSON |
| 金融/电信 | `/api/finance/summary`、`/api/telecom/summary` | 200 |
| 表结构 | `mysql -uroot -p -e "SHOW TABLES FROM complaint_analysis"` | 10 张表 |
| 集群连不通时 | 大屏其余页面正常，「集群控制」提示连接失败 | 符合预期（需目标机能 SSH 到 Hadoop 节点） |

## 六、常见问题

1. **`.env` 不在仓库里**：已 gitignore，新机器必须从 `.env.example` 复制并填数据库密码；Docker 模式由 compose 注入，可不建。
2. **MySQL 数据卷已有数据时不会重跑 initdb**：初始化脚本只在数据目录为空时执行。需要重新导入就用 `scripts/import_db.*` 手动执行。
3. **`import_db.py` 找不到 mysql 客户端**：Windows 装 MySQL Server 自带 `mysql.exe`（脚本内置常见路径探测），Linux 装 `mysql-client` 或把 `mysql` 加入 PATH。
4. **目标机无法连接集群**：`10.15.7.101:22` 需网络可达且账号可登录；不确定时设 `CLUSTER_MOCK=1` 先验证页面。
5. **中文目录**：`未清洗前的源数据/`、`mr/jar包/` 在 Windows/Linux 均可正常使用；Docker 挂载已在 compose 中配好，无需改路径。
6. **数据文件缺失时的表现**：pkl 缺失会回退读同名 CSV（更慢）；连 CSV 也没有时，`ccdb_text` 才会去读 `未清洗前的源数据/CCDB/`，该目录也没有则文本分析页数据为空。
7. **页面不依赖外网**：Vue、Element Plus、ECharts、three.js、字体、美国州界 GeoJSON 全部由 `backend/vendor/` 提供，断网或纯内网环境也能完整渲染。第三方库版本与许可证见 `backend/vendor/THIRD_PARTY_NOTICES.txt`。
