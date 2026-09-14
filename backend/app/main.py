"""用户行为审计系统 - FastAPI 入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import alerts, anomalies, logs, notifications, profiles, reports, rules, stats

app = FastAPI(
    title="用户行为审计系统",
    description="采集用户操作日志，基于规则与统计模型（滑动窗口）实时检测异常行为",
    version="1.0.0",
)

# 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(logs.router)
app.include_router(anomalies.router)
app.include_router(rules.router)
app.include_router(alerts.router)
app.include_router(stats.router)
app.include_router(profiles.router)
app.include_router(reports.router)
app.include_router(notifications.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
