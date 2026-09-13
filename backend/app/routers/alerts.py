"""告警查询与状态更新"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..database import db

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertStatus(BaseModel):
    status: str  # open/acknowledged/resolved/suppressed


@router.get("")
def list_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    where, params = [], []
    if status:
        where.append("status = %s")
        params.append(status)
    if severity:
        where.append("severity = %s")
        params.append(severity)
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)

    cond = (" WHERE " + " AND ".join(where)) if where else ""
    total = db.query_one(f"SELECT COUNT(*) AS c FROM alerts{cond}", tuple(params))["c"]
    rows = db.query(
        f"SELECT * FROM alerts{cond} ORDER BY last_time DESC LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset),
    )
    return {"total": total, "items": rows}


@router.patch("/{alert_id}/status")
def update_status(alert_id: int, body: AlertStatus):
    allowed = {"open", "acknowledged", "resolved", "suppressed"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail="无效状态")
    db.execute("UPDATE alerts SET status = %s WHERE id = %s", (body.status, alert_id))
    return {"ok": True}
