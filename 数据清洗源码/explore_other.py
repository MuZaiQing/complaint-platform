"""额外两份大文件探查脚本（complaints.csv / fcc_consumer_complaints.csv，只读不改）」。

超大文件只抽样前 10000 行，防止内存溢出；输出字段名与各列空值统计。
探查结论：complaints.csv 缺投诉文本列，只能做结构化统计；fcc 字段体系独立，不可与金融投诉合并。
默认目录 E:\\选拔赛\\data\\1，按部署环境自行修改。
"""
import os

import pandas as pd

data_dir = r"E:\选拔赛\data\1"
check_files = [
    "complaints.csv",
    "fcc_consumer_complaints.csv"
]

for fname in check_files:
    print("=" * 70)
    print(f"正在探查：{fname}")
    fp = os.path.join(data_dir, fname)
    try:
        df = pd.read_csv(fp, nrows=10000)
        print(f"✅ 读取成功，抽样行数：{len(df)}")
        print(f"字段总数：{len(df.columns)}")
        print("【全部字段名列表】")
        for col in df.columns:
            print(f" - {col}")

        print("\n【各字段空值统计（仅抽样前10000行）】")
        null_info = df.isna().sum()
        for col, cnt in null_info.items():
            rate = cnt / len(df)
            print(f" - {col}：空 {cnt} 条，占比 {rate:.2%}")

        text_cols = [c for c in df.columns
                     if "narrative" in c.lower() or "complaint" in c.lower() or "text" in c.lower()]
        if text_cols:
            print(f"\n【疑似投诉相关字段】：{text_cols}")
            for tc in text_cols:
                sample_series = df[tc].dropna()
                if len(sample_series) > 0:
                    print(f"{tc} 样例：{str(sample_series.iloc[0])[:300]}")
                else:
                    print(f"{tc} 抽样内全部为空")
        else:
            print("\n⚠️ 没有找到名字带 narrative / complaint / text 的疑似投诉相关字段")

    except Exception as e:
        print(f"❌ 读取失败：{e}")

print("=" * 70)
print("✅ 附加文件探查结束（空值占比仅抽样结果）")
