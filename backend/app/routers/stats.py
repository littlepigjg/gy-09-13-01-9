"""统计概览"""
from fastapi import APIRouter

from ..database import db

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/overview")
def overview():
    total_logs = db.query_one("SELECT COUNT(*) AS c FROM user_behavior_logs")["c"]
    total_anomalies = db.query_one("SELECT COUNT(*) AS c FROM anomaly_events")["c"]
    open_alerts = db.query_one("SELECT COUNT(*) AS c FROM alerts WHERE status = 'open'")["c"]

    event_type_dist = db.query(
        "SELECT event_type, COUNT(*) AS c FROM user_behavior_logs GROUP BY event_type ORDER BY c DESC"
    )
    severity_dist = db.query(
        "SELECT severity, COUNT(*) AS c FROM anomaly_events GROUP BY severity ORDER BY c DESC"
    )
    recent_anomalies = db.query(
        "SELECT id, user_id, rule_name, severity, event_time FROM anomaly_events "
        "ORDER BY event_time DESC LIMIT 10"
    )
    return {
        "total_logs": total_logs,
        "total_anomalies": total_anomalies,
        "open_alerts": open_alerts,
        "event_type_dist": event_type_dist,
        "severity_dist": severity_dist,
        "recent_anomalies": recent_anomalies,
    }


@router.get("/users")
def users():
    """按用户聚合：日志数 / 异常数 / 待处理告警数 / 最后活跃时间。"""
    rows = db.query(
        "SELECT l.user_id, "
        "COUNT(DISTINCT l.id) AS log_count, "
        "COUNT(DISTINCT a.id) AS anomaly_count, "
        "(SELECT COUNT(*) FROM alerts al WHERE al.user_id = l.user_id AND al.status = 'open') AS open_alerts, "
        "MAX(l.event_time) AS last_active "
        "FROM user_behavior_logs l "
        "LEFT JOIN anomaly_events a ON a.user_id = l.user_id "
        "GROUP BY l.user_id ORDER BY log_count DESC"
    )
    return {"items": rows}


@router.get("/rules")
def rules():
    """按规则聚合：触发异常次数、告警数。"""
    rows = db.query(
        "SELECT rule_name, COUNT(*) AS anomaly_count, "
        "SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END) AS high_count, "
        "SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) AS critical_count "
        "FROM anomaly_events GROUP BY rule_name ORDER BY anomaly_count DESC"
    )
    return {"items": rows}
