"""Pydantic 请求/响应模型"""
from typing import Any, Optional

from pydantic import BaseModel, Field


class BehaviorEvent(BaseModel):
    user_id: str = Field(..., description="用户标识")
    event_type: str = Field(..., description="事件类型: login/click/transaction")
    event_time: Any = Field(..., description="事件时间(datetime 或时间戳)")
    ip: Optional[str] = None
    device: Optional[str] = None
    location: Optional[str] = None
    amount: Optional[float] = None
    detail: Optional[dict] = None


class RuleCreate(BaseModel):
    name: str
    rule_type: str
    event_type: Optional[str] = None
    description: Optional[str] = None
    params: dict = Field(default_factory=dict)
    enabled: bool = True
    severity: str = "medium"


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    rule_type: Optional[str] = None
    event_type: Optional[str] = None
    description: Optional[str] = None
    params: Optional[dict] = None
    enabled: Optional[bool] = None
    severity: Optional[str] = None
