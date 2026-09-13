"""初始化数据库、写入默认规则、生成演示数据并触发实时检测。

用法：
    cd backend && python3 seed.py

会先重建表结构，再写入规则与近 7 天行为日志，并按时间顺序喂入检测引擎，
使历史基线得到学习、异常行为被实时识别。
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

# 允许直接以脚本方式运行时导入 app 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import config  # noqa: E402
from app.database import db  # noqa: E402
from app.detection.engine import engine  # noqa: E402

random.seed(20260911)


def _admin_conn(database=None):
    import pymysql
    return pymysql.connect(
        host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER,
        password=config.DB_PASSWORD, charset=config.DB_CHARSET,
        database=database, autocommit=True,
    )


# ---------------------------------------------------------------------------
# 1. 重建 schema
# ---------------------------------------------------------------------------
def init_schema(drop: bool = True):
    import pymysql
    # 1) 建库（drop=True 时先重建）
    conn = _admin_conn()
    with conn.cursor() as cur:
        if drop:
            cur.execute(f"DROP DATABASE IF EXISTS `{config.DB_NAME}`")
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` "
            "DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci"
        )
    conn.close()

    # 2) 读取建表脚本，剔除注释行后逐条执行
    sql_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "init_db.sql")
    with open(sql_path, encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if not ln.strip().startswith("--")]
    sql = "\n".join(lines)

    conn = _admin_conn(database=config.DB_NAME)
    with conn.cursor() as cur:
        for stmt in sql.split(";"):
            s = stmt.strip()
            if s:
                cur.execute(s)
    conn.close()


def is_seeded() -> bool:
    """判断数据库是否已经初始化过（以规则表是否有数据为准）。"""
    try:
        row = db.query_one("SELECT COUNT(*) AS c FROM audit_rules")
        return bool(row and row["c"] > 0)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 2. 默认规则
# ---------------------------------------------------------------------------
DEFAULT_RULES = [
    {
        "name": "深夜登录",
        "rule_type": "late_night_login",
        "event_type": "login",
        "description": "在凌晨 0~5 点发生的登录行为",
        "params": {"late_start_hour": 0, "late_end_hour": 5,
                   "dedup_window_seconds": 1800, "cooldown_seconds": 3600},
        "severity": "medium",
    },
    {
        "name": "异地登录",
        "rule_type": "remote_login",
        "event_type": "login",
        "description": "登录 IP 段或地区与用户常用地址不一致",
        "params": {"min_history": 3, "dedup_window_seconds": 1800, "cooldown_seconds": 3600},
        "severity": "high",
    },
    {
        "name": "高频操作",
        "rule_type": "high_frequency",
        "event_type": None,
        "description": "短时间窗口内操作频次超过阈值（支持动态阈值）",
        "params": {"window_seconds": 60, "threshold": 10, "use_baseline": True,
                   "multiplier": 3.0, "margin": 2,
                   "dedup_window_seconds": 300, "cooldown_seconds": 600},
        "severity": "medium",
    },
    {
        "name": "历史基线偏差",
        "rule_type": "baseline_deviation",
        "event_type": None,
        "description": "行为频次显著偏离用户历史基线（z-score）",
        "params": {"window_seconds": 300, "zscore_threshold": 3.0, "min_history": 5,
                   "min_count": 10,
                   "dedup_window_seconds": 300, "cooldown_seconds": 600},
        "severity": "high",
    },
    {
        "name": "单笔金额异常",
        "rule_type": "amount_anomaly",
        "event_type": "transaction",
        "description": "单笔交易金额显著高于用户历史基线",
        "params": {"abs_threshold": 10000, "multiplier": 3.0, "min_samples": 5,
                   "dedup_window_seconds": 300, "cooldown_seconds": 600},
        "severity": "high",
    },
    {
        "name": "设备更换",
        "rule_type": "device_change",
        "event_type": "login",
        "description": "使用历史未出现过的新设备登录",
        "params": {"min_logins": 3,
                   "dedup_window_seconds": 1800, "cooldown_seconds": 3600},
        "severity": "medium",
    },
    {
        "name": "多地快速登录",
        "rule_type": "rapid_login",
        "event_type": "login",
        "description": "短时间窗口内从多个不同地点/IP段登录",
        "params": {"window_seconds": 300, "min_distinct": 3,
                   "dedup_window_seconds": 300, "cooldown_seconds": 600},
        "severity": "high",
    },
]


def seed_rules():
    for r in DEFAULT_RULES:
        db.insert(
            "INSERT INTO audit_rules (name, rule_type, event_type, description, params, enabled, severity) "
            "VALUES (%s,%s,%s,%s,%s,1,%s)",
            (r["name"], r["rule_type"], r["event_type"], r["description"],
             json.dumps(r["params"], ensure_ascii=False), r["severity"]),
        )


# ---------------------------------------------------------------------------
# 3. 演示数据
# ---------------------------------------------------------------------------
USERS = [
    {"id": "u1001", "loc": "北京", "ip": "10.0.1.10"},
    {"id": "u1002", "loc": "上海", "ip": "10.0.2.20"},
    {"id": "u1003", "loc": "广州", "ip": "10.0.3.30"},
    {"id": "u1004", "loc": "深圳", "ip": "10.0.4.40"},
    {"id": "u1005", "loc": "杭州", "ip": "10.0.5.50"},
    {"id": "u1006", "loc": "成都", "ip": "10.0.6.60"},
]
REMOTE_IP = {"北京": "203.0.113.5", "上海": "203.0.113.6", "广州": "203.0.113.7",
             "深圳": "203.0.113.8", "杭州": "203.0.113.9", "成都": "203.0.113.10"}


def gen_normal_events(user, day: int, base: datetime):
    """生成某用户某一天的正常行为。"""
    events = []
    loc = user["loc"]
    ip = user["ip"]
    day_base = base - timedelta(days=day)

    def at(h, m, s):
        return day_base.replace(hour=h, minute=m, second=s, microsecond=0)

    # 白天登录 2~4 次（8~21 点，避开深夜）
    for _ in range(random.randint(2, 4)):
        h = random.randint(8, 21)
        m = random.randint(0, 59)
        s = random.randint(0, 59)
        events.append({
            "user_id": user["id"], "event_type": "login",
            "event_time": at(h, m, s),
            "ip": ip, "location": loc, "device": "web",
        })
    # 点击 15~40 次（白天分散）
    for _ in range(random.randint(15, 40)):
        h = random.randint(8, 22)
        m = random.randint(0, 59)
        s = random.randint(0, 59)
        events.append({
            "user_id": user["id"], "event_type": "click",
            "event_time": at(h, m, s),
            "ip": ip, "location": loc, "device": "web",
        })
    # 交易 0~3 次
    for _ in range(random.randint(0, 3)):
        h = random.randint(9, 21)
        m = random.randint(0, 59)
        s = random.randint(0, 59)
        events.append({
            "user_id": user["id"], "event_type": "transaction",
            "event_time": at(h, m, s),
            "ip": ip, "location": loc, "device": "app",
            "amount": round(random.uniform(10, 2000), 2),
        })
    return events


def gen_anomaly_events(base: datetime):
    """构造明确的异常行为样本（均发生在近期，便于在时间线顶部展示）。"""

    def recent_at(hour, minute=0):
        t = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return t if t <= base else t - timedelta(days=1)

    events = []
    # 深夜登录：u1001 今日凌晨 3 点登录
    events.append({
        "user_id": "u1001", "event_type": "login",
        "event_time": recent_at(3),
        "ip": "10.0.1.10", "location": "北京", "device": "web",
    })
    # 异地登录：u1002 近期从境外 IP 段登录（白天时段）
    events.append({
        "user_id": "u1002", "event_type": "login",
        "event_time": base - timedelta(minutes=90),
        "ip": REMOTE_IP["上海"], "location": "纽约", "device": "web",
    })
    # 高频操作：u1003 在 60 秒内 25 次点击
    t0 = base - timedelta(minutes=45)
    for i in range(25):
        events.append({
            "user_id": "u1003", "event_type": "click",
            "event_time": t0 + timedelta(seconds=i * 2),
            "ip": "10.0.3.30", "location": "广州", "device": "web",
        })
    # 高频交易：u1004 在 60 秒内 15 次交易（同时触发基线偏差）
    t1 = base - timedelta(minutes=20)
    for i in range(15):
        events.append({
            "user_id": "u1004", "event_type": "transaction",
            "event_time": t1 + timedelta(seconds=i * 3),
            "ip": "10.0.4.40", "location": "深圳", "device": "app",
            "amount": random.uniform(50, 500),
        })
    # 单笔金额异常：u1005 一笔大额交易（50000，远超历史基线）
    events.append({
        "user_id": "u1005", "event_type": "transaction",
        "event_time": base - timedelta(minutes=15),
        "ip": "10.0.5.50", "location": "杭州", "device": "app",
        "amount": 50000.0,
    })
    # 设备更换：u1006 使用历史未出现的新设备 tablet 登录
    events.append({
        "user_id": "u1006", "event_type": "login",
        "event_time": base - timedelta(minutes=10),
        "ip": "10.0.6.60", "location": "成都", "device": "tablet",
    })
    # 多地快速登录：u1001 在 5 分钟内从 3 个不同城市登录
    rapid_sources = [("10.0.1.10", "北京"), ("10.1.1.10", "天津"), ("10.2.1.10", "上海")]
    t_rapid = base - timedelta(minutes=5)
    for i, (ip, loc) in enumerate(rapid_sources):
        events.append({
            "user_id": "u1001", "event_type": "login",
            "event_time": t_rapid + timedelta(seconds=i * 60),
            "ip": ip, "location": loc, "device": "web",
        })
    return events


def seed_logs_and_detect():
    base = datetime.now(timezone.utc)
    all_events = []
    # 正常历史：过去 7 天
    for day in range(7, 0, -1):
        for user in USERS:
            all_events.extend(gen_normal_events(user, day, base))
    # 异常样本：最近 2 小时
    all_events.extend(gen_anomaly_events(base))

    # 按时间顺序喂入引擎（构建基线 -> 检测异常）
    all_events.sort(key=lambda e: e["event_time"])

    def to_db_dt(dt: datetime) -> str:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    anomaly_total = 0
    for e in all_events:
        # 持久化行为日志
        db.insert(
            "INSERT INTO user_behavior_logs (user_id, event_type, event_time, ip, device, "
            "location, amount, detail) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (e["user_id"], e["event_type"], to_db_dt(e["event_time"]),
             e.get("ip"), e.get("device"), e.get("location"),
             e.get("amount"), json.dumps(e.get("detail") or {}, ensure_ascii=False)),
        )
        # 实时检测
        anomalies = engine.process_event(e)
        anomaly_total += len(anomalies)

    print(f"[seed] 生成日志 {len(all_events)} 条，检出异常事件 {anomaly_total} 条")


def run(drop: bool = True):
    print("[seed] 初始化数据库...")
    init_schema(drop=drop)

    if not drop and is_seeded():
        print("[seed] 数据库已初始化，跳过种子数据")
        return

    print("[seed] 写入默认规则...")
    seed_rules()
    print("[seed] 生成演示数据并检测...")
    seed_logs_and_detect()
    print("[seed] 完成")


if __name__ == "__main__":
    # 默认重建数据库并写入演示数据；--init 为幂等初始化（容器启动用）
    drop = "--init" not in sys.argv and "--no-drop" not in sys.argv
    run(drop=drop)
