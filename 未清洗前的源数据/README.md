# 未清洗前的源数据

本目录对应预处理流程的**输入端**：采集下来、尚未清洗的原始文件。

## 内容

| 原始数据 | 位置 | 体积 |
|---|---|---|
| CFPB 17 份 CCDB 原始导出 | `CCDB/CCDB_Export_*.csv`（本目录内） | 约 6.5GB，17 个文件 |
| CFPB 结构化大表 `complaints.csv` | 未随项目保存 | 约 5.32GB，清洗产物为 `data/complaints_clean.csv` |
| FCC 电信原始工单 | 未随项目保存 | 约 683MB，清洗产物为 `data/fcc_consumer_complaints_clean.csv` |

`CCDB/` 已由 `.gitignore` 排除（`.gitignore` 中的 `未清洗前的源数据/CCDB/`），不进版本库；本 README 会正常提交。

## 运行时用途

后端只在 `data/ccdb_text.pkl` **缺失**时才回退读取本目录的 17 份原始 CSV（见 [main.py:639](file:///d:/fqh/backend/main.py#L639-L644)），路径由环境变量 `RAW_DATA_ROOT` 指定：

- 本机默认 `D:\fqh\未清洗前的源数据`
- Docker 内为 `/raw`（compose 挂载 `./未清洗前的源数据:/raw:ro`）

日常运行读的是 `data/ccdb_text.pkl`，不会触碰这个目录。

## 重跑预处理

`../数据清洗源码/` 下脚本默认读取 `E:\选拔赛\data\1`，输出 `E:\选拔赛\data\clean`。在新机器重跑时，把原始文件放到该输入目录，或修改脚本顶部 `data_dir` / `out_dir`：

- `explore.py`、`clean.py` → 读 `CCDB_Export_*`（17 份）
- `explore_other.py`、`clean_complaints.py` → 读 `complaints.csv`
- `explore_other.py`、`clean_fcc.py` → 读 `fcc_consumer_complaints.csv`

清洗产物落到 `data/` 对应文件后，即可按 [docs/data-pipeline.md](file:///d:/fqh/docs/data-pipeline.md) 上传 HDFS 并运行 MapReduce。
