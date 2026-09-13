#!/bin/sh
set -e

echo "[entrypoint] 等待 MySQL 就绪..."
python - <<'PY'
import os
import time

import pymysql

host = os.getenv("AUDIT_DB_HOST", "mysql")
port = int(os.getenv("AUDIT_DB_PORT", "3306"))
user = os.getenv("AUDIT_DB_USER", "root")
pwd = os.getenv("AUDIT_DB_PASSWORD", "root")

for _ in range(60):
    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=pwd, charset="utf8mb4")
        conn.close()
        print("[entrypoint] MySQL 已就绪")
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit("[entrypoint] MySQL 未能就绪，退出")
PY

echo "[entrypoint] 初始化数据库与演示数据（幂等）..."
python seed.py --init

echo "[entrypoint] 启动后端服务..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
