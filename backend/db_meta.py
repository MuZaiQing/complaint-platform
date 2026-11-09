"""
共享数据库元数据：供 main.py（大屏接口）与 cluster.py（集群控制）共用，
避免两者互相 import 造成循环依赖。
"""
import os
import threading
import time

# 部署时全部走环境变量，本地默认值保持开箱即用
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "Fqh112233!"),
    "db": os.getenv("DB_NAME", "complaint_analysis"),
    "charset": "utf8mb4",
}

STATS_TABLES = {
    "fin_monthly":        {"label": "金融月度投诉",       "cols": ["stat_month", "complaint_count"], "sort_col": "stat_month"},
    "fin_product":        {"label": "金融产品投诉",       "cols": ["product_name", "complaint_count"], "sort_col": "complaint_count desc"},
    "fin_state":          {"label": "金融州级投诉",       "cols": ["state_code", "complaint_count"], "sort_col": "complaint_count desc"},
    "fin_timely_response":{"label": "金融及时回复",        "cols": ["response_flag", "complaint_count"]},
    "fin_company":        {"label": "金融企业投诉",       "cols": ["company_name", "complaint_count"], "sort_col": "complaint_count desc"},
    "fin_product_timely": {"label": "金融分产品及时回复", "cols": ["stat_key", "complaint_count"]},
    "fin_word_freq":      {"label": "高频词",             "cols": ["word", "freq"], "sort_col": "freq desc"},
    "fcc_monthly":        {"label": "电信月度投诉",       "cols": ["stat_month", "complaint_count"], "sort_col": "stat_month"},
    "fcc_issue":          {"label": "电信投诉类型",       "cols": ["issue_name", "complaint_count"], "sort_col": "complaint_count desc"},
    "fcc_state":          {"label": "电信州级投诉",       "cols": ["state_code", "complaint_count"], "sort_col": "complaint_count desc"},
}

# ====================== 预聚合表结果缓存 ======================
# 10 张统计表都是 MapReduce 离线产物，短时间内不会变化；按表缓存可把
# 首页 14 次重复查询 + 反复建连压成 1 次（首屏接口从 ~250ms 降到 ~5ms）。
TABLE_CACHE_TTL = float(os.getenv("TABLE_CACHE_TTL", "60"))
_TABLE_CACHE = {}
_TABLE_CACHE_LOCK = threading.Lock()


def cache_get(key):
    """命中返回浅拷贝（防止调用方 sort/reverse 污染缓存），未命中返回 None"""
    with _TABLE_CACHE_LOCK:
        hit = _TABLE_CACHE.get(key)
    if hit and time.time() - hit[0] < TABLE_CACHE_TTL:
        return list(hit[1])
    return None


def cache_put(key, rows):
    with _TABLE_CACHE_LOCK:
        _TABLE_CACHE[key] = (time.time(), rows)


def clear_table_cache():
    """集群导入任务完成后调用，保证大屏立刻看到新数据"""
    with _TABLE_CACHE_LOCK:
        _TABLE_CACHE.clear()
