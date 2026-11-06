# 集群控制台页面 · 设计规格

日期：2026-11-06
状态：待评审
范围：双主题大屏新增「集群控制」页 + 后端 Hadoop 集群接入（SSH）

---

## 1. 背景与目标

大屏现有数据来自本地 MySQL `complaint_analysis`，由 `D:\fqh\jar包` 下的 10 个 MapReduce 程序在 Hadoop 集群
（`10.15.7.101`，用户 `hadoop`）上计算后得到。目前集群与项目完全割裂：跑任务要手工 SSH，结果要手工搬运。

本页目标：在同一个大屏内完成 **集群状态监控 → 选择 jar → 提交任务 → 查看日志 → 可选写回 MySQL → 刷新大屏数据** 的闭环。

### 1.1 已确认的需求边界

| 决策项 | 结论 |
|---|---|
| 页面能力 | 监控 + 任务提交一体化 |
| 集群接入 | 后端 `.env` + SSH（paramiko），密码不进前端 |
| 任务粒度 | 10 个 jar 全量列出，可任选单个运行 |
| 结果入库 | 可选：每个任务独立开关「完成后写入 MySQL」，默认关 |
| 运行参数 | 输入/输出 HDFS 路径可编辑，可一键恢复默认 |
| 输出路径 | 默认 `/data/output/<任务id>`，运行前可选覆盖（`rm -r -skipTrash`） |

### 1.2 集群侧已知事实

HDFS 现有输入（来自集群实拍截图）：

| 数据 | 路径 | 大小 |
|---|---|---|
| CFPB 结构化 | `/data/cfpb_struct/input/complaints_clean.csv` | 573,461,572 B |
| CFPB 文本 | `/data/cfpb_text/input/`（17 个 `CCDB_Export_*.csv`） | 目录 |
| FCC 清洗数据 | `/data/fcc/input/fcc_consumer_complaints_clean.csv` | 61,515,272 B |

端口探测（本机 → 集群）：仅 `22` 可达；`9870` / `8088` / `3306` 不可达。因此所有集群操作走 SSH 命令行，
不做 YARN REST 集成。

---

## 2. 现状（改造基线）

| 模块 | 位置 | 与本页的关系 |
|---|---|---|
| 前端 | `backend/index.html`（单文件，Vue3 CDN + ECharts + Three.js） | 新增页面区块、导航项、`cluster` 状态与轮询逻辑 |
| 页面登记 | `index.html` 内 `const pages = [...]` | 追加 `{ key: 'cluster', label: '集群控制' }` |
| 后端 | `backend/main.py`（FastAPI，约 830 行） | 挂载 `cluster` 路由、启动时加载 `.env` |
| 数据层 | `pymysql` + `DB_CONFIG`（环境变量优先） | 入库复用同一套连接参数 |
| 统计表 | `main.py` 的 `STATS_TABLES` | 入库目标表的列名以此为准 |

`STATS_TABLES` 中与本页相关的表：

```
fin_company         (company_name, complaint_count)
fin_product         (product_name, complaint_count)
fin_state           (state_code, complaint_count)
fin_timely_response (response_flag, complaint_count)
fin_product_timely  (stat_key, complaint_count)
fin_word_freq       (word, freq)
fcc_state           (state_code, complaint_count)
fcc_monthly         (stat_month, complaint_count)
fcc_issue           (issue_name, complaint_count)
```

`fin_monthly` 没有对应的 jar，本页不创建该任务（不制造错误数据）。

---

## 3. 架构

```
┌──────────────────────────────────────────────────────────┐
│ backend/index.html  ——  新页 activePage === 'cluster'     │
│  2s 轮询 /api/cluster/jobs 与 /api/cluster/status          │
└───────────────────────────┬──────────────────────────────┘
                            │ HTTP
┌───────────────────────────▼────────────────────────────────┐
│ backend/cluster.py  (APIRouter, 前缀 /api/cluster)         │
│  ├─ ssh.py 部分：SSHClient 单例（懒连接/自动重连/15s 超时） │
│  ├─ runner：ThreadPoolExecutor(max_workers=2)              │
│  │    · 每任务 id 同时只允许 1 个实例                        │
│  │    · 日志环形缓冲（每任务最近 300 行 + 全量落盘）          │
│  │    · 状态机 queued→running→success/failed/killed         │
│  └─ importer：hdfs dfs -cat 输出 → 解析 → 本地 MySQL 事务   │
└───────────┬───────────────────────────────┬───────────────┘
            │ SSH (paramiko)                │ pymysql
┌───────────▼──────────────┐    ┌──────────▼──────────────────┐
│ 10.15.7.101 (hadoop)     │    │ 本地 MySQL                   │
│ /home/hadoop/jars/*.jar  │    │ complaint_analysis           │
│ /data/...                │    │ fin_* / fcc_* 表             │
└──────────────────────────┘    └──────────────────────────────┘
```

### 3.1 新增文件

| 文件 | 作用 |
|---|---|
| `backend/cluster.py` | 集群路由 + SSH + 任务调度 + 入库（单文件，约 400 行） |
| `backend/cluster_jobs.json` | 10 个任务的元数据配置（可直接改，不需改代码） |
| `backend/.env` | 集群与数据库凭据（不入库、不进前端） |
| `backend/.env.example` | 配置模板，含全部字段与注释 |
| `backend/tests/test_cluster.py` | 不依赖集群的单测（mock SSH / mock DB） |
| `docs/superpowers/specs/2026-11-06-cluster-console-design.md` | 本文件 |

### 3.2 修改文件

| 文件 | 改动 |
|---|---|
| `backend/main.py` | 顶部 `load_dotenv()`；`include_router(cluster.router)`（页面仍由现有单文件 SPA 渲染） |
| `backend/index.html` | `pages` 数组追加项；新增 `cluster` 页模板、状态、轮询、样式 |
| `backend/requirements.txt` | 追加 `paramiko>=3.4,<4.0`、`python-dotenv>=1.0,<2.0` |

---

## 4. 任务配置 `cluster_jobs.json`

```jsonc
{
  "jobs": [
    {
      "id": "company_count",
      "name": "金融 · 企业投诉量",
      "jar": "CompanyCount.jar",
      "main_class": null,                     // null = 用 jar 清单里的 Main-Class
      "default_input": "/data/cfpb_struct/input/complaints_clean.csv",
      "default_output": "/data/output/company_count",
      "target_table": "fin_company",
      "columns": ["company_name", "complaint_count"],
      "import_enabled": false,
      "description": "按企业聚合 CFPB 投诉"
    }
  ]
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `id` | 唯一标识，同时用作输出子目录与前端 key |
| `name` | 页面显示名 |
| `jar` | `D:\fqh\jar包` 内的文件名（首次运行自动上传到 `/home/hadoop/jars/`） |
| `main_class` | 可选覆盖。`hadoop jar <jar> <main_class> <in> <out>` |
| `default_input` / `default_output` | 页面「恢复默认」用 |
| `target_table` | 写回 MySQL 的表名（必须在 `STATS_TABLES` 中） |
| `columns` | Reducer 输出两列到表两列的映射顺序 |
| `import_enabled` | 该任务「写入 MySQL」开关的默认值 |
| `parser` | 可选：`"tsv"`（默认）/ `"csv"` |

10 条默认配置：

| id | jar | 默认输入 | 目标表 |
|---|---|---|---|
| `company_count` | CompanyCount.jar | `/data/cfpb_struct/input/complaints_clean.csv` | fin_company |
| `product_count` | ProductCount.jar | 同上 | fin_product |
| `state_count` | state_count.jar | 同上 | fin_state |
| `timely_response` | TimelyResponseCount.jar | 同上 | fin_timely_response |
| `product_timely` | ProductTimelyCount.jar | 同上 | fin_product_timely |
| `word_count` | NarrativeWordCount.jar | `/data/cfpb_text/input/` | fin_word_freq |
| `word_count2` | NarrativeWordCount2.jar | `/data/cfpb_text/input/` | fin_word_freq（默认入库关） |
| `fcc_state` | FccStateCount.jar | `/data/fcc/input/fcc_consumer_complaints_clean.csv` | fcc_state |
| `fcc_monthly` | FccMonthlyCount.jar | 同上 | fcc_monthly |
| `fcc_issue` | FccIssueCount.jar | 同上 | fcc_issue |

> 输出格式默认假设为 Hadoop `TextOutputFormat` 的 `key\tvalue`。若实际输出为 `key,value` 或三列以上，
> 在 `cluster_jobs.json` 里改 `parser` / `columns` 即可，无需改代码。

---

## 5. 后端接口

统一前缀 `/api/cluster`。所有响应 `application/json`，错误统一 `{"ok": false, "error": "...", "detail": "..."}`，HTTP 状态码 200（前端按 `ok` 判断），仅参数非法返回 400/404。

| 方法 | 路径 | 入参 | 出参（关键字段） |
|---|---|---|---|
| GET | `/status` | — | `connected, host, user, hdfs{used,total,pct}, nodes{total,active}, apps{running}, checked_at` |
| POST | `/test` | — | `ok, hostname, hadoop_version, latency_ms` |
| GET | `/jobs` | — | `jobs: [{id,name,jar,input,output,import_to_mysql,state,import_state,last_run,progress}]` |
| POST | `/jobs/{id}/run` | `{input, output, overwrite, import_to_mysql}` | `run_id, state` |
| POST | `/jobs/{id}/kill` | — | `ok, app_id` |
| GET | `/jobs/{id}/log` | `?offset=0` | `offset, lines[], state, progress, app_id` |
| GET | `/jobs/{id}/preview` | — | `lines[]`（`hdfs dfs -cat <output>/part-r-* \| head -20`） |
| POST | `/jobs/{id}/import` | — | `ok, rows, table, seconds` |
| GET | `/history` | `?limit=20` | `runs: [{run_id,id,name,state,started,ended,duration,rows_out,rows_imported}]` |

### 5.1 状态机

```
queued ──► running ──► success
                 ├──► failed
                 ├──► killed        （用户停止，或 YARN 返回 FAILED）
                 └──► interrupted   （服务重启时检测为 running 的记录）
```

- `progress` 由日志解析：`map 60% reduce 20%` → `{map:60, reduce:20}`；解析不到时为 `null`（前端显示不确定进度条）。
- 每个 `id` 同时只允许一个实例；重复提交返回 `{"ok":false,"error":"该任务正在运行"}`。

### 5.2 执行流程（run）

1. 校验路径：必须以 `/` 开头，只允许 `[A-Za-z0-9._/-]`，禁止 `..`；否则 400。
2. 校验 `target_table` 在 `STATS_TABLES` 白名单内（仅在 `import_to_mysql` 为真时）。
3. 确保 jar 在集群：`ls -l /home/hadoop/jars/<jar>`；缺失则 SFTP 上传，比对大小。
4. `overwrite=true` → `hdfs dfs -rm -r -skipTrash <output>`（忽略“不存在”错误）。
5. `hadoop jar /home/hadoop/jars/<jar> [main_class] <input> <output>`，`stderr` 合并进日志。
6. 从日志抓 `application_1xxx_xxxx` 作为 `app_id`。
7. 进程退出码 0 → `success`，否则 `failed`（日志尾部作为错误摘要）。
8. 若 `import_to_mysql` → 调用入库；入库单独成败，不改变 MR 状态，只置 `import_state`。

### 5.3 停止（kill）

优先 `yarn application -kill <app_id>`；若尚未拿到 `app_id`，直接关闭 SSH channel 并标记 `killed`。

### 5.4 入库（import）

1. `hdfs dfs -cat <output>/part-r-*`（流式逐行读，避免大文件全量入内存）。
2. 按 `parser` 切分；行数/列数不符 → 失败并提示前 3 行原文，引导改配置。
3. 本地 MySQL 单事务：`DELETE FROM <table>` + 分批 `INSERT`（每批 1000 行）。
4. 返回 `rows`（写入行数）、`seconds`。

> 之所以用「清空再写」：现有 `STATS_TABLES` 全是全量快照表（大屏直接全读），增量 upsert 无意义，
> 且 MR 输出本身是全量结果。

### 5.5 连接与容错

| 场景 | 行为 |
|---|---|
| SSH 认证失败 | `/status` 返回 `connected:false, error:"Authentication failed"`；run 直接拒绝 |
| SSH 超时 | 后端 15s 超时，自动重连 1 次；仍失败则报错 |
| `hadoop` 不在 PATH | 执行 `command -v hadoop` 预检，缺失时给出明确提示 |
| 服务重启 | 启动时把 `running` 记录改为 `interrupted`，日志保留 |
| 日志过大 | 内存只保留最近 300 行；全量写 `backend/.cluster_logs/<run_id>.log` |

---

## 6. 前端页面

### 6.1 导航与页面

- `pages` 数组追加 `{ key: 'cluster', label: '集群控制' }`，位置放在「智能预警中心」之后。
- 页面容器 `v-if="activePage === 'cluster'"`，复用现有 `.card`、`.page-enter`、`--fin-top1` 等变量。
- 进入页面时启动 2s 轮询，离开或 `document.hidden` 时停止（复用现有预警轮播的可见性判断方式）。

### 6.2 布局（桌面 1440）

```
┌ 指标卡 ×4 ────────────────────────────────────────────┐
│ HDFS 已用/总量   YARN 节点   运行中任务   近24h 成功    │
├ 连接条 ───────────────────────────────────────────────┤
│ ● 10.15.7.101 · hadoop · 已连接    [测试连接]          │
├ 任务列表 (7fr) ──────────────────────┬ 日志 (5fr) ─────┤
│ ▸ 10 行任务，每行：                    │ 等宽日志         │
│   名称 / jar / 状态徽标                │ 自动滚底         │
│   输入路径（可编辑）                   │ [清屏][复制]     │
│   输出路径（可编辑）                   │                 │
│   [写入MySQL 开关] [运行][停止][日志]  │                 │
├ 运行记录表 ───────────────────────────────────────────┤
│ 时间 / 任务 / 状态 / 耗时 / 输出行数 / 入库行数        │
└───────────────────────────────────────────────────────┘
```

- 任务行默认折叠为一行，点击展开路径与按钮，避免 10 行撑爆首屏。
- 「运行」置灰条件：SSH 未连接、该任务 running、该任务 id 已在队列。
- 状态徽标：`排队中`（灰）、`运行中`（蓝，带朴素进度条）、`成功`（绿）、`失败`（红）、`已停止`（灰）、`入库失败`（橙）。
- 深色主题沿用现有深空配色；浅色主题沿用奶油学术底，状态色用 `--fin-top1` 系派生的低饱和版本。
- 移动端（≤900px）：单列堆叠，日志面板高度收到 260px。

### 6.3 视觉约束

- 与全站一致：卡片无发光边框、无扫描线、无脉冲动画。
- 进度条：1px 高底色 + 实色填充，无渐变光效。
- 数字与路径使用等宽字体（`ui-monospace`）。

---

## 7. 安全

| 项 | 做法 |
|---|---|
| 凭据 | 仅 `.env`；接口不回显密码；前端不提供连接设置表单 |
| 命令注入 | 路径白名单正则 + 参数拼接采用 list 形式传入 `exec_command` 前先 quote |
| 危险命令 | 仅允许固定模板（`hdfs dfs -ls/cat/rm/df`、`yarn node/application`、`hadoop jar`） |
| 覆盖保护 | `overwrite` 默认 false；输入路径禁止出现在输出路径覆盖范围内 |
| 文件 | `.env`、`.cluster_logs/`、`cluster_history.json` 加入 `.gitignore`（若后续建仓） |
| 权限 | 不新增任何写集群文件的接口（jar 只读上传一次） |

---

## 8. 测试与验收

### 8.1 单测（`python -m unittest backend/tests/test_cluster.py`）

- 路径校验：合法/非法（相对路径、`..`、`;`、空格）
- 日志解析：`map 40% reduce 0%`、`application_xxx` 抓取、异常输出
- 输出解析：`key\tvalue` 正常、列数不符、空文件
- 历史记录：写盘 / 读盘 / 损坏 JSON 容错
- 全部用 mock SSH / mock pymysql，不依赖网络与数据库

### 8.2 页面验收

| 场景 | 判据 |
|---|---|
| 断连态 | 顶部红条显示原文错误，运行按钮全禁用 |
| 运行中 | 进度条随轮询推进，日志持续追加，无重复行 |
| 成功 | 状态绿色，运行记录出现耗时与行数 |
| 失败 | 状态红色，日志尾部展示 Java 异常摘要 |
| 深浅主题 | 两套配色下对比度 ≥ 4.5:1，无漏改 |
| 移动端 390×844 | 单列、无横向溢出、日志区可独立滚动 |
| console | 0 error |

### 8.3 真实集群验证（需用户确认后执行）

1. `POST /api/cluster/test` 返回 hostname 与 `hadoop version`
2. 用最小的 `fcc_state` 任务跑一次，确认日志、`part-r-00000` 生成
3. 打开「写入 MySQL」再跑一次，确认 `fcc_state` 行数变化且大屏数字同步更新
4. 停止：运行中点击「停止」，确认 YARN 应用变为 KILLED

> 本轮实现不主动连接真实集群；需在用户明确同意后执行上述 4 步。

---

## 9. 不在本次范围

- 定时调度 / cron 自动重跑（后续可加）
- 多集群、多用户、权限体系
- YARN/HDFS Web UI 反向代理（8088/9870 端口不通）
- 浏览器端上传 HDFS 数据文件
- `fin_monthly` 的数据生成（没有对应 jar）
- WebSocket 实时日志（当前用 2s 轮询）
- 任务依赖编排（如先跑 A 再跑 B）

---

## 10. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| jar 输出格式与假设不符 | 入库失败 | 页面提供「预览输出」；解析失败时展示原文并提示改 `cluster_jobs.json` |
| jar 的 Main-Class 与清单不一致 | 报 ClassNotFound | 配置支持 `main_class` 覆盖，页面可直接改并重跑 |
| 大结果集入库耗时 | 接口超时 | 入库在后台线程执行，页面轮询 `import_state`；分批 1000 行 |
| SSH 单连接被长任务占用 | 状态查询卡住 | SSH 连接池：1 条执行连接 + 1 条监控连接，互不阻塞 |
| MR 日志被 ANSI 控制符污染 | 页面显示乱码 | 后端剥离 `\x1b[...m` 转义 |
