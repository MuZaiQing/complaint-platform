# -*- coding: utf-8 -*-
# 模型消融对比脚本（答辩用）：同一份抽样数据、同一 8:2 分层切分下对比三组模型
#   1) 词袋(1-gram) + 朴素贝叶斯
#   2) TF-IDF(1-2gram) + 朴素贝叶斯
#   3) TF-IDF(1-2gram) + 逻辑回归（当前线上模型）
# 产出 cfpb_model_compare.json，供前端「模型选型对比」柱状图读取
import os, json, time
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

from train_cfpb_text_model import stream_sample, TOP_N, RANDOM_STATE

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def evaluate(name, vec, clf, Xtr, Xte, ytr, yte):
    """训练单个模型并返回测试集宏平均指标"""
    pipe = Pipeline([("vec", vec), ("clf", clf)])
    t0 = time.time()
    pipe.fit(Xtr, ytr)
    pred = pipe.predict(Xte)
    acc = accuracy_score(yte, pred)
    p, r, f1, _ = precision_recall_fscore_support(yte, pred, average="macro", zero_division=0)
    cost = round(time.time() - t0, 1)
    print(f"  {name}: acc={acc:.4f} f1={f1:.4f} 训练 {cost}s", flush=True)
    return {"name": name, "accuracy": round(float(acc), 4), "f1": round(float(f1), 4),
            "precision": round(float(p), 4), "recall": round(float(r), 4), "train_seconds": cost}


def main():
    df = stream_sample()
    dist = df["label"].value_counts()
    top = dist.head(TOP_N).index
    df = df[df["label"].isin(top)].reset_index(drop=True)
    Xtr, Xte, ytr, yte = train_test_split(
        df["text"], df["label"], test_size=0.2, stratify=df["label"], random_state=RANDOM_STATE)
    print(f"[对比] 样本 {len(df)}，训练 {len(Xtr)} / 测试 {len(Xte)}", flush=True)

    tfidf = lambda: TfidfVectorizer(max_features=50000, ngram_range=(1, 2),
                                    min_df=5, sublinear_tf=True, stop_words="english")
    models = [
        evaluate("词袋 + 朴素贝叶斯", CountVectorizer(max_features=50000, ngram_range=(1, 1),
                                                      min_df=5, stop_words="english"),
                 MultinomialNB(), Xtr, Xte, ytr, yte),
        evaluate("TF-IDF + 朴素贝叶斯", tfidf(), MultinomialNB(), Xtr, Xte, ytr, yte),
        evaluate("TF-IDF + 逻辑回归（当前）", tfidf(),
                 LogisticRegression(max_iter=1000, class_weight="balanced", n_jobs=-1),
                 Xtr, Xte, ytr, yte),
    ]
    payload = {
        "models": models,
        "sample_count": int(len(df)),
        "note": "同一抽样数据、同一 8:2 分层切分下的测试集宏平均指标，用于模型选型对照",
    }
    with open(os.path.join(OUT_DIR, "cfpb_model_compare.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("[完成] 已写入 cfpb_model_compare.json", flush=True)


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"总耗时 {time.time()-t0:.0f}s", flush=True)
