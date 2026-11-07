"""fcc_consumer_complaints.csv（约 683M）清洗脚本，与 complaints 同一套安全清洗逻辑。

电信骚扰投诉数据独立处理：加 low_memory=False 消除 DtypeWarning；
字符串去首尾空格、空白串转缺失值；无长文本字段，仅结构化清洗。
默认目录 E:\\选拔赛\\data\\1，输出 E:\\选拔赛\\data\\clean，按部署环境自行修改。
"""
import os

import pandas as pd

data_dir = r"E:\选拔赛\data\1"
out_dir = r"E:\选拔赛\data\clean"
os.makedirs(out_dir, exist_ok=True)

source_path = os.path.join(data_dir, "fcc_consumer_complaints.csv")
save_path = os.path.join(out_dir, "fcc_consumer_complaints_clean.csv")

chunk_iter = pd.read_csv(source_path, chunksize=50000, low_memory=False)
first_chunk = True
total_origin = 0
total_clean = 0

for chunk in chunk_iter:
    chunk_len = len(chunk)
    total_origin += chunk_len
    for col in chunk.columns:
        if chunk[col].dtype == "object":
            chunk[col] = chunk[col].apply(
                lambda x: x.strip() if isinstance(x, str) else x
            )
            chunk[col] = chunk[col].replace(r'^\s*$', pd.NA, regex=True)
    total_clean += len(chunk)
    chunk.to_csv(save_path, mode='w' if first_chunk else 'a', header=first_chunk, index=False)
    first_chunk = False
    print("写入一块完成")

print(f"\nfcc_consumer_complaints.csv 原始总行数：{total_origin}，清洗后总行数：{total_clean}")
print(f"✅ fcc文件清洗完成，输出：{save_path}")
