"""用户画像查询

画像数据以内存态维护（见 detection/profile.py）；服务重启后内存画像为空，
本模块会按需从 MySQL 的历史日志中重放重建，保证查询可用。
"""
from fastapi import APIRouter, HTTPException

from ..database import db
from ..detection.profile import profile_aggregator

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


def _load_profile(user_id: str):
    rows = db.query(
        "SELECT user_id, event_type, event_time, ip, device, location, amount "
        "FROM user_behavior_logs WHERE user_id = %s ORDER BY event_time",
        (user_id,),
    )
    for r in rows:
        profile_aggregator.update({
            "user_id": r["user_id"],
            "event_type": r["event_type"],
            "event_time": r["event_time"],
            "ip": r["ip"],
            "device": r["device"],
            "location": r["location"],
            "amount": float(r["amount"]) if r["amount"] is not None else None,
        })


def _ensure_loaded(user_id: str = None):
    if user_id:
        if not profile_aggregator.get(user_id):
            _load_profile(user_id)
        return
    # 列表：补载所有历史用户
    existing = set(profile_aggregator.list_user_ids())
    rows = db.query("SELECT DISTINCT user_id FROM user_behavior_logs")
    for r in rows:
        if r["user_id"] not in existing:
            _load_profile(r["user_id"])


@router.get("")
def list_profiles():
    _ensure_loaded()
    uids = profile_aggregator.list_user_ids()
    return {"items": [profile_aggregator.get(u) for u in uids]}


@router.get("/{user_id}")
def get_profile(user_id: str):
    _ensure_loaded(user_id)
    profile = profile_aggregator.get(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="用户不存在")
    return profile
