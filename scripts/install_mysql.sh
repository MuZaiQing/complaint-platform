#!/usr/bin/env bash
# 投诉分析平台 - 裸机安装 MySQL 8（Linux）
#
# 用法:
#   sudo bash scripts/install_mysql.sh [--password 密码] [--db 库名]
#   sudo DBPASS='xxx' bash scripts/install_mysql.sh
#
# 做的事: 按发行版装包 -> 启动并开机自启 -> 设置 root 密码 -> 建库
# 完成后执行: bash scripts/import_db.sh <db/complaint_analysis.sql>
set -u

DBPASS="${DBPASS:-Fqh112233!}"
DBNAME="${DBNAME:-complaint_analysis}"

while [ $# -gt 0 ]; do
  case "$1" in
    --password) DBPASS="${2:?缺少密码值}"; shift 2 ;;
    --db)       DBNAME="${2:?缺少库名}"; shift 2 ;;
    -h|--help)  sed -n '2,8p' "$0"; exit 0 ;;
    *)          echo "[失败] 未知参数: $1"; exit 1 ;;
  esac
done

# 密码会拼进 SQL 的单引号字符串 / shell 变量，禁止会破坏语法的字符
case "$DBPASS" in
  *"'"*|*'"'*|*'\'*|*'`'*|*'$'*)
    echo "[失败] 密码不能包含单引号、双引号、反斜杠、反引号或 \$"; exit 1 ;;
esac
case "$DBNAME" in
  *"'"*|*'"'*|*'\'*|*'`'*|*'$'*)
    echo "[失败] 库名不能包含引号、反斜杠、反引号或 \$"; exit 1 ;;
esac

if [ "$(id -u)" -ne 0 ]; then
  echo "[失败] 需要 root 权限，请用: sudo bash $0"; exit 1
fi

echo "[信息] 目标库: $DBNAME"

# ---------- 1. 安装 ----------
if command -v mysql >/dev/null 2>&1; then
  echo "[信息] 已检测到 mysql 客户端，跳过安装"
else
  if command -v apt-get >/dev/null 2>&1; then
    echo "[信息] Debian/Ubuntu: apt-get 安装 mysql-server"
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server
  elif command -v dnf >/dev/null 2>&1; then
    echo "[信息] RHEL/CentOS/Fedora: dnf 安装 mysql-server"
    dnf install -y mysql-server
  elif command -v yum >/dev/null 2>&1; then
    echo "[信息] RHEL/CentOS: yum 安装 mysql-server"
    yum install -y mysql-server
  else
    echo "[失败] 未识别的包管理器，请手动安装 MySQL 8 后重跑本脚本"; exit 1
  fi
fi

# ---------- 2. 启动 ----------
if command -v systemctl >/dev/null 2>&1; then
  systemctl enable mysqld >/dev/null 2>&1 || systemctl enable mysql >/dev/null 2>&1 || true
  systemctl start mysqld 2>/dev/null || systemctl start mysql 2>/dev/null || true
else
  service mysqld start 2>/dev/null || service mysql start 2>/dev/null || true
fi

echo "[信息] 等待 MySQL 就绪..."
READY=0
for i in $(seq 1 30); do
  if mysqladmin ping --silent >/dev/null 2>&1; then READY=1; break; fi
  sleep 2
done
[ "$READY" -eq 1 ] || { echo "[失败] MySQL 30 秒内未就绪，查看 journalctl -u mysqld"; exit 1; }

# ---------- 3. 设置 root 密码 + 建库 ----------
# 优先 socket 认证（Debian/Ubuntu 默认 root 走 socket 免密），其次试已有密码
if mysql -uroot -e "SELECT 1" >/dev/null 2>&1; then
  AUTH=("-uroot")
elif mysql -uroot -p"$DBPASS" -e "SELECT 1" >/dev/null 2>&1; then
  echo "[信息] root 已是目标密码，只做建库"
  AUTH=("-uroot" "-p$DBPASS")
else
  echo "[失败] 无法用 socket 或密码 $DBPASS 登录 root"
  echo "       请先手动确认 root 密码，或执行: mysql -uroot -p 后重跑"
  exit 1
fi

VER=$(mysql "${AUTH[@]}" -N -B -e "SELECT VERSION()" 2>/dev/null | head -n1)
echo "[信息] MySQL 版本: $VER"

mysql "${AUTH[@]}" <<SQL
CREATE DATABASE IF NOT EXISTS \`$DBNAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
SQL
if [ $? -ne 0 ]; then
  echo "[失败] 建库失败"; exit 1
fi

if mysql "${AUTH[@]}" -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH caching_sha2_password BY '$DBPASS'" 2>/dev/null; then
  :
else
  echo "[信息] 当前服务不支持 caching_sha2_password（可能是 MariaDB），改用默认认证"
  mysql "${AUTH[@]}" -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '$DBPASS'" \
    || { echo "[失败] 设置 root 密码失败"; exit 1; }
fi

# ---------- 4. 验证 ----------
if ! mysql -uroot -p"$DBPASS" -N -B -e "SELECT 1" >/dev/null 2>&1; then
  echo "[失败] 新密码验证失败"; exit 1
fi
mysql -uroot -p"$DBPASS" -N -B -e "SHOW DATABASES LIKE '$DBNAME'" 2>/dev/null | grep -q . \
  || { echo "[失败] 库 $DBNAME 未创建成功"; exit 1; }

echo "[成功] MySQL 已安装并配置完成（root 密码须与 backend/.env 的 DB_PASSWORD 一致）"

echo "[信息] 下一步: cd $(cd "$(dirname "$0")/.." && pwd) && bash scripts/import_db.sh"
