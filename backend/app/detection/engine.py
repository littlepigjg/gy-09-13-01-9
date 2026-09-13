"""实时异常检测引擎

包含：
- 规则加载与缓存
- 规则型检测（深夜登录、异地登录、高频操作、设备更换、多地快速登录）
- 统计型检测（历史基线对比、单笔金额异常，滑动窗口 + 动态阈值）
- 告警聚合与去重、误报控制（冷却/升级）、告警通知
"""
import hashlib
import json
import math
import threading
import time
from datetime import datetime, timezone

from ..database import db
from .profile import profile_aggregator
from .window import window_state, to_timestamp

# 规则类型常量
RULE_LATE_NIGHT = "late_night_login"
RULE_REMOTE = "remote_login"
RULE_HIGH_FREQ = "high_frequency"
RULE_BASELINE = "baseline_deviation"
RULE_AMOUNT = "amount_anomaly"
RULE_DEVICE = "device_change"
RULE_RAPID = "rapid_login"


def _utcnow_ts() -> float:
    return time.time()


def _now_dt():
    return datetime.now(timezone.utc)


def _fmt_dt(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class RuleCache:
    """规则缓存：定期刷新，避免每次事件都查询 DB。"""

    def __init__(self, ttl: float = 5.0):
        self._ttl = ttl
        self._lock = threading.Lock()
        self._rules = []
        self._last_load = 0.0

    def refresh(self):
        with self._lock:
            if time.time() - self._last_load < self._ttl and self._rules:
                return self._rules
            rows = db.query(
                "SELECT id, name, rule_type, event_type, description, params, "
                "enabled, severity FROM audit_rules WHERE enabled = 1"
            )
            rules = []
            for r in rows:
                params = r["params"]
                if isinstance(params, str):
                    params = json.loads(params)
                rules.append({**r, "params": params or {}})
            self._rules = rules
            self._last_load = time.time()
            return self._rules

    def get(self):
        return self.refresh()


rule_cache = RuleCache()


class AlertAggregator:
    """告警聚合 + 去重 + 误报控制。

    alert_key = md5(user_id:rule_id:时间桶)，同一用户在聚合窗口内的相同规则
    异常合并为同一条告警；冷却窗口内不再产生重复告警。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._dedup = {}  # alert_key -> (last_emit_ts, alert_id)
        self._cooldown = {}  # (user_id, rule_id) -> last_alert_ts

    def _make_key(self, user_id, rule_id, ts, bucket_seconds):
        bucket = int(ts // bucket_seconds)
        raw = f"{user_id}:{rule_id}:{bucket}"
        return hashlib.md5(raw.encode()).hexdigest()

    def process(self, anomaly: dict, dedup_window: int, cooldown: int) -> dict:
        """将一条异常事件聚合进告警，返回告警 dict（可能是已有告警）。"""
        user_id = anomaly["user_id"]
        rule_id = anomaly["rule_id"]
        ts = anomaly["ts"]

        key = self._make_key(user_id, rule_id, ts, dedup_window)

        with self._lock:
            cooldown_until = self._cooldown.get((user_id, rule_id), 0)
            cached = self._dedup.get(key)

            # 1) 去重：聚合窗口内已存在告警，则递增计数并更新时间
            if cached and ts - cached[0] < dedup_window:
                alert_id = cached[1]
                self._dedup[key] = (ts, alert_id)
                return self._increment_alert(alert_id, anomaly, ts)

            # 2) 误报控制：冷却期内直接压制（不产生新告警）
            if ts < cooldown_until:
                return None

            # 3) 新告警
            alert_id = self._create_alert(anomaly, ts, key)
            self._dedup[key] = (ts, alert_id)
            self._cooldown[(user_id, rule_id)] = ts + cooldown
            return {"id": alert_id, "status": "open", "created": True}

    def _create_alert(self, anomaly, ts, key):
        sql = (
            "INSERT INTO alerts (alert_key, user_id, rule_id, rule_name, severity, "
            "anomaly_count, first_time, last_time, status, summary) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        )
        summary = f"{anomaly['user_id']} 触发规则「{anomaly['rule_name']}」"
        params = (
            key, anomaly["user_id"], anomaly["rule_id"], anomaly["rule_name"],
            anomaly["severity"], 1,
            _fmt_dt(ts), _fmt_dt(ts), "open", summary,
        )
        alert_id = db.insert(sql, params)

        # 产生告警时写入通知（默认 channel = web）
        try:
            db.insert(
                "INSERT INTO notifications (alert_id, user_id, rule_name, severity, "
                "channel, content, status) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (alert_id, anomaly["user_id"], anomaly["rule_name"], anomaly["severity"],
                 "web", summary, "unread"),
            )
        except Exception:
            pass  # 通知失败不影响主流程
        return alert_id

    def _increment_alert(self, alert_id, anomaly, ts):
        db.execute(
            "UPDATE alerts SET anomaly_count = anomaly_count + 1, last_time = %s, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (_fmt_dt(ts), alert_id),
        )
        # 达到升级阈值则提升严重程度
        row = db.query_one("SELECT anomaly_count, severity FROM alerts WHERE id = %s", (alert_id,))
        if row and row["anomaly_count"] >= 5 and row["severity"] in ("low", "medium"):
            nxt = {"low": "medium", "medium": "high"}.get(row["severity"])
            if nxt:
                db.execute("UPDATE alerts SET severity = %s WHERE id = %s", (nxt, alert_id))
        return {"id": alert_id, "status": "open", "created": False}


alert_aggregator = AlertAggregator()


class DetectionEngine:
    """统一检测入口。"""

    SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

    def __init__(self):
        # 检测链路涉及窗口状态、画像与告警聚合，需保证原子性
        self._lock = threading.RLock()

    def process_event(self, event: dict):
        """处理单条事件，返回触发的异常列表（已持久化并聚合告警）。"""
        return self.process_batch([event])

    def process_batch(self, events: list):
        anomalies = []
        with self._lock:
            for event in events:
                anomalies.extend(self._detect(event))
        return anomalies

    # ------------------------------------------------------------------
    def _detect(self, event: dict):
        user_id = event.get("user_id")
        event_type = event.get("event_type")
        ts = to_timestamp(event.get("event_time"))
        ip = event.get("ip")
        location = event.get("location")

        # 更新滑动窗口（包含当前事件，供高频/异地/多地检测使用）
        window_state.add_event(user_id, event_type, ts, ip, location)

        detected = []
        for rule in rule_cache.get():
            if rule.get("event_type") and rule["event_type"] != event_type:
                continue
            try:
                result = self._run_rule(rule, event, ts)
            except Exception:
                # 单条规则失败不应阻塞整条流水线
                continue
            if result:
                detected.append(result)

        # 检测完成后才更新画像，保证金额/设备等规则读到的是“不含当前”的历史基线
        profile_aggregator.update(event)

        # 持久化异常事件 + 聚合告警
        for a in detected:
            self._persist_anomaly(a)
            self._aggregate(a)
        return detected

    # ------------------------------------------------------------------
    def _run_rule(self, rule, event, ts):
        rtype = rule["rule_type"]
        params = rule["params"]
        if rtype == RULE_LATE_NIGHT:
            return self._detect_late_night(rule, event, ts, params)
        if rtype == RULE_REMOTE:
            return self._detect_remote(rule, event, ts, params)
        if rtype == RULE_HIGH_FREQ:
            return self._detect_high_freq(rule, event, ts, params)
        if rtype == RULE_BASELINE:
            return self._detect_baseline(rule, event, ts, params)
        if rtype == RULE_AMOUNT:
            return self._detect_amount(rule, event, ts, params)
        if rtype == RULE_DEVICE:
            return self._detect_device(rule, event, ts, params)
        if rtype == RULE_RAPID:
            return self._detect_rapid(rule, event, ts, params)
        return None

    def _base_anomaly(self, rule, event, ts, score, detail):
        return {
            "user_id": event.get("user_id"),
            "event_type": event.get("event_type"),
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "severity": rule["severity"],
            "score": round(float(score), 3),
            "detail": detail,
            "ts": ts,
        }

    # --- 深夜登录 ------------------------------------------------------
    def _detect_late_night(self, rule, event, ts, params):
        if event.get("event_type") != "login":
            return None
        start = int(params.get("late_start_hour", 0))
        end = int(params.get("late_end_hour", 5))
        hour = datetime.fromtimestamp(ts, tz=timezone.utc).hour
        if start < end:
            in_range = start <= hour < end
        else:  # 跨零点区间，如 22:00 ~ 06:00
            in_range = hour >= start or hour < end
        if not in_range:
            return None
        detail = {"hour": hour, "window": [start, end], "reason": "深夜登录"}
        return self._base_anomaly(rule, event, ts, 2.0, detail)

    # --- 异地登录 ------------------------------------------------------
    def _detect_remote(self, rule, event, ts, params):
        if event.get("event_type") != "login":
            return None
        min_history = int(params.get("min_history", 3))
        user_id = event.get("user_id")
        dom_ip, dom_loc = window_state.dominant_location(user_id, ts)
        if dom_ip is None and dom_loc is None:
            return None  # 无历史基线，暂不判定

        cur_ip = event.get("ip")
        cur_loc = event.get("location")
        is_remote = False
        reason = []
        if dom_loc and cur_loc and cur_loc != dom_loc:
            is_remote = True
            reason.append(f"常用地区 {dom_loc} -> 当前 {cur_loc}")
        if dom_ip and cur_ip and self._ip_segment(dom_ip) != self._ip_segment(cur_ip):
            is_remote = True
            reason.append(f"常用 IP 段 {self._ip_segment(dom_ip)} -> 当前 {self._ip_segment(cur_ip)}")

        if not is_remote:
            return None
        detail = {"dominant_location": dom_loc, "dominant_ip_segment": self._ip_segment(dom_ip),
                  "current_location": cur_loc, "current_ip_segment": self._ip_segment(cur_ip),
                  "reason": " / ".join(reason)}
        return self._base_anomaly(rule, event, ts, 3.0, detail)

    @staticmethod
    def _ip_segment(ip):
        if not ip:
            return ""
        return ".".join(ip.split(".")[:2])

    # --- 高频操作 ------------------------------------------------------
    def _detect_high_freq(self, rule, event, ts, params):
        user_id = event.get("user_id")
        event_type = event.get("event_type")
        window_seconds = int(params.get("window_seconds", 60))
        base_threshold = int(params.get("threshold", 10))

        count = window_state.sliding_count(user_id, event_type, window_seconds, ts)

        threshold = base_threshold
        detail = {"count": count, "window_seconds": window_seconds, "threshold": threshold}

        # 动态阈值：按用户历史速率自适应，避免“一刀切”阈值导致的误报/漏报
        if params.get("use_baseline"):
            _, (mean, std, n), bucket_seconds = window_state.bucket_baseline(user_id, event_type)
            if n >= 3:
                multiplier = float(params.get("multiplier", 3.0))
                margin = int(params.get("margin", 2))
                # 将历史“每桶平均事件数”折算到当前窗口长度
                expected = mean * (window_seconds / bucket_seconds)
                dynamic = max(base_threshold, expected * multiplier + margin)
                threshold = dynamic
                detail["baseline_mean"] = round(mean, 2)
                detail["dynamic_threshold"] = round(dynamic, 2)

        if count < threshold:
            return None

        score = count / max(threshold, 1)
        detail["ratio"] = round(score, 2)
        return self._base_anomaly(rule, event, ts, score, detail)

    # --- 历史基线偏差（统计模型） --------------------------------------
    def _detect_baseline(self, rule, event, ts, params):
        user_id = event.get("user_id")
        event_type = event.get("event_type")
        window_seconds = int(params.get("window_seconds", 300))
        z_threshold = float(params.get("zscore_threshold", 3.0))
        min_history = int(params.get("min_history", 5))
        min_count = int(params.get("min_count", 10))

        # 当前窗口计数 vs 历史基线（按窗口长度折算）
        current = window_state.sliding_count(user_id, event_type, window_seconds, ts)
        if current < min_count:
            return None

        _, (mean, std, n), bucket_seconds = window_state.bucket_baseline(user_id, event_type)
        if n < min_history:
            return None

        # 基线均值/标准差从“每桶”折算到“当前窗口长度”
        expected = mean * (window_seconds / bucket_seconds)
        std_window = std * math.sqrt(window_seconds / bucket_seconds)
        if std_window == 0 and current <= expected:
            return None

        zscore = (current - expected) / (std_window + 1e-6)
        if zscore < z_threshold:
            return None

        detail = {
            "current_count": current,
            "baseline_mean": round(mean, 2),
            "baseline_std": round(std, 2),
            "expected_count": round(expected, 2),
            "zscore": round(zscore, 2),
            "zscore_threshold": z_threshold,
            "reason": "行为频次显著偏离历史基线",
        }
        return self._base_anomaly(rule, event, ts, zscore, detail)

    # --- 单笔金额异常 --------------------------------------------------
    def _detect_amount(self, rule, event, ts, params):
        if event.get("event_type") != "transaction":
            return None
        amount = event.get("amount")
        if amount is None:
            return None
        amount = float(amount)
        user_id = event.get("user_id")

        abs_threshold = float(params.get("abs_threshold", 10000))
        multiplier = float(params.get("multiplier", 3.0))
        min_samples = int(params.get("min_samples", 5))

        baseline = profile_aggregator.amount_baseline(user_id)
        # 冷启动：历史样本不足时仅用绝对阈值兜底
        if baseline is None or baseline[2] < min_samples:
            if amount >= abs_threshold:
                detail = {"amount": amount, "abs_threshold": abs_threshold,
                          "reason": "大额交易（历史样本不足）"}
                return self._base_anomaly(rule, event, ts, amount / abs_threshold, detail)
            return None

        mean, std, _ = baseline
        threshold = max(abs_threshold, mean * multiplier)
        if amount <= threshold:
            return None

        zscore = (amount - mean) / (std + 1e-6)
        detail = {
            "amount": amount,
            "baseline_mean": round(mean, 2),
            "baseline_std": round(std, 2),
            "threshold": round(threshold, 2),
            "zscore": round(zscore, 2),
            "reason": "单笔交易金额异常",
        }
        return self._base_anomaly(rule, event, ts, zscore, detail)

    # --- 设备更换 ------------------------------------------------------
    def _detect_device(self, rule, event, ts, params):
        if event.get("event_type") != "login":
            return None
        device = event.get("device")
        if not device:
            return None
        user_id = event.get("user_id")
        min_logins = int(params.get("min_logins", 3))

        # 冷启动：历史登录次数不足时不判定
        if profile_aggregator.login_count(user_id) < min_logins:
            return None

        known = profile_aggregator.known_devices(user_id)
        if device in known:
            return None

        detail = {"device": device, "known_devices": sorted(known), "reason": "新设备登录"}
        return self._base_anomaly(rule, event, ts, 2.5, detail)

    # --- 多地快速登录 --------------------------------------------------
    def _detect_rapid(self, rule, event, ts, params):
        if event.get("event_type") != "login":
            return None
        user_id = event.get("user_id")
        window_seconds = int(params.get("window_seconds", 300))
        min_distinct = int(params.get("min_distinct", 3))

        distinct = window_state.distinct_login_sources(user_id, window_seconds, ts)
        if distinct < min_distinct:
            return None

        detail = {
            "distinct_sources": distinct,
            "window_seconds": window_seconds,
            "min_distinct": min_distinct,
            "reason": "短时间多地登录",
        }
        return self._base_anomaly(rule, event, ts, float(distinct), detail)

    # ------------------------------------------------------------------
    def _persist_anomaly(self, a: dict):
        detail = json.dumps(a["detail"], ensure_ascii=False)
        sql = (
            "INSERT INTO anomaly_events (user_id, event_type, rule_id, rule_name, "
            "severity, score, detail, event_time) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
        )
        db.insert(sql, (
            a["user_id"], a["event_type"], a["rule_id"], a["rule_name"],
            a["severity"], a["score"], detail, _fmt_dt(a["ts"]),
        ))

    def _aggregate(self, a: dict):
        rule = next((r for r in rule_cache.get() if r["id"] == a["rule_id"]), None)
        params = (rule or {}).get("params", {})
        dedup_window = int(params.get("dedup_window_seconds", 300))
        cooldown = int(params.get("cooldown_seconds", 600))
        alert_aggregator.process(a, dedup_window, cooldown)


engine = DetectionEngine()
