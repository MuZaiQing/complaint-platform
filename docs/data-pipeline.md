# 数据链路说明

本项目有两条独立业务线（金融 CFPB、电信 FCC），数据从公开源采集后，经本地清洗、Hadoop MapReduce 统计，最终落 MySQL 供大屏读取。

## 总览

```
CFPB 官网 archive.html
        │  pipeline/collect_narratives.py（curl 并发下载 + CRC 校验 + sha256 清单）
        ▼
17 份 Export zip → 解压 CSV                     FCC 公开投诉数据
        │                                              │
        ▼                                              ▼
data/CCDB/（17 份 CCDB_Export_*.csv）      data/fcc_consumer_complaints_clean.csv
        │                                              │
        ├──→ data/complaints_clean.csv/.pkl（结构化字段）│
        └──→ data/ccdb_text.pkl（投诉原文合并）         │
                    │                                   │
                    ▼                                   ▼
        HDFS /data/cfpb_struct/input/          HDFS /data/fcc/input/
        HDFS /data/cfpb_text/input/                     │
                    │                                   │
                    └────────► 10 个 MapReduce 任务 ◄────┘
                              （mr/jar包 + mr/src）
                                     │
                                     ▼
                     HDFS /data/output/<job_id>
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
        data/mr_result/*.txt（本地留存）      集群控制台「写回 MySQL」
                     │                               │
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

> 特点：任一份下载失败或 CRC 不符会记录进 `errors` 并以退出码 1 结束，不会静默产出残缺数据集。

## 二、本地数据文件

| 文件 | 位置 | 内容 |
|---|---|---|
| 17 份原始导出 | `data/CCDB/CCDB_Export_*.csv` | CFPB 投诉原始记录（含 narrative 原文） |
| 结构化清洗集 | `data/complaints_clean.csv` / `.pkl` | CSV 供 MR 读取，pkl 为 category 优化版供后端懒加载 |
| 原文文本集 | `data/ccdb_text.pkl` | 17 份合并后的投诉叙述文本（约 200 万行量级） |
| 电信清洗集 | `data/fcc_consumer_complaints_clean.csv` / `.pkl` | FCC 工单清洗结果（Issue 字段为分类依据） |

pkl 优先、CSV 兜底：后端 `ensure_dataset()`（[main.py:611](file:///d:/fqh/backend/main.py#L611-L658)）先找同名 pkl，缺失时回退读 CSV 或逐份拼 `CCDB/`。

## 三、MapReduce 统计

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

## 四、MySQL 与前端

数据库 `complaint_analysis` 共 10 张表，采购/统计元数据集中定义在 [db_meta.py](file:///d:/fqh/backend/db_meta.py#L17-L28)（同时作为集群入库白名单）。

- 后端：`backend/main.py` 提供 6 个页面的接口，读取 MySQL + 明细 CSV/pkl
- 前端：`backend/index.html` 单文件 Vue3 大屏，6 个页面 tab
- 部署：`Dockerfile` / `docker-compose.yml`；启停与数据库导入导出见 `scripts/`

## 五、复现顺序

1. 采集：跑 `pipeline/collect_narratives.py`，得到 17 份 zip 与 manifest
2. 解压：zip 内 CSV 放入 `data/CCDB/`
3. 清洗：生成 `complaints_clean.csv`、`ccdb_text.pkl`、`fcc_consumer_complaints_clean.csv`
4. 上传：三个输入路径推到 HDFS（`/data/cfpb_struct/input/`、`/data/cfpb_text/input/`、`/data/fcc/input/`）
5. 统计：集群控制台跑 10 个任务，结果写回 MySQL
6. 入库（换机部署）：`scripts/export_db.bat|sh` 导出，`scripts/import_db.bat|sh` 导入
7. 启动：`scripts/start.bat|sh`，访问 `http://127.0.0.1:8000`

## 六、已知缺口

- **清洗脚本未随项目留存**：第 3 步生成 `complaints_clean` / `ccdb_text` / `fcc_clean` 的脚本不在本仓库，历史产物已固化在 `data/`；如需重新从原始 CSV 生成，需要补写清洗脚本。
- **训练脚本仅用于离线模型**：`backend/train_cfpb_text_model.py`、`train_model_compare.py` 生成 `cfpb_text_model.joblib` 与指标 json，不属于日常启动路径。
