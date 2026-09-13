"""行为日志采集与查询"""
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query

from ..database import db
from ..detection.engine import engine
from ..schemas import BehaviorEvent

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _parse_event_time(value) -> datetime:
    """兼容 datetime、ISO 字符串、秒/毫秒时间戳。"""
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        # 毫秒时间戳
        if value > 1e12:
            value = value / 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        s = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
    return datetime.now(timezone.utc)


def _to_db_dt(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


@router.post("/ingest")
def ingest_log(event: BehaviorEvent):
    """采集单条用户行为日志并实时检测。"""
    return ingest_batch([event])


@router.post("/ingest/batch")
def ingest_batch(events: list[BehaviorEvent]):
    """批量采集日志（流式高效处理）。"""
    inserted = 0
    detected = 0
    for e in events:
        data = e.model_dump()
        dt = _parse_event_time(data["event_time"])
        db_dt = _to_db_dt(dt)

        db.insert(
            "INSERT INTO user_behavior_logs (user_id, event_type, event_time, ip, device, "
            "location, amount, detail) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                data["user_id"], data["event_type"], db_dt,
                data.get("ip"), data.get("device"), data.get("location"),
                data.get("amount"), json.dumps(data.get("detail") or {}, ensure_ascii=False),
            ),
        )
        inserted += 1

        # 使用 datetime 对象喂给检测引擎
        anomalies = engine.process_event({**data, "event_time": dt})
        detected += len(anomalies)

    return {"inserted": inserted, "detected_anomalies": detected}


@router.get("")
def list_logs(
    user_id: Optional[str] = None,
    event_type: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """查询用户行为时间线。"""
    where, params = [], []
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)
    if event_type:
        where.append("event_type = %s")
        params.append(event_type)
    if start_time:
        where.append("event_time >= %s")
        params.append(start_time)
    if end_time:
        where.append("event_time <= %s")
        params.append(end_time)

    cond = (" WHERE " + " AND ".join(where)) if where else ""
    total = db.query_one(f"SELECT COUNT(*) AS c FROM user_behavior_logs{cond}", tuple(params))["c"]
    rows = db.query(
        f"SELECT id, user_id, event_type, event_time, ip, device, location, amount, detail "
        f"FROM user_behavior_logs{cond} ORDER BY event_time DESC LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset),
    )
    return {"total": total, "items": rows}
