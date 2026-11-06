"""
共享数据库元数据：供 main.py（大屏接口）与 cluster.py（集群控制）共用，
避免两者互相 import 造成循环依赖。
"""
import os

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
