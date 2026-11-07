# 未清洗前的源数据

本目录对应预处理流程的**输入端**：采集下来、尚未清洗的原始文件。

## 当前项目实际落点

| 原始数据 | 实际位置 | 说明 |
|---|---|---|
| CFPB 17 份 CCDB 原始导出 | `data/CCDB/CCDB_Export_*.csv` | 约 6.9GB，未清洗 |
| CFPB 结构化大表 `complaints.csv` | 未随项目保存 | 约 5.32GB，清洗产物为 `data/complaints_clean.csv` |
| FCC 电信原始工单 | 未随项目保存 | 约 683MB，清洗产物为 `data/fcc_consumer_complaints_clean.csv` |

大文件（>500MB）统一放在 `data/` 下并由 `.gitignore` 排除，不进版本库，因此不在本目录重复存放。

## 使用方式

`../数据清洗源码/` 下的脚本默认读取 `E:\选拔赛\data\1`，输出到 `E:\选拔赛\data\clean`。
在新机器重跑预处理时，把原始文件放进同一个输入目录，或修改脚本顶部的 `data_dir` / `out_dir` 即可：

- `explore.py`、`clean.py` → 读 `CCDB_Export_*`（17 份）
- `explore_other.py`、`clean_complaints.py` → 读 `complaints.csv`
- `explore_other.py`、`clean_fcc.py` → 读 `fcc_consumer_complaints.csv`

清洗产物落到 `data/` 对应文件后，即可按 [docs/data-pipeline.md](file:///d:/fqh/docs/data-pipeline.md) 上传 HDFS 并运行 MapReduce。
