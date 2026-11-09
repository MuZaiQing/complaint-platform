# -*- coding: utf-8 -*-
"""
离线预聚合：为 3D 地球面板准备「州 × 月」时序与「州下钻」明细。

输入（本地明细，pkl 优先，缺失时回落 CSV）：
    data/complaints_clean.pkl               CFPB 金融投诉全量
    data/fcc_consumer_complaints_clean.pkl  FCC 电信投诉
输出：
    backend/data/geo_detail.json

口径说明：
    月份轴取 CFPB 完整月份（剔除最后一个月 2026-11 的残缺数据，与驾驶舱趋势一致）；
    FCC 在同一轴对齐，缺失月份补 0。FCC 时序统一取「Date Created」（完整无缺失），
    个别缺失时回落到「Date of Issue」。
    州代码只保留 50 州 + DC（与前端 GLOBE_DROP 一致）；
    人口用 2020 年美国人口普查常住人口，供「人均投诉率」维度使用（每 10 万人）。
    state_total 按全量行统计（含无日期行），by_month_state 只含可解析月份的行。
"""
import json
import os
import time

import pandas as pd

DATA_ROOT = os.getenv("DATA_ROOT", r"D:\fqh\data")
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "data")
OUT_FILE = os.path.join(OUT_DIR, "geo_detail.json")

DROP_MONTH = "2026-11"
TOP_N_PRODUCT = 8
TOP_N_COMPANY = 8
TOP_N_ISSUE = 8

# 2020 年美国人口普查常住人口（50 州 + DC）
POPULATION = {
    "AL": 5024279, "AK": 733391, "AZ": 7151502, "AR": 3011524, "CA": 39538223,
    "CO": 5773714, "CT": 3605944, "DE": 989948, "DC": 689545, "FL": 21538187,
    "GA": 10711908, "HI": 1455271, "ID": 1839106, "IL": 12812508, "IN": 6785528,
    "IA": 3190369, "KS": 2937880, "KY": 4505836, "LA": 4657757, "ME": 1362359,
    "MD": 6177224, "MA": 7029917, "MI": 10077331, "MN": 5706494, "MS": 2961279,
    "MO": 6154913, "MT": 1084225, "NE": 1961504, "NV": 3104614, "NH": 1377529,
    "NJ": 9288994, "NM": 2117522, "NY": 20201249, "NC": 10439388, "ND": 779094,
    "OH": 11799448, "OK": 3959353, "OR": 4237256, "PA": 13002700, "RI": 1097379,
    "SC": 5118425, "SD": 886667, "TN": 6910840, "TX": 29145505, "UT": 3271616,
    "VT": 643077, "VA": 8631393, "WA": 7705281, "WV": 1794716, "WI": 5893718,
    "WY": 576851,
}


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
    """任意日期文本 → YYYY-MM（兼容 MM/DD/YYYY 与 YYYY-MM-DD）"""
    s = s.astype(str)
    d = pd.to_datetime(s, errors="coerce", format="mixed")
    return d.dt.strftime("%Y-%m")


def keep_us_states(df):
    code = df["State"].astype(str).str.strip().str.upper()
    return df.assign(_st=code)[code.isin(list(POPULATION.keys()))]


def state_aggregate(df, months, cat_col, top_n):
    """state_total（全量）+ by_month_state（可定月）+ 州内类别 TOP N"""
    total = df.groupby("_st", observed=True).size()
    state_total = {str(k): int(v) for k, v in total.items()}

    mi = {m: i for i, m in enumerate(months)}
    dated = df.assign(_mi=df["_month"].map(mi)).dropna(subset=["_mi"])
    dated["_mi"] = dated["_mi"].astype(int)

    by_month_state = {}
    for (code, idx), v in dated.groupby(["_st", "_mi"], observed=True).size().items():
        by_month_state.setdefault(str(code), [0] * len(months))[int(idx)] = int(v)

    cs = dated.groupby(["_st", cat_col], observed=True).size().reset_index(name="n")
    detail = {}
    for code, grp in cs.groupby("_st", observed=True):
        top = grp.nlargest(top_n, "n")
        detail[str(code)] = [[str(a), int(b)] for a, b in zip(top[cat_col], top["n"])]

    return {
        "by_month_state": by_month_state,
        "state_total": state_total,
        "detail": detail,
        "total": int(len(df)),
        "dated": int(len(dated)),
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # ---------- 金融 ----------
    fin = load_frame("complaints_clean.pkl", "complaints_clean.csv",
                     ["Date received", "State", "Product", "Company"])
    fin = keep_us_states(fin)
    fin_fm = month_of(fin["Date received"])
    fin = fin.assign(_month=fin_fm)
    months = sorted(m for m in fin["_month"].dropna().unique() if m != DROP_MONTH)
    print(f"[口径] 月份轴 {months[0]} → {months[-1]}，共 {len(months)} 个月")

    fin_agg = state_aggregate(fin, months, "Product", TOP_N_PRODUCT)

    comp = fin.groupby(["_st", "Company"], observed=True).size().reset_index(name="n")
    companies = {}
    for code, grp in comp.groupby("_st", observed=True):
        top = grp.nlargest(TOP_N_COMPANY, "n")
        companies[str(code)] = [[str(a), int(b)] for a, b in zip(top["Company"], top["n"])]
    fin_agg["companies"] = companies
    print(f"[金融] 州数 {len(fin_agg['state_total'])}，合计 {fin_agg['total']:,} 条"
          f"（可定月 {fin_agg['dated']:,}）")
    del fin, comp

    # ---------- 电信 ----------
    fcc = load_frame("fcc_consumer_complaints_clean.pkl", "fcc_consumer_complaints_clean.csv",
                     ["Date Created", "Date of Issue", "State", "Issue"])
    fcc = keep_us_states(fcc)
    fcc_m = month_of(fcc["Date Created"]).fillna(month_of(fcc["Date of Issue"]))
    fcc = fcc.assign(_month=fcc_m)
    fcc_agg = state_aggregate(fcc, months, "Issue", TOP_N_ISSUE)
    print(f"[电信] 州数 {len(fcc_agg['state_total'])}，合计 {fcc_agg['total']:,} 条"
          f"（可定月 {fcc_agg['dated']:,}）")
    del fcc

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "months": months,
        "population": POPULATION,
        "fin": fin_agg,
        "fcc": fcc_agg,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n[完成] {OUT_FILE}（{os.path.getsize(OUT_FILE) / 1024:.1f} KB）")


if __name__ == "__main__":
    main()
