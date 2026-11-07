"""17 个 CCDB 批次清洗脚本（原始文件只读，清洗结果另存 clean 文件夹）。

核心：只清洗 Consumer complaint narrative 投诉文本——换行/制表符转空格、连续空格压缩、
剔除不可见控制字符，空值保留。csv 分块读取防内存溢出，xls 因 pandas 限制需全量读取。
输出统一 .csv（Hadoop 生态最友好），并打印原始/清洗后行数做完整性校验。
默认目录 E:\\选拔赛\\data\\1，输出 E:\\选拔赛\\data\\clean，按部署环境自行修改。
"""
import os
import re

import pandas as pd


def clean_narrative_raw(text):
    if pd.isna(text):
        return None
    text = str(text)
    # 换行、制表符替换为空格
    text = re.sub(r'[\r\n\t]+', ' ', text)
    # 只删除不可见控制字符，保留正常文字、标点、重音字符
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    # 连续空格合并
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


data_dir = r"E:\选拔赛\data\1"
out_dir = r"E:\选拔赛\data\clean"
os.makedirs(out_dir, exist_ok=True)

file_list = [
    f for f in os.listdir(data_dir)
    if f.startswith("CCDB_Export")
    and f.lower().endswith((".csv", ".xls", ".xlsx"))
]

for fname in file_list:
    print(f"\n正在处理：{fname}")
    source_path = os.path.join(data_dir, fname)
    base_name = os.path.splitext(fname)[0]
    save_path = os.path.join(out_dir, base_name + ".csv")
    total_origin = 0
    total_clean = 0
    try:
        if fname.lower().endswith(".csv"):
            reader = pd.read_csv(source_path, chunksize=10000)
            first = True
            for chunk in reader:
                chunk_len = len(chunk)
                total_origin += chunk_len
                if "Consumer complaint narrative" in chunk.columns:
                    chunk["Consumer complaint narrative"] = chunk["Consumer complaint narrative"].apply(clean_narrative_raw)
                total_clean += len(chunk)
                chunk.to_csv(save_path, mode='w' if first else 'a', header=first, index=False)
                first = False
            print(f"{fname} 原始行数：{total_origin}，清洗后行数：{total_clean}")
            print(f"{fname} 清洗完成，输出：{base_name}.csv")
        else:
            df_all = pd.read_excel(source_path)
            total_origin = len(df_all)
            if "Consumer complaint narrative" in df_all.columns:
                df_all["Consumer complaint narrative"] = df_all["Consumer complaint narrative"].apply(clean_narrative_raw)
            total_clean = len(df_all)
            df_all.to_csv(save_path, index=False)
            print(f"{fname} 原始行数：{total_origin}，清洗后行数：{total_clean}")
            print(f"{fname} 清洗完成，输出：{base_name}.csv")
    except Exception as e:
        print(f"❌ 失败 {fname}：{e}")

print("\n✅ CCDB全部清洗完成！文件输出目录：E:\\选拔赛\\data\\clean")
