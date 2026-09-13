"""异常事件查询"""
from typing import Optional

from fastapi import APIRouter, Query

from ..database import db

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


@router.get("")
def list_anomalies(
    user_id: Optional[str] = None,
    severity: Optional[str] = None,
    rule_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    where, params = [], []
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)
    if severity:
        where.append("severity = %s")
        params.append(severity)
    if rule_id:
        where.append("rule_id = %s")
        params.append(rule_id)

    cond = (" WHERE " + " AND ".join(where)) if where else ""
    total = db.query_one(f"SELECT COUNT(*) AS c FROM anomaly_events{cond}", tuple(params))["c"]
    rows = db.query(
        f"SELECT id, user_id, event_type, rule_id, rule_name, severity, score, detail, event_time "
        f"FROM anomaly_events{cond} ORDER BY event_time DESC LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset),
    )
    return {"total": total, "items": rows}
