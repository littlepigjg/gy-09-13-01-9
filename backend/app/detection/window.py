"""滑动窗口状态管理

为每个 (user_id, event_type) 维护滑动窗口，并维护历史基线统计，
用于支持高效的流式实时异常检测。

设计要点（对应难点）：
1. 流式事件处理效率：使用 deque + 惰性驱逐，均摊 O(1) 更新；
2. 窗口状态管理：为不同规则维护独立的时间戳窗口与桶计数器；
3. 阈值动态调整：使用 Welford 在线算法维护历史基线的均值/标准差，
   阈值随基线漂移自适应。
"""
import math
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone


def to_timestamp(t) -> float:
    """统一将 datetime / float / int 转换为 UTC 秒级时间戳。"""
    if isinstance(t, datetime):
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.timestamp()
    return float(t)


class SlidingWindow:
    """基于时间戳 deque 的滑动窗口，支持 O(1) 均摊驱逐与计数。"""

    def __init__(self):
        self._ts = deque()

    def add(self, ts: float) -> None:
        self._ts.append(ts)

    def count_within(self, window_seconds: float, now: float) -> int:
        self._evict(now - window_seconds)
        return len(self._ts)

    def _evict(self, cutoff: float) -> None:
        while self._ts and self._ts[0] < cutoff:
            self._ts.popleft()

    def __len__(self):
        return len(self._ts)


class WelfordStats:
    """Welford 在线均值/方差，用于历史基线统计。"""

    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self.m2 = 0.0

    def update(self, x: float) -> None:
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (x - self.mean)

    def std(self) -> float:
        if self.n < 2:
            return 0.0
        return math.sqrt(self.m2 / (self.n - 1))


class BucketCounter:
    """固定时间桶计数器，用于历史基线对比（统计模型）。

    每个桶代表固定时间片（默认 300s），桶完成时把该桶计数喂入基线，
    从而得到用户/事件类型的历史“桶内频次”分布。粗粒度桶能避免稀疏点击
    场景下基线方差过小导致的误报。
    """

    def __init__(self, bucket_seconds: float = 300.0, history_size: int = 288):
        self.bucket_seconds = bucket_seconds
        self.history = deque(maxlen=history_size)
        self.stats = WelfordStats()
        self.current_bucket = 0
        self.current_count = 0

    def add(self, ts: float) -> None:
        bucket = int(ts // self.bucket_seconds)
        if self.current_count == 0:
            self.current_bucket = bucket
            self.current_count = 1
            return

        gap = bucket - self.current_bucket
        if gap == 0:
            self.current_count += 1
        else:
            # 当前桶完成，喂入基线；中间空桶补 0（代表空闲期）
            self._commit(self.current_count)
            # 补 0，但限制补桶数量避免长时间空闲产生大量零
            zeros = min(gap - 1, self.history.maxlen)
            for _ in range(zeros):
                self._commit(0)
            self.current_bucket = bucket
            self.current_count = 1

    def _commit(self, value: int) -> None:
        self.history.append(value)
        self.stats.update(float(value))

    def current(self) -> int:
        return self.current_count

    def baseline(self):
        return self.stats.mean, self.stats.std(), len(self.history)


class WindowState:
    """检测引擎的内存状态容器，线程安全。"""

    def __init__(self):
        self._lock = threading.RLock()
        self.sliding = defaultdict(SlidingWindow)
        self.buckets = defaultdict(lambda: BucketCounter(300.0, 288))
        self.location_history = defaultdict(deque)  # user_id -> deque[(ts, ip, location)]

    def add_event(self, user_id: str, event_type: str, ts: float,
                  ip: str = None, location: str = None) -> None:
        with self._lock:
            self.sliding[(user_id, event_type)].add(ts)
            self.buckets[(user_id, event_type)].add(ts)
            if event_type == "login":
                self.location_history[user_id].append((ts, ip, location))
                # 仅保留最近 7 天登录记录
                cutoff = ts - 7 * 86400
                while self.location_history[user_id] and self.location_history[user_id][0][0] < cutoff:
                    self.location_history[user_id].popleft()

    def sliding_count(self, user_id: str, event_type: str, window_seconds: float, now: float) -> int:
        with self._lock:
            return self.sliding[(user_id, event_type)].count_within(window_seconds, now)

    def bucket_baseline(self, user_id: str, event_type: str):
        with self._lock:
            b = self.buckets[(user_id, event_type)]
            return b.current(), b.baseline(), b.bucket_seconds

    def dominant_location(self, user_id: str, now: float) -> tuple:
        """返回用户近期最常见的 (ip, location)，无历史则返回 (None, None)。"""
        with self._lock:
            hist = self.location_history[user_id]
            cutoff = now - 7 * 86400
            recent = [(ip, loc) for ts, ip, loc in hist if ts >= cutoff and (ip or loc)]
            if not recent:
                return None, None
            from collections import Counter
            (ip, loc), _ = Counter(recent).most_common(1)[0]
            return ip, loc

    def distinct_login_sources(self, user_id: str, window_seconds: float, now: float) -> int:
        """返回指定时间窗口内，用户登录来源（IP 段 + 地区）的去重数量。"""
        with self._lock:
            hist = self.location_history[user_id]
            cutoff = now - window_seconds
            sources = set()
            for ts, ip, loc in hist:
                if ts >= cutoff:
                    seg = ".".join(ip.split(".")[:2]) if ip else ""
                    sources.add((seg, loc))
            return len(sources)


# 全局单例（每个进程一份内存状态）
window_state = WindowState()
