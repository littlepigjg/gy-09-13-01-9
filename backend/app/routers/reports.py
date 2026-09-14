"""用户行为基线报告

为指定用户汇总行为基线（常用活跃时段、常用设备、常用登录地点、交易金额
常规区间），并把近期明显偏离基线的行为（深夜登录、异地登录、大额交易）
单独标注，供前端页面直接查看。

一致性设计：
- 基线数据与「用户画像」页同源：复用画像路由的按需重建逻辑，同读内存画像
  聚合器（detection/profile.py），保证两处展示的数值一致；
- 偏离标注与检测规则同口径：直接读取检测引擎持久化的异常事件
  （anomaly_events），检测判定为异常的行为才会被标注，未被判定的不标注，
  不会出现两边结论不一致；
- 判定口径说明取自当前启用的规则参数（与检测引擎共用同一规则缓存），
  金额判定线的计算与 engine._detect_amount 使用同一公式；
- 冷启动：历史数据很少的用户返回带充分度说明的精简报告，而非报错或空白。
"""
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from ..database import db
from ..detection.engine import RULE_AMOUNT, RULE_LATE_NIGHT, RULE_REMOTE, rule_cache
from ..detection.profile import profile_aggregator
from .profiles import _ensure_loaded

router = APIRouter(prefix="/api/reports", tags=["reports"])

# 报告单独标注的偏离类型 -> 展示名称（取值与检测引擎的规则类型常量一致）
DEVIATION_TYPES = {
    RULE_LATE_NIGHT: "深夜登录",
    RULE_REMOTE: "异地登录",
    RULE_AMOUNT: "大额交易",
}

# 数据充分度参考阈值
_SUFFICIENT_EVENTS = 10  # 行为事件总量达到该值视为有一定积累
_SUFFICIENT_LOGINS = 3   # 与设备更换规则 min_logins 的默认口径一致


def _fmt_dt(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value) if value is not None else None


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# 基线汇总（与画像页同源）
# ---------------------------------------------------------------------------
def _build_baseline(profile: dict):
    """从画像序列化结果中提取报告所需的基线特征，不引入第二份统计口径。"""
    if not profile:
        return None

    # 将 UTC 小时分布归并到四个时段，便于报告阅读
    periods = {"凌晨(0-6时)": 0, "上午(6-12时)": 0, "下午(12-18时)": 0, "晚上(18-24时)": 0}
    for h, c in (profile.get("active_hours") or {}).items():
        h = int(h)
        if h < 6:
            periods["凌晨(0-6时)"] += c
        elif h < 12:
            periods["上午(6-12时)"] += c
        elif h < 18:
            periods["下午(12-18时)"] += c
        else:
            periods["晚上(18-24时)"] += c

    # 交易金额常规区间：均值 ± 2 倍标准差（下界不小于 0），仅供参考；
    # 大额交易的判定线以 criteria 中的规则口径为准
    amount_range = None
    mean = profile.get("amount_mean")
    std = profile.get("amount_std")
    if mean is not None:
        std = std or 0.0
        amount_range = [max(0.0, round(mean - 2 * std, 2)), round(mean + 2 * std, 2)]

    return {
        "total_events": profile.get("total_events", 0),
        "event_counts": profile.get("event_counts") or {},
        "top_active_hours": profile.get("top_active_hours") or [],
        "active_hours": profile.get("active_hours") or {},
        "active_periods": periods,
        "devices": profile.get("devices") or {},
        "dominant_device": profile.get("dominant_device"),
        "locations": profile.get("locations") or {},
        "dominant_location": profile.get("dominant_location"),
        "transaction_count": profile.get("transaction_count", 0),
        "amount_mean": mean,
        "amount_std": std,
        "amount_normal_range": amount_range,
        "first_seen": profile.get("first_seen"),
        "last_seen": profile.get("last_seen"),
    }


# ---------------------------------------------------------------------------
# 判定口径（与检测引擎共用同一规则缓存）
# ---------------------------------------------------------------------------
def _rules_of(rules, rtype):
    return [r for r in rules if r["rule_type"] == rtype]


def _build_criteria(user_id: str, rules: list) -> dict:
    criteria = {}

    late = _rules_of(rules, RULE_LATE_NIGHT)
    if late:
        p = late[0]["params"]
        start = int(p.get("late_start_hour", 0))
        end = int(p.get("late_end_hour", 5))
        criteria[RULE_LATE_NIGHT] = {
            "enabled": True,
            "rule_name": late[0]["name"],
            "late_start_hour": start,
            "late_end_hour": end,
            "description": f"{start}~{end} 点（UTC）之间登录判定为深夜登录",
        }
    else:
        criteria[RULE_LATE_NIGHT] = {"enabled": False, "description": "规则未启用"}

    remote = _rules_of(rules, RULE_REMOTE)
    if remote:
        criteria[RULE_REMOTE] = {
            "enabled": True,
            "rule_name": remote[0]["name"],
            "description": "登录地区或 IP 段与近 7 天常用地址不一致",
        }
    else:
        criteria[RULE_REMOTE] = {"enabled": False, "description": "规则未启用"}

    amount = _rules_of(rules, RULE_AMOUNT)
    if amount:
        p = amount[0]["params"]
        abs_threshold = float(p.get("abs_threshold", 10000))
        multiplier = float(p.get("multiplier", 3.0))
        min_samples = int(p.get("min_samples", 5))
        # 与 engine._detect_amount 相同的判定线口径：
        # 样本不足时仅用绝对阈值兜底，否则 max(绝对阈值, 历史均值 × 倍数)
        baseline = profile_aggregator.amount_baseline(user_id)
        if baseline is None or baseline[2] < min_samples:
            effective = abs_threshold
            basis = f"历史样本不足（<{min_samples} 笔），仅按绝对阈值判定"
            compare = "≥"
        else:
            effective = max(abs_threshold, baseline[0] * multiplier)
            basis = f"max(绝对阈值 {abs_threshold:g}, 历史均值 {round(baseline[0], 2)} × {multiplier:g})"
            compare = ">"
        criteria[RULE_AMOUNT] = {
            "enabled": True,
            "rule_name": amount[0]["name"],
            "abs_threshold": abs_threshold,
            "multiplier": multiplier,
            "min_samples": min_samples,
            "effective_threshold": round(effective, 2),
            "description": f"单笔交易金额 {compare} {round(effective, 2)} 元判定为大额交易（{basis}）",
        }
    else:
        criteria[RULE_AMOUNT] = {"enabled": False, "description": "规则未启用"}

    return criteria


# ---------------------------------------------------------------------------
# 数据充分度（冷启动用户也能得到合理说明）
# ---------------------------------------------------------------------------
def _build_sufficiency(profile: dict, criteria: dict) -> dict:
    if not profile:
        return {
            "level": "none",
            "total_events": 0,
            "login_count": 0,
            "transaction_count": 0,
            "notes": ["该用户暂无行为数据，基线暂未建立；产生行为数据后报告会自动丰富"],
        }

    total = profile.get("total_events", 0)
    logins = (profile.get("event_counts") or {}).get("login", 0)
    tx = profile.get("transaction_count", 0)
    min_samples = (criteria.get(RULE_AMOUNT) or {}).get("min_samples", 5)

    notes = []
    if total < _SUFFICIENT_EVENTS:
        notes.append(f"行为事件总量较少（{total} 条），基线仅供参考")
    if logins < _SUFFICIENT_LOGINS:
        notes.append(f"登录记录较少（{logins} 次），常用登录地点基线尚不稳定")
    if tx == 0:
        notes.append("暂无交易记录，交易金额常规区间暂未建立")
    elif tx < min_samples:
        notes.append(f"交易样本不足（{tx}/{min_samples} 笔），大额交易判定仅使用绝对阈值")

    return {
        "level": "limited" if notes else "sufficient",
        "total_events": total,
        "login_count": logins,
        "transaction_count": tx,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# 近期偏离行为（直接读取检测引擎的判定结果，保证口径一致）
# ---------------------------------------------------------------------------
def _summarize(rtype: str, detail: dict) -> str:
    if rtype == RULE_LATE_NIGHT:
        hour = detail.get("hour")
        window = detail.get("window") or []
        if hour is not None and len(window) == 2:
            return f"{hour} 点（UTC）登录，处于深夜时段 {window[0]}~{window[1]} 点"
        return detail.get("reason") or "深夜时段登录"
    if rtype == RULE_REMOTE:
        if detail.get("reason"):
            return detail["reason"]
        dom, cur = detail.get("dominant_location"), detail.get("current_location")
        if dom and cur:
            return f"常用地区 {dom} -> 当前 {cur}"
        return "登录地点与常用地址不一致"
    if rtype == RULE_AMOUNT:
        amount = detail.get("amount")
        threshold = detail.get("threshold", detail.get("abs_threshold"))
        if amount is not None and threshold is not None:
            return f"单笔交易 {amount} 元，达到大额判定线 {threshold} 元"
        return detail.get("reason") or "单笔交易金额异常"
    return detail.get("reason") or ""


def _load_deviations(user_id: str, recent_days: int) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=recent_days)).strftime("%Y-%m-%d %H:%M:%S")
    # 异常事件由检测引擎在判定当时写入；按当前规则类型关联归类。
    # 已删除规则产生的历史异常无法归类，不计入报告。
    rows = db.query(
        "SELECT a.id, a.rule_id, a.rule_name, a.severity, a.score, a.detail, a.event_time, "
        "r.rule_type FROM anomaly_events a JOIN audit_rules r ON a.rule_id = r.id "
        "WHERE a.user_id = %s AND r.rule_type IN (%s, %s, %s) AND a.event_time >= %s "
        "ORDER BY a.event_time DESC LIMIT 100",
        (user_id, RULE_LATE_NIGHT, RULE_REMOTE, RULE_AMOUNT, cutoff),
    )

    items = []
    by_type = {t: 0 for t in DEVIATION_TYPES}
    for r in rows:
        rtype = r["rule_type"]
        detail = r["detail"]
        if isinstance(detail, str):
            try:
                detail = json.loads(detail)
            except ValueError:
                detail = {}
        detail = detail or {}
        by_type[rtype] += 1
        items.append({
            "id": r["id"],
            "type": rtype,
            "type_label": DEVIATION_TYPES[rtype],
            "rule_id": r["rule_id"],
            "rule_name": r["rule_name"],
            "severity": r["severity"],
            "score": r["score"],
            "summary": _summarize(rtype, detail),
            "detail": detail,
            "event_time": _fmt_dt(r["event_time"]),
        })

    return {"total": len(items), "by_type": by_type, "items": items}


# ---------------------------------------------------------------------------
@router.get("/baseline/{user_id}")
def baseline_report(user_id: str, recent_days: int = Query(7, ge=1, le=90)):
    """生成指定用户的行为基线报告。

    recent_days：偏离行为的统计窗口（近 N 天，默认 7 天）。
    """
    # 与画像页同源的加载逻辑：内存画像缺失时从历史日志重放重建
    _ensure_loaded(user_id)
    profile = profile_aggregator.get(user_id)

    rules = rule_cache.get()  # 与检测引擎同一规则缓存
    criteria = _build_criteria(user_id, rules)

    return {
        "user_id": user_id,
        "generated_at": _now_str(),
        "recent_days": recent_days,
        "data_sufficiency": _build_sufficiency(profile, criteria),
        "baseline": _build_baseline(profile),
        "criteria": criteria,
        "deviations": _load_deviations(user_id, recent_days),
    }
