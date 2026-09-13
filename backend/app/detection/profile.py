"""用户画像聚合器（内存态）

聚合每个用户的行为统计特征，既用于前端画像展示，也供部分检测规则
（单笔金额异常、设备更换）读取历史基线，与滑动窗口状态（window.py）形成
跨模块依赖。

设计要点：
- 线程安全：使用 RLock 保护内部状态；
- 在线统计：交易金额用 Welford 算法维护均值/标准差；
- 冷启动：新用户无历史时不参与需要基线的判定。
"""
import threading
from collections import Counter, defaultdict

from .window import WelfordStats, to_timestamp


class ProfileAggregator:
    def __init__(self):
        self._lock = threading.RLock()
        self._profiles = defaultdict(dict)

    def update(self, event: dict):
        user_id = event.get("user_id")
        event_type = event.get("event_type")
        ts = to_timestamp(event.get("event_time"))
        with self._lock:
            p = self._profiles[user_id]
            p["user_id"] = user_id
            p["total_events"] = p.get("total_events", 0) + 1

            counts = p.setdefault("event_counts", Counter())
            counts[event_type] += 1

            hours = p.setdefault("active_hours", Counter())
            from datetime import datetime, timezone
            hour = datetime.fromtimestamp(ts, tz=timezone.utc).hour
            hours[hour] += 1

            if event.get("device"):
                p.setdefault("devices", Counter())[event["device"]] += 1
            if event.get("location"):
                p.setdefault("locations", Counter())[event["location"]] += 1

            if event_type == "transaction" and event.get("amount") is not None:
                stats = p.setdefault("amount_stats", WelfordStats())
                stats.update(float(event["amount"]))
                p["transaction_count"] = p.get("transaction_count", 0) + 1

            if "first_seen" not in p:
                p["first_seen"] = ts
            p["last_seen"] = ts

            if event_type == "login":
                p["last_login"] = {
                    "ts": ts,
                    "ip": event.get("ip"),
                    "location": event.get("location"),
                    "device": event.get("device"),
                }

    def get(self, user_id: str) -> dict:
        with self._lock:
            p = self._profiles.get(user_id)
            if not p:
                return None
            return self._serialize(p)

    def list_user_ids(self):
        with self._lock:
            return sorted(self._profiles.keys())

    def raw(self, user_id: str):
        with self._lock:
            return self._profiles.get(user_id)

    # ---- 供检测规则使用的基线读取 ----
    def amount_baseline(self, user_id: str):
        """返回 (mean, std, n)。"""
        with self._lock:
            p = self._profiles.get(user_id)
            stats = p.get("amount_stats") if p else None
            if not stats or stats.n < 2:
                return None
            return stats.mean, stats.std(), stats.n

    def known_devices(self, user_id: str):
        with self._lock:
            p = self._profiles.get(user_id)
            if not p:
                return set()
            return set((p.get("devices") or Counter()).keys())

    def login_count(self, user_id: str):
        with self._lock:
            p = self._profiles.get(user_id)
            if not p:
                return 0
            return (p.get("event_counts") or Counter()).get("login", 0)

    # ---- 序列化 ----
    def _serialize(self, p: dict) -> dict:
        from datetime import datetime, timezone

        def fmt(ts):
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        amount_mean = amount_std = None
        stats = p.get("amount_stats")
        if stats and stats.n > 0:
            amount_mean = round(stats.mean, 2)
            amount_std = round(stats.std(), 2) if stats.n >= 2 else 0.0

        devices = p.get("devices") or Counter()
        locations = p.get("locations") or Counter()
        hours = p.get("active_hours") or Counter()
        counts = p.get("event_counts") or Counter()

        top_hours = [h for h, _ in hours.most_common(3)]
        last_login = p.get("last_login")

        return {
            "user_id": p["user_id"],
            "total_events": p.get("total_events", 0),
            "event_counts": dict(counts),
            "active_hours": dict(sorted(hours.items())),
            "top_active_hours": top_hours,
            "devices": dict(devices),
            "dominant_device": devices.most_common(1)[0][0] if devices else None,
            "locations": dict(locations),
            "dominant_location": locations.most_common(1)[0][0] if locations else None,
            "transaction_count": p.get("transaction_count", 0),
            "amount_mean": amount_mean,
            "amount_std": amount_std,
            "first_seen": fmt(p.get("first_seen")) if p.get("first_seen") else None,
            "last_seen": fmt(p.get("last_seen")) if p.get("last_seen") else None,
            "last_login": last_login,
        }


# 全局单例（每个进程一份）
profile_aggregator = ProfileAggregator()
