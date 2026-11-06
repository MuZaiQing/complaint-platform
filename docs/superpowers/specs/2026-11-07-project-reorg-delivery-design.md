# 项目整理归类与一键交付设计（方案 A+C）

日期：2026-11-07
状态：已获用户确认（目录结构逐项确认）

## 背景与目标

多源消费者投诉智能分析与预警平台（FastAPI + MySQL + Vue3 单文件大屏 + Hadoop 集群控制台）根目录混杂：16GB 大数据、MR jar/源码、调试残留、交付物平铺。用户要求：

1. 目录整理归类、结构清晰（中力度：大数据入 data/、MR 入 mr/、杂项入 archive/，代码不动）
2. 数据库内容导出，可在其他 Windows/Linux 主机一键入库（mysqldump 全量 SQL + 跨平台引导脚本）
3. 项目启动/停止脚本（原生 .bat + .sh 双套）
4. 调试残留归档（仅归档，不做代码级精简）
5. 方案 C：git init 首次快照，使迁移可回滚、code-review 插件后续可用

约束：集群控制台刚验收，不得破坏；backend 逻辑零改动（仅路径常量默认值）；大数据同盘 Move-Item（秒级）；迁移后需重启 8000 端口服务并回归。

## 目标目录结构

```
d:\fqh\
├── backend/            # 不动；新增 backend/logs/（启停日志与 PID）
├── data/               # 大数据：complaints_clean.csv/pkl、ccdb_text.pkl、
│   │                   #   fcc_consumer_complaints_clean.csv/pkl
│   ├── CCDB/           # 17 个原始导出 CSV
│   └── mr_result/      # 13 个集群结果 txt
├── mr/
│   ├── jar包/          # 10 个 jar
│   └── src/            # 原 example/，10 个 .java
├── archive/            # debug.log、ai.txt、clean_validation_report.csv、
│   │                   #   项目描述.txt、screenshots/（原 .screenshots/）
├── scripts/            # start/stop/export_db/import_db 双平台脚本
├── dist/               # 交付物（新增 dist/db/ 放 dump）
├── docs/、.superpowers/ # 不动
├── .git/、.gitignore   # 新增
├── Dockerfile / docker-compose.yml / .dockerignore  # 改路径引用
└── .env.example        # 根级新增说明样例
```

## 迁移清单（Move-Item）

| 源 | 目标 |
|---|---|
| complaints_clean.csv / .pkl | data/ |
| ccdb_text.pkl | data/ |
| fcc_consumer_complaints_clean.csv / .pkl | data/ |
| CCDB/ | data/CCDB/ |
| mr_result/ | data/mr_result/ |
| jar包/ | mr/jar包/ |
| example/ | mr/src/ |
| debug.log、ai.txt、clean_validation_report.csv、项目描述.txt | archive/ |
| .screenshots/ | archive/screenshots/ |

## 路径引用同步修改

| 位置 | 现值 | 改为 |
|---|---|---|
| backend DATA_ROOT 默认值 | `D:\fqh` | `D:\fqh\data` |
| backend JAR_DIR 默认值（cluster.py） | `D:\fqh\jar包` | `D:\fqh\mr\jar包` |
| backend/.env、.env.example | `JAR_DIR=D:\fqh\jar包` | `JAR_DIR=D:\fqh\mr\jar包` |
| docker-compose 卷 | `./:/data:ro`、`./jar包:/jars:ro` | `./data:/data:ro`、`./mr/jar包:/jars:ro` |
| .dockerignore | `CCDB/`、`mr_result/` | `data/` 前缀 |

先 grep 全部出现点再改，确保无遗漏。.env 显式值优先于代码默认值，两边都改。

## 数据库一键入库

- 导出：`scripts/export_db.bat` / `export_db.sh`
  - 从 backend/.env 读连接参数（可被环境变量覆盖）
  - `mysqldump --routines --triggers --single-transaction --default-character-set=utf8mb4`
  - 输出 `dist/db/complaint_analysis_YYYYMMDD.sql`；若库 >1GB 自动 gzip（.sql.gz）
- 入库：`scripts/import_db.py`（跨平台，Python 3.8+ 标准库实现）
  - 依次在 PATH 与常见安装目录找 `mysql` 客户端；自动解压 .gz
  - 参数：--host/--port/--user/--password/--db（缺省读环境变量，再缺省交互提示）
  - `CREATE DATABASE IF NOT EXISTS ... CHARACTER SET utf8mb4` → 导入 → 打印各表行数校验
  - `import_db.bat` / `import_db.sh` 为一行包装
- 实施时先查当前库实际大小以决定是否默认 gzip

## 启停脚本

- `scripts/start.bat`：定位 Python（优先 `D:\ruan_jain_an_zhuang\python-3.13.7\python.exe`，兜底 PATH）→ 检查依赖（fastapi/pymysql 可 import）→ 检查 8000 端口占用 → 后台启动 uvicorn（日志 `backend/logs/app.log`，PID 写 `backend/logs/app.pid`）→ 轮询健康检查直到就绪或超时
- `scripts/stop.bat`：读 PID 文件 taskkill；无 PID 则按 8000 端口查杀
- `scripts/start.sh` / `stop.sh`：nohup + PID 文件；stop 兜底 `lsof -i:8000` / `fuser`
- 输出中文成败信息，失败给非零退出码

## git 快照与 .gitignore

- `git init`；迁移前先 commit 0（记录迁移前状态不可行——大文件太多，改为迁移后首次 commit，迁移本身用 Move-Item 即时完成）
- 决策：先建 .gitignore（排除 data/、dist/、archive/、.screenshots、backend/.env、backend/logs/、__pycache__、*.pkl、*.csv），再 git init + add + commit「初始快照：目录整理后结构」

## 验证

1. `D:\ruan_jain_an_zhuang\python-3.13.7\python.exe -m pytest backend/tests` 全量单测（31+20 项）
2. 重启 8000 端口，浏览器回归大屏各 tab + 集群控制台（preflight 抽查 2 个任务）
3. export_db 实跑一次产出 dist/db dump；import_db 用 `--help`/干跑校验参数解析（不在本机真实导入，避免覆盖现库；可在本机导入到临时库名验证）
4. start.bat/stop.bat 本机实测一轮
5. start.sh/stop.sh 做静态检查（bash -n 不可用则人工核对语法）
6. docker compose config 校验（如本机有 Docker）
7. 重新打包 dist 源码 zip（新结构）

## 不做（YAGNI）

- 不做代码级精简/重构（用户明确只选归档调试残留）
- 不删除任何归档内容
- 不动 backend/ 内部结构与前端
- 不引入 CI、不做远程仓库推送
