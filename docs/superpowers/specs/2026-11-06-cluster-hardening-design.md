# 集群控制台 · 运行可靠性与可观测性增强 · 设计规格

日期：2026-11-06
状态：待评审
范围：`backend/cluster_probe.py`（新建）+ `backend/cluster.py` 增量改造 + 集群控制页增量改造

---

## 1. 背景与目标

上一轮真实联调只验证了 `fcc_state` 一个任务（`FccStateCount.jar`，local 模式，约 18 分钟）全链路跑通：
提交 → 日志 → `part-r-*` 预览 → 写回 MySQL `fcc_state` → 大屏刷新。暴露出的问题集中在三类：

| 类别 | 具体问题 |
|---|---|
| 跑通 | 10 个 jar 只有 1 个真跑过；6 个 `main_class` 为 `null`（靠 MANIFEST），2 个是猜测值 `org.example.Main`；输入路径不存在要等十几分钟才报错；输出列数只在导入阶段才知道对不对 |
| 可观测 | local 模式没有 YARN application，进度只能靠 stderr 里的 `map x% reduce y%`，没有阶段、耗时、心跳；日志量大、无分级、无过滤 |
| 稳定性 | 停止依赖 `pkill -f "RunJar <jar>"` 字符串匹配；失败遗留输出目录导致下次“输出已存在”失败；SSH 断连后状态查询不稳定 |

本规格解决这三类问题，并追加两项能力：HDFS 结果导出为 CSV、运行过程可视化。不改数据表结构、不动其他大屏页面。

### 1.1 已确认的决策

| 决策项 | 结论 |
|---|---|
| 本轮范围 | 三块全做，顺序固定为「jar 跑通 → 可观测 → 稳定性」 |
| jar 验收方式 | 只做自动探测机制，不做批量试跑；哪个 jar 能跑由用户按需点击 |
| 自动探测内容 | ① 读 MANIFEST 得 Main-Class ② 输入路径预检 ③ 输出列数与分隔符探测 ④ 入库列结构校对 |
| 可观测内容 | ① 阶段/耗时/心跳 ② 日志分级着色与过滤 ③ 历史趋势与成功率 ④ 合并详情接口 |
| 稳定性内容 | ① 停止可靠化（按 PID） ② 手动一键清理目录 ③ 失败自动清理本次输出 ④ 连接自愈与轮询退避 |
| 代码落点 | 方案 B：新增 `cluster_probe.py` 存放纯探测函数，`cluster.py` 保留 SSH/调度/路由 |
| 结果导出 | 导出 HDFS 上该任务最近一次成功 run 的 `part-r-*`，合并为带表头 CSV（UTF-8 BOM），流式下载，不落临时文件 |
| 过程可视化 | 阶段轴 + 环形进度 + 60 秒日志吞吐曲线，纯内联 SVG，不引图表库 |

### 1.2 非目标

- 不为 10 个 jar 做批量自动试跑或结果比对。
- 不接入 YARN REST / ResourceManager Web UI（集群侧 8088、9870 不可达，只能走 SSH）。
- 不改 `cluster_jobs.json` 的任务集合与业务含义，只允许运行期以 MANIFEST 覆盖 `main_class`。
- 不改其他 6 个大屏页面与其数据接口。
- 不引入前端构建工具或第三方图表库。

---

## 2. 现状基线

| 模块 | 位置 | 现状 |
|---|---|---|
| 后端路由 | `backend/cluster.py`（581 行） | SSH 双 slot（`main`/`exec`/`monitor`）、`RUNS/ACTIVE/LAST`、ThreadPoolExecutor(2)、日志环形 5000 行、`/status` 5 秒缓存 |
| 任务配置 | `backend/cluster_jobs.json` | 10 个任务；`fcc_state` 已实跑通过 |
| 前端 | `backend/index.html`（6673 行） | 集群页已有状态卡、任务行、日志区、历史表；2 秒轮询 `/jobs/{id}/log` 与 `/status` |
| 环境变量 | `backend/.env` / `.env.example` | `CLUSTER_MOCK=0` 真实模式；`CLUSTER_ENV` 显式注入 hadoop 环境 |

### 2.1 数据集与输入目录（已用 `hdfs dfs -ls -h` 核验）

集群上 `/data` 只有三个输入域，与 `cluster_jobs.json` 现有默认值完全一致，无需改动路径：

| 数据集 | 路径 | 实测大小 | 用途 | 使用它的任务 |
|---|---|---|---|---|
| B · CFPB 结构化全量 | `/data/cfpb_struct/input/complaints_clean.csv` | 5.3 G（单文件） | 15 个结构化字段、无投诉原文；金融宏观大盘主数据源（月度/产品/州/企业/时效） | `company_count`、`product_count`、`state_count`、`timely_response`、`product_timely` |
| A · CFPB 文本子集 | `/data/cfpb_text/input/`（17 个 `CCDB_Export_*.csv`） | 6.1 G（目录合计） | 比 B 多一列 `Consumer complaint narrative`；只用于文本挖掘（词频、关键词、AI 分类），不用于总量统计 | `word_count`、`word_count2` |
| C · FCC 电信投诉 | `/data/fcc/input/fcc_consumer_complaints_clean.csv` | 586.7 M（单文件） | 电信工单日期、投诉类型、州、通话方式等；独立业务域，不与金融投诉合并 | `fcc_state`、`fcc_monthly`、`fcc_issue` |

约束：A 是目录、B/C 是单文件，`input_check` 对两者都用 `hdfs dfs -test -e`，不区分文件或目录；B 与 A 不可互相替代（A 少列、B 无原文）。

现有输入与输出目录：
- 当前 `/data/output` 下仅有 `fcc_state`、`timely_response` 两个目录，其余任务首次运行前输出路径不存在，符合“输出不存在才运行”的预检假设。


现有接口（保持不变）：`/test`、`/status`、`/jobs`、`/jobs/{id}/run`、`/jobs/{id}/kill`、`/jobs/{id}/log`、`/jobs/{id}/preview`、`/jobs/{id}/import`、`/history`。

---

## 3. 架构

```
index.html (cluster 页)
        │  fetch
        ▼
cluster.py（路由 + SSH + 调度 + 入库）
        │ 调用纯函数
        ▼
cluster_probe.py（无 SSH、无 DB 依赖，纯字符串/结构处理）
        └─ 被 tests/test_probe.py 直接单测
```

依赖方向单向：`cluster_probe` 不 import `cluster`；`cluster` 可以 import `cluster_probe`。探测函数一律接收已取到的文本/结构，不发命令、不连库，便于单测。

### 3.1 `cluster_probe.py` 函数清单

| 函数 | 输入 | 输出 |
|---|---|---|
| `main_class_from_manifest(text)` | MANIFEST.MF 全文 | `str \| None`；处理 72 字节续行、大小写键名、CRLF |
| `build_jar_command(jar_remote, main_class, input_path, output_path)` | 组件 | 完整 `hadoop jar ...` 命令字符串 |
| `detect_layout(sample_lines, expected_cols)` | 前若干行原文 + 期望列数 | `{"sep", "ncols", "mismatch", "sample"}` |
| `diff_columns(cfg_cols, db_cols)` | 配置列、`information_schema` 列 | `{"ok", "missing", "extra"}` |
| `input_check_cmd(path)` | HDFS 路径 | `hdfs dfs -test -e <path> && echo OK \|\| echo MISSING` |
| `parse_input_check(text)` | 上面命令的输出 | `bool`（`OK` → True，其余 False） |
| `guess_pid(text, jar_name)` | `pgrep -af` 输出 + jar 名 | 最新的 PID 或 `None`；必须命令行含 jar 名才采纳 |
| `csv_row(fields)` | 一行字段列表 | 按 RFC4180 转义的 CSV 单行（含结尾换行） |

`schema_query_sql(db)` 也放在此模块，返回 `information_schema.columns` 查询语句，避免在路由里拼 SQL。

---

## 4. 数据契约

### 4.1 run 新增字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `phase` | `"queued" \| "preflight" \| "uploading" \| "submitting" \| "running" \| "finalizing" \| "done" \| "failed" \| "killed"` | 当前阶段 |
| `phase_at` | ISO 时间串 | 进入当前阶段的时间 |
| `heartbeat` | ISO 时间串 | 最近一次收到日志的时间 |
| `pid` | `int \| None` | 运行期探测到的 RunJar 进程号 |
| `log_bytes` | `int` | 已写入日志文件的字节数 |
| `phase_log` | `[{"phase", "at"}]` | 阶段切换历史，最多 10 条 |
| `rate_series` | `int[60]` | 最近 60 个 1 秒桶的日志行数，环形覆盖 |
| `probe` | `dict` | 见 4.2 |

`state` 字段保持原语义（`queued/running/success/failed/killed/interrupted`），`phase` 是更细的过程信息，互不替代。

### 4.2 `probe` 结构

```json
{
  "main_class": "org.example.FccStateCount",
  "main_class_source": "manifest",
  "input_check": "ok",
  "output_existed": false,
  "layout": {"sep": "tsv", "ncols": 2, "mismatch": false, "sample": ["CA\t446841", "TX\t301119"]},
  "schema": {"ok": true, "missing": [], "extra": []},
  "checked_at": "2026-11-06T20:11:03"
}
```

未执行到的探测项保持 `null`，不写猜测值。历史记录只保存 `phase`、耗时与 `probe.main_class/source`，其余丢弃以控制体积。

---

## 5. 执行链路

```
queued → preflight → uploading → submitting → running → finalizing → done
                                            ↘ failed / killed（任一阶段可进入）
```

| 阶段 | 动作 | 失败处理 |
|---|---|---|
| `preflight` | 读远端 jar 的 `META-INF/MANIFEST.MF` 定 Main-Class；`hdfs dfs -test -e <input>`；`hdfs dfs -test -e <output>` | 无 Main-Class 且配置为空、输入不存在、输出已存在且未勾选覆盖 → `failed`，错误写明原因 |
| `uploading` | 远端缺 jar 时 SFTP 上传 | 上传异常 → `failed`，保留 SSH 错误原文 |
| `submitting` | 有 main_class 走 `hadoop jar X.jar <MainClass> in out`，无则 `hadoop jar X.jar in out`；命令尾 `2>&1` 流式读取 | 非 0 退出 → `failed` |
| `running` | 每行刷新 `heartbeat`/`log_bytes`，持续解析 `map/reduce` 百分比与 `application_*` | 同上 |
| `finalizing` | 读 `part-r-*` 前 5 行做 `detect_layout` | 读不到 part 文件 → 记录 warning，不判失败（部分 jar 无输出也属正常） |
| `done` | 若勾选入库：先 `diff_columns`，再事务写入 | 列结构不符 → 不入库，`import_state=failed` 并写明缺失列 |

关键约束：

1. **不盲跑**：任何 preflight 失败都在无人值守前终止，并保留可读原因。
2. **覆盖语义不变**：勾选覆盖时先 `-rm -r -skipTrash <output>`，再提交；不勾选且目录存在则失败。
3. **失败清理**：仅当本次 run 自己产生过输出目录（preflight 时记录它原本不存在）时，`failed` 后自动 `-rm -r -skipTrash <output>`，并在日志里记录被删路径。原本就存在的目录不碰。
4. **停止不覆盖状态**：`killed` 优先级高于随后到达的退出码（沿用现有保护）。

---

## 6. 停止与连接自愈

**取 PID**：命令提交后约 1 秒，用 `monitor` 连接执行 `pgrep -af "RunJar"`，由 `guess_pid` 匹配 jar 文件名，取最新的一个写入 `run["pid"]`。取不到不影响任务运行，只降低停止精度。

**停止**：先 `ps -p <pid> -o args=` 校验命令行含该 jar；通过则 `kill <pid>`，1 秒后仍存活再 `kill -9`。校验不通过或无 PID 时才退回 `[R]unJar <jar>` 兜底。日志回显「已停止 PID 12345 / 兜底 pkill」。

**连接自愈**：`run_cmd` 出现 `SSH_ERROR` 时将该 slot 从 `_clients` 移除，下次调用自动重建；`/status` 只有在命令成功时才写 5 秒缓存。前端轮询失败按 2s → 5s → 10s 退避，成功一次回到 2s，并在连接条上提示「连接异常，重试中」。

---

## 7. 接口

### 7.1 新增

**`GET /api/cluster/runs/{run_id}/detail?lines=200`**

一次返回 run 全字段（含 `phase_log`、`rate_series`）+ 计算后的 `elapsed_sec`/`log_rate` + 最近 N 行日志：

```json
{
  "ok": true,
  "run": {"run_id": "...", "phase": "running", "elapsed_sec": 742, "log_rate": 3.1, "probe": {...}},
  "lines": ["..."]
}
```

未知 `run_id` → 404。

**`GET /api/cluster/jobs/{job_id}/export?run_id=<可选>`**

导出 HDFS 结果 CSV。选 run 规则：传了 `run_id` 用它，否则取该任务最近一次成功 run；都没有 → 409。用 `exec` 连接执行 `hdfs dfs -cat <output>/part-r-*` 流式读取，首行写配置 `columns` 表头，字段按 RFC4180 转义（含逗号、引号、换行时加引号），编码 UTF-8 带 BOM。

响应头：`Content-Type: text/csv; charset=utf-8`、`Content-Disposition: attachment; filename="<job_id>_<YYYYmmdd_HHMM>.csv"`。输出目录不存在 → 404；输出为空 → 仅表头；MOCK 模式返回内置两行假数据。

**`POST /api/cluster/jobs/{job_id}/preflight`**

不跑任务，只做体检：读远端 MANIFEST、检查输入、检查输出是否存在、查目标表列并 `diff_columns`。响应体即 `probe` 结构。SSH 不可用 → 503，附错误原因。

**`POST /api/cluster/jobs/{job_id}/cleanup`**

```json
{"path": "/data/output/fcc_state_stoptest"}
```

`path` 省略时用该任务的 `default_output`。只允许规范化后落在 `/data/output/` 之下、且不含 `..`；否则 400。执行 `hdfs dfs -rm -r -skipTrash`，返回 `{"ok": true, "path": "..."}`。

**`GET /api/cluster/runs/{run_id}/log/download`**

返回 `text/plain; charset=utf-8` 的 `.cluster_logs/<run_id>.log`，文件名带 run_id。文件不存在 → 404。

### 7.2 变更

- `POST /jobs/{id}/run`：新增可选字段 `preflight_only`（默认 false）；run 结构新增 `phase/probe` 等字段。
- `GET /jobs/{id}/log`：响应追加 `phase`、`heartbeat`、`pid`、`probe`；`lines` 语义不变（保证旧前端兼容）。
- `/history`：每条新增 `phase`、`duration_sec`、`main_class`；读取旧记录时缺字段按 `null` 处理。

---

## 8. 前端改动（仅 cluster 页）

1. **任务行**：`phase` 徽标；进度区有 `map/reduce` 时显示百分比，否则显示阶段中文名；已耗时由本地 1 秒计时器计算，不发请求；`heartbeat` 超过 120 秒显示灰字「无输出 Ns」。
2. **日志区**：按 `ERROR`/`WARN`/`INFO` 正则着色；关键词输入框实时过滤（纯前端）；自动滚动开关（滚动到底自动开启，用户上滚 20px 即暂停）；「下载日志」按钮走新接口。
3. **体检**：每个任务行加「体检」按钮 → 弹层展示 Main-Class 及来源、输入状态、输出是否存在、表结构差异。
4. **详情**：日志面板轮询改为 `/runs/{run_id}/detail`，一次拿到全部信息（含 `phase_log`/`rate_series`）；样例行展示在日志头上方。
5. **阶段轴与环形进度**：运行卡展示六段阶段轴（已过阶段实心、当前阶段脉动、失败段变红）；环形进度优先用 `map*0.6 + reduce*0.4`，无百分比时按阶段权重（5/10/5/70/10）推进。
6. **吞吐曲线**：用 `rate_series` 画最近 60 秒日志行数折线（内联 SVG，纵轴自适应峰值）；仅运行中更新，结束后保留最后一帧。
7. **导出**：任务行在存在成功 run 时显示「导出」按钮，直接触发浏览器下载 CSV，不走 XHR。
8. **历史**：新增「耗时」列；顶部一行统计（成功/失败数、平均耗时）；用一条内联 SVG 画耗时迷你趋势，不引库。
9. **清理**：任务行「清理输出」→ `confirm` 二次确认 → `/cleanup`，成功后把输出路径输入框清空并提示。
10. 新样式只追加 `/* ===== 集群控制台 · 增强 ===== */` 区块，深色主题为主，浅色覆盖随既有规则补一条；不改其他页面样式。

---

## 9. 错误处理与边界

| 场景 | 处理 |
|---|---|
| jar 无 Main-Class 且配置为空 | `failed`，错误「jar 未声明 Main-Class，请在 cluster_jobs.json 填写 main_class」 |
| 输入路径不存在 | `failed`，耗时通常在数秒内 |
| 输出目录已存在且未覆盖 | `failed`，提示「可勾选覆盖或先清理输出目录」 |
| 输出列数与配置不符 | `probe.layout.mismatch=true`，不自动入库；详情面板标红 |
| 目标表缺列 | `import_state=failed`，写明缺失/多余列名 |
| 取不到 PID | 不影响运行；停止走兜底 pkill，日志注明「兜底」 |
| SSH 断连 | slot 失效后自动重建；前端退避轮询，不计任务失败 |
| 日志过大 | 内存保留 5000 行环形（沿用）；磁盘文件不截断，供下载 |
| 没有成功 run 却点导出 | 按钮置灰；直接访问接口返回 409 |
| 导出中途 SSH 中断 | 已发出的表头与部分行无法回收，浏览器得到截断文件；页面提示重新导出 |
| 结果字段含逗号/引号/换行 | 按 RFC4180 转义，Excel 可正确解析 |
| 导出大结果 | 流式读取，后端内存恒定；耗时取决于网络 |
| MOCK 模式 | 所有探测返回 `null` 或内置假值，导出返回内置两行假数据，页面仍可演示 |

---

## 10. 测试策略

**单测（新增 `backend/tests/test_probe.py`）**

- MANIFEST：正常、含续行、无 `Main-Class`、CRLF；
- `build_jar_command`：有无 main_class 两种形态；
- `detect_layout`：tab / 逗号 / 单列 / 列数不符 / 空行；
- `diff_columns`：完全一致、缺列、多列；
- `parse_input_check`：`OK` / `MISSING` / 混合输出；
- `guess_pid`：多进程时取最新、命令行不含 jar 时返回 None；
- `csv_row`（新增到 `cluster_probe.py`）：普通字段、含逗号、含引号、含换行、空值。

**手动验收（不批量跑 jar）**

1. 对 `company_count` 点「体检」：能看到 Main-Class 与来源、输入 OK、输出状态。
2. 造一个不存在的输入路径提交：数秒内 `failed`，原因正确。
3. 提交 `fcc_state`（勾选覆盖 + 入库）：阶段依次变化，日志分级着色，耗时与心跳更新，结束后列结构校对通过。
4. 运行中点「停止」：`killed` 保持，日志回显 PID。
5. 失败 run 留下输出目录时自动清理；手动清理旧 `*_stoptest` 目录成功。
6. 断网/断 SSH 期间刷新页面：连接条提示重试，恢复后自动回到正常。
7. 对已成功的 `timely_response` 点「导出」：CSV 首行为表头，行数与 `part-r-*` 一致，Excel 打开无乱码。
8. 运行中观察阶段轴、环形进度、吞吐曲线随时间变化；无 `map/reduce` 百分比时环形仍按阶段推进。
9. 无成功 run 的任务「导出」按钮为置灰状态；直接请求接口返回 409。

---

## 11. 兼容与迁移

- 旧 `/log` 接口保留且 `lines` 语义不变，前端可逐步切换。
- `cluster_history.json` 中新字段缺失时按 `null` 渲染，不做数据迁移。
- `cluster_jobs.json` 不需要修改：Main-Class 以运行期 MANIFEST 为准，配置值仅作兜底。
- `CLUSTER_MOCK=1` 下探测全部走假值，页面功能可离线演示。

## 12. 风险

| 风险 | 取舍 |
|---|---|
| `pgrep -af "RunJar"` 在共享集群可能匹配到别人的任务 | `guess_pid` 必须命中 jar 文件名，且停止前二次校验 cmdline |
| MANIFEST 缺失（部分打包工具不写） | 配置兜底；两者都没有则明确失败，不猜测 |
| local 模式无 YARN app，进度仍可能长时间不动 | 用阶段 + 心跳 + 「无输出 Ns」提示替代百分比 |
| 自动清理误删 | 只删本次 run 产生且原本不存在的输出路径，路径先经 `validate_path` |
| 流式导出中途断连 | 只能返回截断文件，无法在流中改状态码；前端提示重新导出 |
| `cluster.py` 继续变大 | 探测逻辑外置后，本文件预估 ≤ 750 行；若继续膨胀再拆执行层 |
