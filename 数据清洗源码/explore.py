"""CCDB 17 个批次文件探查脚本（只读，不修改原始文件）。

用途：写报告的数据探查章节、提前发现「大量空文本」等问题。
默认目录 E:\\选拔赛\\data\\1，按部署环境自行修改。
"""
import os

import pandas as pd

# CFPB CCDB标准表头
standard_cols = [
    "Date received", "Product", "Sub-product", "Issue", "Sub-issue",
    "Consumer complaint narrative", "Company public response", "Company",
    "State", "ZIP code", "Tags", "Submitted via", "Date sent to company",
    "Company response to consumer", "Timely response?", "Complaint ID",
]

data_dir = r"E:\选拔赛\data\1"
# 增加后缀过滤
file_list = [
    f for f in os.listdir(data_dir)
    if f.startswith("CCDB_Export")
    and f.lower().endswith((".csv", ".xls", ".xlsx"))
]

print(f"一共找到 {len(file_list)} 个CCDB批次文件\n")
for fname in file_list:
    full_path = os.path.join(data_dir, fname)
    print("=" * 70)
    print(f"文件：{fname}")
    try:
        if fname.lower().endswith(".csv"):
            df = pd.read_csv(full_path, nrows=10000)
        else:
            df = pd.read_excel(full_path, nrows=10000)

        print(f"抽样字段数量：{len(df.columns)}")
        if list(df.columns) == standard_cols:
            print("✅ 表头匹配标准CCDB")
        else:
            print("❌ 表头不一致！")
            print("当前表头：", list(df.columns))

        # 判断字段是否存在，防止KeyError
        if "Consumer complaint narrative" in df.columns:
            total = len(df)
            null_nar = df["Consumer complaint narrative"].isna().sum()
            null_rate = null_nar / total if total > 0 else 0
            print("【抽样前10000行结果】")
            print(f"抽样行数：{total}")
            print(f"文本空值数量：{null_nar}")
            print(f"文本空值占比：{null_rate:.2%}")

            sample_series = df["Consumer complaint narrative"].dropna()
            if len(sample_series) > 0:
                sample = sample_series.iloc[0]
                print(f"文本样例：{str(sample)[:250]}")
            else:
                print("文本样例：抽样内全部为空")
        else:
            print("⚠️ 缺少 Consumer complaint narrative 字段")

    except Exception as e:
        print(f"读取异常：{e}")

print("=" * 70)
print("✅ CCDB批次探查结束（空值占比仅为抽样结果，不代表全文件）")
