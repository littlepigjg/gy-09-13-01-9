# 用户行为审计系统

基于 **Python(FastAPI) + Vue3 + MySQL** 的实时用户行为审计系统。采集登录、点击、交易等操作日志，通过规则引擎与统计模型（滑动窗口 + 历史基线对比）实时检测异常行为，支持告警聚合、去重与误报控制，并提供可视化前端。

## 功能特性

- **日志采集**：支持单条 / 批量采集用户行为日志（登录、点击、交易）。
- **规则检测**：
  - 深夜登录（凌晨时段登录）
  - 异地登录（IP 段 / 地区与常用地址不一致）
  - 高频操作（短窗口内操作频次超阈值，支持动态阈值）
  - 设备更换（历史未出现的新设备登录）
  - 多地快速登录（短时间窗口内多来源登录）
- **统计模型检测**：
  - 历史基线偏差（滑动窗口 + Welford 在线均值/方差 + z-score）
  - 单笔金额异常（交易金额偏离用户历史基线）
- **用户画像**：聚合活跃时段、常用设备 / 地区、交易金额均值与标准差等特征。
- **基线报告**：为指定用户生成行为基线报告（常用活跃时段、常用设备、常用登录地点、交易金额常规区间），并单独标注近期偏离基线的行为（深夜登录、异地登录、大额交易）；基线数据与画像页同源，偏离标注直接采用检测引擎的判定结果，与检测规则口径一致；历史数据很少的用户返回带充分度说明的精简报告。
- **告警聚合与误报控制**：`md5(用户+规则+时间桶)` 指纹去重、冷却窗口压制、聚合计数与严重度升级。
- **告警通知**：告警产生时写入通知记录，支持已读 / 未读管理。
- **可视化前端**：概览、行为时间线、异常事件、规则配置、用户画像、通知。

## 技术架构

```
用户操作日志 ──▶ 后端(FastAPI) ──▶ 检测引擎(滑动窗口 + 用户画像) ──▶ 异常事件 ──▶ 告警聚合/去重 ──▶ 通知
                       │                                                        │
                       ▼                                                        ▼
                  MySQL (日志/规则/异常/告警/通知)                            MySQL
                                                                               ▲
                 Vue3 前端 ── Nginx 反向代理 /api ────────────────────────────┘
```

难点对应的实现：

| 难点 | 实现 |
| --- | --- |
| 流式事件处理效率 | 内存 `deque` 惰性驱逐，均摊 O(1) 更新 |
| 窗口状态管理 | 每 `(用户, 事件类型)` 独立滑动窗口 + 时间桶计数器 |
| 异常判定阈值动态调整 | Welford 在线基线 + 动态阈值 `max(基准阈值, 基线均值×倍数+余量)` |
| 告警去重机制 | 时间桶指纹去重 + 冷却窗口 + 聚合升级 |

## 目录结构

```
.
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 配置(读环境变量)
│   │   ├── database.py          # MySQL 连接池
│   │   ├── schemas.py           # Pydantic 模型
│   │   ├── detection/
│   │   │   ├── window.py        # 滑动窗口 / 基线统计
│   │   │   ├── profile.py       # 用户画像聚合器
│   │   │   └── engine.py        # 检测引擎 + 告警聚合去重 + 通知
│   │   └── routers/             # 日志/异常/规则/告警/统计/画像/通知路由
│   ├── init_db.sql              # 建库建表脚本
│   ├── seed.py                  # 初始化 + 演示数据
│   ├── requirements.txt
│   ├── Dockerfile
│   └── entrypoint.sh
├── frontend/
│   ├── src/
│   │   ├── views/               # 概览/时间线/异常/规则/画像/通知
│   │   ├── api/                 # axios 封装
│   │   └── router/
│   ├── nginx.conf
│   └── Dockerfile
├── docker-compose.yml
└── start.sh
```

## 一键启动（Docker）

前置条件：已安装 Docker 与 Docker Compose。

```bash
docker compose up -d --build
```

启动后访问：

- 前端：http://localhost:5173
- 后端 API 文档：http://localhost:8010/docs
- MySQL：`localhost:13306`（root / root，库 `audit_db`）

首次启动会自动初始化表结构并写入演示数据（约 1390 条日志、52 条异常、11 条聚合告警，覆盖 7 类检测规则）；重启不会重置数据。如需重置演示数据：

```bash
docker compose exec backend python seed.py
```

停止 / 清理：

```bash
docker compose down          # 停止并保留数据卷
docker compose down -v       # 停止并删除数据卷（彻底清空）
```

## 本地开发启动（不使用 Docker）

### 1. 初始化 MySQL

```bash
mysql -uroot -proot -e "CREATE DATABASE IF NOT EXISTS audit_db DEFAULT CHARACTER SET utf8mb4"
```

### 2. 启动后端

```bash
cd backend
pip install -r requirements.txt
python seed.py                                   # 建表 + 演示数据
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev                                      # http://localhost:5173
```

> 本地前端通过 Vite 代理将 `/api` 转发到后端；后端默认连接 `127.0.0.1:3306` 的 MySQL（root / root）。可通过环境变量 `AUDIT_DB_HOST / AUDIT_DB_PORT / AUDIT_DB_USER / AUDIT_DB_PASSWORD / AUDIT_DB_NAME` 覆盖。

## 主要 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/logs/ingest` | 采集单条日志并实时检测 |
| POST | `/api/logs/ingest/batch` | 批量采集日志 |
| GET | `/api/logs` | 查询行为时间线 |
| GET | `/api/anomalies` | 查询异常事件 |
| GET | `/api/alerts` | 查询聚合告警 |
| PATCH | `/api/alerts/{id}/status` | 更新告警状态 |
| GET/POST | `/api/rules` | 查询 / 新增规则 |
| PUT/DELETE | `/api/rules/{id}` | 修改 / 删除规则 |
| GET | `/api/stats/overview` | 概览统计 |
| GET | `/api/stats/users` | 按用户聚合统计 |
| GET | `/api/stats/rules` | 按规则聚合统计 |
| GET | `/api/profiles` | 用户画像列表 |
| GET | `/api/profiles/{user_id}` | 单个用户画像 |
| GET | `/api/reports/baseline/{user_id}` | 用户行为基线报告（`recent_days` 控制偏离统计窗口，默认 7 天） |
| GET | `/api/notifications` | 告警通知列表 |
| PATCH | `/api/notifications/{id}/read` | 标记通知已读 |
| PATCH | `/api/notifications/read-all` | 全部标记已读 |

### 日志采集示例

```bash
curl -X POST http://localhost:8010/api/logs/ingest \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1001","event_type":"login","event_time":"2026-09-11T03:15:00Z","ip":"10.0.1.10","location":"北京","device":"web"}'
```

## 规则参数说明

| 规则类型 | 关键参数 |
| --- | --- |
| `late_night_login` | `late_start_hour`、`late_end_hour` |
| `remote_login` | `min_history` |
| `high_frequency` | `window_seconds`、`threshold`、`use_baseline`、`multiplier`、`margin` |
| `baseline_deviation` | `window_seconds`、`zscore_threshold`、`min_history`、`min_count` |
| `amount_anomaly` | `abs_threshold`、`multiplier`、`min_samples` |
| `device_change` | `min_logins` |
| `rapid_login` | `window_seconds`、`min_distinct` |

所有规则均可配置 `dedup_window_seconds`（聚合窗口）与 `cooldown_seconds`（冷却/压制窗口），可在「规则配置」页面在线调整。
