
本项目有两条独立业务线（金融 CFPB、电信 FCC），数据从公开源采集后，经本地探查与清洗、Hadoop MapReduce 统计，最终落 MySQL 供大屏读取。

## 总览

```
CFPB 官网 archive.html                     FCC 公开投诉数据
        │  pipeline/collect_narratives.py（curl 并发 + CRC + sha256 清单）
        ▼                                          │
17 份 Export zip → 解压 CSV（未清洗）              │
        │                                          │
        ▼                                          ▼
未清洗前的源数据/CCDB/（17 份 CCDB_Export_*.csv）       fcc_consumer_complaints.csv（未清洗）
complaints.csv（未清洗，未随项目保存）             │
        │                                          │
        │  数据清洗源码/explore*.py（只读探查，改造前摸底）
        │  数据清洗源码/clean*.py（另存清洗产物，原文件不动）
        ▼                                          ▼
data/complaints_clean.csv/.pkl              data/fcc_consumer_complaints_clean.csv/.pkl
data/ccdb_text.pkl                                  │
        │                                          │
        ▼                                          ▼
HDFS /data/cfpb_struct/input/                HDFS /data/fcc/input/
HDFS /data/cfpb_text/input/                        │
        │                                          │
        └────────► 10 个 MapReduce 任务 ◄──────────┘
                   （mr/jar包 + mr/src）
                          │
                          ▼
              HDFS /data/output/<job_id>
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
  data/mr_result/*.txt（本地留存）   集群控制台「写回 MySQL」
              │                       │
              └────────► MySQL complaint_analysis（10 张表）
                                      │
                                      ▼
                     backend/main.py → index.html 大屏（6 页面）
```

## 一、采集

脚本：[pipeline/collect_narratives.py](file:///d:/fqh/pipeline/collect_narratives.py)

| 项 | 说明 |
|---|---|
| 数据源 | CFPB FOIA Electronic Reading Room 的 narrative archive 页面（页面 HTML 需先存为 `work/archive.html`） |
| 范围 | 正则筛出地址中 Export 序号 5~21 的 zip，共 **17 份**（脚本内 `assert len(urls) == 17` 硬校验） |
| 下载 | 3 线程并发 + `curl -C -` 断点续传 + 5 次重试 |
| 完整性 | HEAD 取 Content-Length 比对字节数；`zipfile.testzip()` 校验 CRC |
| 溯源 | 产出 `download_manifest.json`：每份文件的 url / 字节数 / sha256 / zip 成员清单 |
| 运行环境 | Windows（调用 `curl.exe`），产物默认写到 `E:\选拔赛\data\narratives` |

> 任一份下载失败或 CRC 不符会记录进 `errors` 并以退出码 1 结束，不会静默产出残缺数据集。

## 二、预处理（探查 + 清洗）

脚本目录：`数据清洗源码/`（5 份，全部只读原始数据、另写新文件，绝不覆盖源文件）。默认输入 `E:\选拔赛\data\1`，输出 `E:\选拔赛\data\clean`，换机时改脚本顶部路径即可。

| 脚本 | 类型 | 输入 | 作用 |
|---|---|---|---|
| `explore.py` | 探查 | 17 份 `CCDB_Export_*` | 抽样 1 万行，校验表头是否匹配标准 CCDB，统计 narrative 空值数与占比，打印文本样例 |
| `explore_other.py` | 探查 | `complaints.csv`、`fcc_consumer_complaints.csv` | 抽样 1 万行，列出全部字段与逐列空值占比，自动识别疑似投诉文本字段 |
| `clean.py` | 清洗 | 17 份 `CCDB_Export_*` | 只清洗 `Consumer complaint narrative`：换行/制表符转空格、压缩连续空格、剔除不可见控制字符；csv 分块读取 |
| `clean_complaints.py` | 清洗 | `complaints.csv`（约 5.32G） | 无 narrative 列，仅结构化规整：字符串去首尾空格、空白串转缺失值；分块 10 万行 |
| `clean_fcc.py` | 清洗 | `fcc_consumer_complaints.csv`（约 683M） | 与上同一套安全清洗逻辑，`low_memory=False` 消除 DtypeWarning |

三条设计约束：

1. **探查与清洗分离**——探查脚本只读，产出分析报告用的结论；清洗脚本另存新文件
2. **数据集隔离**——CCDB 带文本、complaints 纯结构化、FCC 电信三套分开处理，不合并
3. **完整性校验**——每个清洗脚本都打印「原始行数 / 清洗后行数」，两者应相等，不等即为异常

本轮探查已确认的两个结论：`complaints.csv` 15 字段 **缺投诉文本列**，只能做结构化统计；FCC 是电信骚扰投诉，字段体系独立，不能与金融投诉合并计算。

## 三、本地数据文件

| 文件 | 位置 | 内容 |
|---|---|---|
| 17 份原始导出 | `未清洗前的源数据/CCDB/CCDB_Export_*.csv` | CFPB 投诉原始记录（含 narrative 原文），约 6.5GB |
| 结构化清洗集 | `data/complaints_clean.csv` / `.pkl` | CSV 供 MR 读取，pkl 为 category 优化版供后端懒加载 |
| 原文文本集 | `data/ccdb_text.pkl` | 17 份合并后的投诉叙述文本（约 200 万行量级） |
| 电信清洗集 | `data/fcc_consumer_complaints_clean.csv` / `.pkl` | FCC 工单清洗结果（Issue 字段为分类依据） |

`未清洗前的源数据/` 是输入端目录，记录了原始文件的落点与重跑方式（见该目录 README）。

pkl 优先、CSV 兜底：后端 `ensure_dataset()`（[main.py:611](file:///d:/fqh/backend/main.py#L611-L658)）先找 `data/` 下的同名 pkl，缺失时回退读同名 CSV；连 `ccdb_text.pkl` 也缺失时，才按 `RAW_DATA_ROOT/CCDB/` 逐份合并原始 CSV。

## 四、MapReduce 统计

源码与产物：`mr/src/*.java`（10 个）、`mr/jar包/*.jar`（10 个）

任务与入库目标（`backend/cluster_jobs.json`）：

| 任务 id | jar | 输入 | 输出表 |
|---|---|---|---|
| company_count | CompanyCount.jar | `/data/cfpb_struct/input/complaints_clean.csv` | `fin_company` |
| product_count | ProductCount.jar | 同上 | `fin_product` |
| state_count | state_count.jar | 同上 | `fin_state` |
| timely_response | TimelyResponseCount.jar | 同上 | `fin_timely_response` |
| product_timely | ProductTimelyCount.jar | 同上 | `fin_product_timely` |
| word_count | NarrativeWordCount.jar | `/data/cfpb_text/input/` | `fin_word_freq` |
| word_count2 | NarrativeWordCount2.jar | 同上 | `fin_word_freq`（备用口径，默认不入库） |
| fcc_state | FccStateCount.jar | `/data/fcc/input/fcc_consumer_complaints_clean.csv` | `fcc_state` |
| fcc_monthly | FccMonthlyCount.jar | 同上 | `fcc_monthly` |
| fcc_issue | FccIssueCount.jar | 同上 | `fcc_issue` |

运行方式：大屏「集群控制」页通过 SSH 驱动（`backend/cluster.py`），输出为 TSV 两列（维度值 + 计数），可直接写回 MySQL（`import_enabled` 控制是否允许入库）。

> 注意：Hadoop 3.5 下 jar 的 MANIFEST 已声明 Main-Class 时，`hadoop jar` 不能再显式传类名，否则类名会被当成业务参数（详见 `cluster_probe.build_jar_command`）。项目已按 MANIFEST 自动判定。

本地留存结果：`data/mr_result/`（13 个 txt，另有 `描述.txt` 记录「表 → 图表」一一对应关系）。

## 五、MySQL 与前端

数据库 `complaint_analysis` 共 10 张表，统计元数据集中定义在 [db_meta.py](file:///d:/fqh/backend/db_meta.py#L17-L28)（同时作为集群入库白名单）。

- 后端：`backend/main.py` 提供 6 个页面的接口，读取 MySQL + 明细 CSV/pkl
- 前端：`backend/index.html` 单文件 Vue3 大屏，6 个页面 tab
- 部署：`Dockerfile` / `docker-compose.yml`；启停与数据库导入导出见 `scripts/`

## 六、复现顺序

1. 采集：跑 `pipeline/collect_narratives.py`，得到 17 份 zip 与 manifest
2. 解压：zip 内 CSV 放入 `未清洗前的源数据/CCDB/`
3. 探查：`数据清洗源码/explore.py`、`explore_other.py`，确认字段与空值情况
4. 清洗：`数据清洗源码/clean.py`、`clean_complaints.py`、`clean_fcc.py`，核对输出行数
5. 上传：三个输入路径推到 HDFS（`/data/cfpb_struct/input/`、`/data/cfpb_text/input/`、`/data/fcc/input/`）
6. 统计：集群控制台跑 10 个任务，结果写回 MySQL
7. 入库（换机部署）：`scripts/export_db.bat|sh` 导出，`scripts/import_db.bat|sh` 导入
8. 启动：`scripts/start.bat|sh`，访问 `http://127.0.0.1:8000`

## 七、已知缺口

- **`ccdb_text.pkl` 的合成脚本未留存**：17 份清洗后 CSV 合并成单个 pkl 的步骤目前靠一次性脚本完成，仓库内没有对应文件；`complaints_clean` / `fcc_clean` 已有 `clean_complaints.py` / `clean_fcc.py` 可复现。如需完全重跑，补一个合并脚本即可。
- **训练脚本仅用于离线模型**：`backend/train_cfpb_text_model.py`、`train_model_compare.py` 生成 `cfpb_text_model.joblib` 与指标 json，不属于日常启动路径。
