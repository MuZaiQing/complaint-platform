# -*- coding: utf-8 -*-
# CFPB 投诉文本分类模型训练脚本
# 数据：D:\fqh\未清洗前的源数据\CCDB 下 17 份 CCDB Export 原始 CSV
#   特征 X = Consumer complaint narrative（投诉原文），标签 y = Product（CFPB 官方产品分类）
# 流程：逐文件分块流式读取 → per-class 蓄水池抽样(每类≤2万，内存恒定) → TF-IDF(1~2gram, 5万特征)
#       + LogisticRegression(class_weight=balanced) → 8:2 分层评估
# 产出：cfpb_text_model.joblib（推理管道+类别表）、cfpb_text_metrics.json（真实评估指标，供后端读取）
import os, json, glob, time
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

DATA_DIR = r'D:\fqh\未清洗前的源数据\CCDB'
OUT_DIR  = os.path.dirname(os.path.abspath(__file__))
TOP_N        = 9        # 样本量 TOP9 的 Product 类（与前端人工校正下拉框一致）
PER_CLASS    = 20000    # 每类蓄水池抽样上限
MIN_TEXT_LEN = 30       # 过滤过短/无意义原文
RANDOM_STATE = 42


def stream_sample():
    """stdlib csv 逐行流式读取（C 加速、行级缓冲，内存恒定），对 narrative 非空行做 per-class 蓄水池抽样"""
    import csv
    csv.field_size_limit(10 * 1024 * 1024)  # 单条原文可能很长
    rng = np.random.default_rng(RANDOM_STATE)
    pools, seen = {}, {}                    # label -> 样本池 list / 全局已见计数
    files = sorted(glob.glob(os.path.join(DATA_DIR, 'CCDB_Export_*.csv')))
    print(f'[1/4] 流式抽样：{len(files)} 个 CSV，每类上限 {PER_CLASS}', flush=True)
    t0 = time.time()
    for fp in files:
        with open(fp, newline='', encoding='utf-8', errors='replace') as f:
            rd = csv.reader(f)
            header = next(rd, None) or []
            if 'Product' not in header or 'Consumer complaint narrative' not in header:
                print(f'  跳过（缺列）：{os.path.basename(fp)}', flush=True)
                continue
            i_lab, i_txt = header.index('Product'), header.index('Consumer complaint narrative')
            for row in rd:
                if len(row) <= max(i_lab, i_txt):
                    continue
                lab, txt = row[i_lab], row[i_txt]
                if len(txt) <= MIN_TEXT_LEN:
                    continue
                n0 = seen.get(lab, 0) + 1
                seen[lab] = n0
                pool = pools.setdefault(lab, [])
                if len(pool) < PER_CLASS:               # 蓄水池未满：直接填充
                    pool.append(txt)
                else:                                   # 已满：按 PER_CLASS/n0 概率替换
                    j = rng.integers(0, n0)
                    if j < PER_CLASS:
                        pool[j] = txt
        print(f'  {os.path.basename(fp)} 完成，累计 {time.time()-t0:.0f}s，类别数 {len(pools)}', flush=True)
    rows = [(lab, txt) for lab, pool in pools.items() for txt in pool]
    df = pd.DataFrame(rows, columns=['label', 'text'])
    print(f'  抽样完成：{len(df)} 条 / {len(pools)} 类', flush=True)
    return df


def train(df):
    dist = df['label'].value_counts()
    print('[2/4] 抽样类别分布:', flush=True)
    print(dist.to_string(), flush=True)
    top = dist.head(TOP_N).index
    df = df[df['label'].isin(top)].reset_index(drop=True)
    Xtr, Xte, ytr, yte = train_test_split(
        df['text'], df['label'], test_size=0.2, stratify=df['label'], random_state=RANDOM_STATE)
    pipe = Pipeline([
        ('tfidf', TfidfVectorizer(max_features=50000, ngram_range=(1, 2),
                                  min_df=5, sublinear_tf=True, stop_words='english')),
        ('clf', LogisticRegression(max_iter=1000, class_weight='balanced', n_jobs=-1)),
    ])
    print(f'[3/4] 训练：train={len(Xtr)} test={len(Xte)} ...', flush=True)
    t0 = time.time()
    pipe.fit(Xtr, ytr)
    print(f'  fit 完成，耗时 {time.time()-t0:.0f}s', flush=True)
    pred = pipe.predict(Xte)
    acc = accuracy_score(yte, pred)
    p, r, f1, _ = precision_recall_fscore_support(yte, pred, average='macro', zero_division=0)
    labels = sorted(df['label'].unique().tolist())
    joblib.dump({'pipeline': pipe, 'labels': labels},
                os.path.join(OUT_DIR, 'cfpb_text_model.joblib'))
    metrics = {
        'accuracy': round(float(acc), 4), 'precision': round(float(p), 4),
        'recall': round(float(r), 4), 'f1': round(float(f1), 4),
        'sample_count': int(len(df)), 'classes': labels,
        'features': 'TF-IDF(1-2gram) · 50,000 维',
        'note': f'真实训练：CCDB 17 份 Export 流式抽样(每类≤{PER_CLASS})，'
                f'TF-IDF(5万特征,1-2gram)+LogisticRegression(balanced)，指标为测试集宏平均',
    }
    with open(os.path.join(OUT_DIR, 'cfpb_text_metrics.json'), 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print('[4/4] 测试集指标:', json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    t_all = time.time()
    df = stream_sample()
    train(df)
    print(f'全部完成，总耗时 {time.time()-t_all:.0f}s', flush=True)
