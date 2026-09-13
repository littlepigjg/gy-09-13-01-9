"""告警通知查询"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..database import db

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    where, params = [], []
    if status:
        where.append("status = %s")
        params.append(status)
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)

    cond = (" WHERE " + " AND ".join(where)) if where else ""
    total = db.query_one(f"SELECT COUNT(*) AS c FROM notifications{cond}", tuple(params))["c"]
    rows = db.query(
        f"SELECT * FROM notifications{cond} ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset),
    )
    return {"total": total, "items": rows}


@router.patch("/{notification_id}/read")
def mark_read(notification_id: int):
    db.execute("UPDATE notifications SET status = 'read' WHERE id = %s", (notification_id,))
    return {"ok": True}


@router.patch("/read-all")
def mark_all_read():
    db.execute("UPDATE notifications SET status = 'read' WHERE status = 'unread'")
    return {"ok": True}
