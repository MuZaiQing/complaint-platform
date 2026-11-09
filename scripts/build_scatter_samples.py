# -*- coding: utf-8 -*-
"""
离线预聚合：为 Scatter3D 生成「单条投诉文本」三维投影样本。

做法：
    1) 抽样：CFPB 从 CCDB 原始 CSV 流式读取投诉原文（只取必要列，不加载 2GB pkl）；
       FCC 读取清洗后 pkl，用 Issue / 通话类型 / Form 拼成短文本。
    2) 文本向量化：TF-IDF → TruncatedSVD 降到 3 维（真实投影，非随机）。
    3) 逐轴分位裁剪缩放到 [-1.3, 1.3]，与词散点的 2.8 边长坐标框对齐。
    4) KMeans(4) 计算到质心距离，最远 5% 标记为离群点（= 难分类样本）。

输出：
    backend/data/scatter_samples.json
"""
import glob
import json
import os
import re
import time

import numpy as np
import pandas as pd

DATA_ROOT = os.getenv("DATA_ROOT", r"D:\fqh\data")
RAW_DATA_ROOT = os.getenv("RAW_DATA_ROOT", r"D:\fqh\未清洗前的源数据")
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "data")
OUT_FILE = os.path.join(OUT_DIR, "scatter_samples.json")

N_SAMPLES = 2000
K_CLUSTER = 4
TEXT_COL_CACHE = 200      # 前端展示用文本截断
TOK_N = 14                # 前端框选匹配用代表词数量
BOX = 1.3                 # 坐标半边长（与散点场景 2.8 边长一致）

STOP = set("""
a an the and or but if as at by for from in into of on to with is are was were be been
being have has had do does did this that these those it its i me my we our you your he she they
them his her not no so than then too very can could would should will may might must about
""".split())

TOKEN_RE = re.compile(r"[a-z][a-z']{2,}")


def tokenize(text):
    return [w for w in TOKEN_RE.findall(text.lower()) if w not in STOP]


def truncate(text, n=TEXT_COL_CACHE):
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text[:n]


# ---------------- CFPB：流式抽样原文 ----------------
def sample_cfpb():
    files = sorted(glob.glob(os.path.join(RAW_DATA_ROOT, "CCDB", "CCDB_Export_*.csv")))
    if not files:
        raise SystemExit(f"未找到 CCDB 原始 CSV：{RAW_DATA_ROOT}\\CCDB")
    cols = ["Complaint ID", "Product", "State", "Company", "Consumer complaint narrative"]
    chunks = []
    t0 = time.time()
    for fi, path in enumerate(files, 1):
        print(f"[CFPB] {fi}/{len(files)} {os.path.basename(path)}")
        for ch in pd.read_csv(path, usecols=cols, chunksize=200000, low_memory=False):
            txt = ch["Consumer complaint narrative"].astype("string").fillna("")
            mask = txt.str.len() >= 60
            if not mask.any():
                continue
            sub = ch.loc[mask, ["Complaint ID", "Product", "State", "Company"]].copy()
            sub["text"] = txt[mask].str.slice(0, 800)
            chunks.append(sub.sample(min(len(sub), 400), random_state=1000 + fi))
    df = pd.concat(chunks, ignore_index=True)
    df = df.sample(min(len(df), N_SAMPLES), random_state=42).reset_index(drop=True)
    print(f"  → 流式抽样完成 {len(df):,} 条，用时 {time.time() - t0:.1f}s")
    return pd.DataFrame({
        "id": df["Complaint ID"].astype(str),
        "cat": df["Product"].astype(str),
        "st": df["State"].astype(str),
        "text": df["text"].astype(str),
    })


# ---------------- FCC：结构化字段拼短文本 ----------------
def sample_fcc():
    pkl = os.path.join(DATA_ROOT, "fcc_consumer_complaints_clean.pkl")
    print(f"[FCC] 读取 {os.path.basename(pkl)} ...")
    df = pd.read_pickle(pkl)
    parts = []
    for col in ["Issue", "Type of Call or Msge", "Form", "Type of Property Goods or Services"]:
        if col in df.columns:
            parts.append(df[col].astype("string").fillna(""))
    text = parts[0]
    for p in parts[1:]:
        text = text + " | " + p
    df = df.assign(_text=text)
    mask = df["_text"].str.len() >= 8
    df = df.loc[mask].sample(min(int(mask.sum()), N_SAMPLES), random_state=42)
    print(f"  → 抽样 {len(df):,} 条")
    return pd.DataFrame({
        "id": df["Ticket ID"].astype(str),
        "cat": df["Issue"].astype(str),
        "st": df["State"].astype(str),
        "text": df["_text"].astype(str),
    })


# ---------------- TF-IDF + SVD → 3D ----------------
def project(df):
    from sklearn.cluster import KMeans
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(max_features=20000, min_df=2, max_df=0.7, sublinear_tf=True,
                          token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z']{2,}\b", stop_words="english")
    X = vec.fit_transform(df["text"])
    svd = TruncatedSVD(n_components=3, random_state=42)
    Z = svd.fit_transform(X).astype(np.float64)
    print(f"  词表 {X.shape[1]:,} · 解释方差 {np.round(svd.explained_variance_ratio_, 3).tolist()}")

    # 逐轴 2%~98% 分位裁剪 → [-BOX, BOX]
    for j in range(3):
        col = Z[:, j]
        lo, hi = np.percentile(col, [2, 98])
        if hi <= lo:
            hi = lo + 1e-6
        Z[:, j] = (np.clip((col - lo) / (hi - lo), 0, 1) * 2 - 1) * BOX

    k = min(K_CLUSTER, len(df))
    km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(Z)
    dist = np.linalg.norm(Z - km.cluster_centers_[km.labels_], axis=1)
    outlier = dist >= np.percentile(dist, 95)

    # 每条文本的代表词（TF-IDF 权重最高的前 TOK_N 个），供前端框选时按词匹配
    names = np.array(vec.get_feature_names_out())
    toks = []
    for i in range(X.shape[0]):
        row = X.getrow(i)
        idx = row.indices[np.argsort(row.data)[::-1][:TOK_N]]
        toks.append(" ".join(names[idx].tolist()))

    out = []
    for i in range(len(df)):
        out.append({
            "id": df["id"].iloc[i],
            "cat": truncate(df["cat"].iloc[i], 40),
            "st": df["st"].iloc[i] if df["st"].iloc[i] not in ("nan", "") else "",
            "t": truncate(df["text"].iloc[i]),
            "tok": toks[i],
            "x": round(float(Z[i, 0]), 3),
            "y": round(float(Z[i, 1]), 3),
            "z": round(float(Z[i, 2]), 3),
            "o": 1 if bool(outlier[i]) else 0,
        })
    return out, [round(float(v), 3) for v in svd.explained_variance_ratio_]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    payload = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "k": K_CLUSTER}

    cfpb_df = sample_cfpb()
    cfpb_samples, evr = project(cfpb_df)
    payload["cfpb"] = {"label": "CFPB 投诉原文", "total": len(cfpb_samples),
                       "evr": evr, "samples": cfpb_samples}
    print(f"[CFPB] 投影样本 {len(cfpb_samples)}，离群 {sum(s['o'] for s in cfpb_samples)}")

    fcc_df = sample_fcc()
    fcc_samples, evr2 = project(fcc_df)
    payload["fcc"] = {"label": "FCC 工单字段", "total": len(fcc_samples),
                      "evr": evr2, "samples": fcc_samples}
    print(f"[FCC] 投影样本 {len(fcc_samples)}，离群 {sum(s['o'] for s in fcc_samples)}")

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[输出] {OUT_FILE}  {os.path.getsize(OUT_FILE) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
