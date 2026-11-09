# -*- coding: utf-8 -*-
"""
离线预聚合：为 3D 知识图谱准备「企业 / 产品 / 问题」月度时序。

输入：
    data/complaints_clean.pkl               CFPB 金融投诉全量（Date received / Product / Company）
    data/fcc_consumer_complaints_clean.pkl  FCC 电信投诉（Date Created / Date of Issue / Issue）
输出：
    backend/data/kg_detail.json

口径说明：
    月份轴与 geo_detail.json 完全一致（CFPB 完整月份，剔除 2026-11 残缺月）；
    企业按月计数保留投诉量 TOP 40（覆盖任意窗口下的头部企业，供环比预警）；
    金融产品、电信问题各保留 TOP 25，用于「窗口新增主题」与类别规模；
    只输出月度数组，窗口求和由前端完成，避免为每种时间窗重复落盘。
"""
import json
import os
import time

import pandas as pd

DATA_ROOT = os.getenv("DATA_ROOT", r"D:\fqh\data")
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "data")
OUT_FILE = os.path.join(OUT_DIR, "kg_detail.json")

DROP_MONTH = "2026-11"
TOP_N_COMPANY = 40
TOP_N_PRODUCT = 25
TOP_N_ISSUE = 25


def load_frame(pkl_name, csv_name, usecols):
    pkl = os.path.join(DATA_ROOT, pkl_name)
    t = time.time()
    if os.path.exists(pkl):
        print(f"[读取] {pkl_name} ...")
        df = pd.read_pickle(pkl)
    else:
        print(f"[读取] {csv_name}（未找到 pkl，回落 CSV）...")
        df = pd.read_csv(os.path.join(DATA_ROOT, csv_name), usecols=usecols, low_memory=False)
    print(f"  → {len(df):,} 行，{time.time() - t:.1f}s")
    return df


def month_of(s):
    d = pd.to_datetime(s.astype(str), errors="coerce", format="mixed")
    return d.dt.strftime("%Y-%m")


def month_series(subset, months, name_col):
    """按 name_col × 月份计数，返回 {name: [每月条数]}"""
    mi = {m: i for i, m in enumerate(months)}
    d = subset.assign(_mi=subset["_month"].map(mi)).dropna(subset=["_mi"])
    d["_mi"] = d["_mi"].astype(int)
    out = {}
    for (name, i), v in d.groupby([name_col, "_mi"], observed=True).size().items():
        out.setdefault(str(name), [0] * len(months))[int(i)] = int(v)
    return out


def top_names(df, col, n):
    return [str(k) for k in df.groupby(col, observed=True).size().nlargest(n).index]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # ---------- 金融：企业 + 产品 ----------
    fin = load_frame("complaints_clean.pkl", "complaints_clean.csv", ["Date received", "Product", "Company"])
    fin = fin.assign(_month=month_of(fin["Date received"]))
    months = sorted(m for m in fin["_month"].dropna().unique() if m != DROP_MONTH)
    print(f"[口径] 月份轴 {months[0]} → {months[-1]}，共 {len(months)} 个月")

    comp_names = top_names(fin, "Company", TOP_N_COMPANY)
    company_month = month_series(fin[fin["Company"].isin(comp_names)], months, "Company")
    print(f"[金融] 企业月序列 {len(company_month)} 家")

    prod_names = top_names(fin, "Product", TOP_N_PRODUCT)
    product_month = month_series(fin[fin["Product"].isin(prod_names)], months, "Product")
    print(f"[金融] 产品月序列 {len(product_month)} 类")
    del fin

    # ---------- 电信：问题类型 ----------
    fcc = load_frame("fcc_consumer_complaints_clean.pkl", "fcc_consumer_complaints_clean.csv",
                     ["Date Created", "Date of Issue", "Issue"])
    fcc_m = month_of(fcc["Date Created"]).fillna(month_of(fcc["Date of Issue"]))
    fcc = fcc.assign(_month=fcc_m)
    issue_names = top_names(fcc, "Issue", TOP_N_ISSUE)
    issue_month = month_series(fcc[fcc["Issue"].isin(issue_names)], months, "Issue")
    print(f"[电信] 问题月序列 {len(issue_month)} 类")
    del fcc

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "months": months,
        "fin": {"company_month": company_month, "product_month": product_month},
        "fcc": {"issue_month": issue_month},
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n[完成] {OUT_FILE}（{os.path.getsize(OUT_FILE) / 1024:.1f} KB）")


if __name__ == "__main__":
    main()
