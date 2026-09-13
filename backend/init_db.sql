-- ============================================================
-- 用户行为审计系统 - 数据库初始化脚本
-- 使用 MySQL 8.0
-- ============================================================

CREATE DATABASE IF NOT EXISTS audit_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE audit_db;

-- ------------------------------------------------------------
-- 用户行为日志表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_behavior_logs (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id     VARCHAR(64)  NOT NULL COMMENT '用户标识',
    event_type  VARCHAR(32)  NOT NULL COMMENT '事件类型: login/click/transaction',
    event_time  DATETIME(3)  NOT NULL COMMENT '事件发生时间(毫秒精度)',
    ip          VARCHAR(45)  NULL COMMENT '来源 IP',
    device      VARCHAR(64)  NULL COMMENT '设备标识',
    location    VARCHAR(64)  NULL COMMENT '登录/操作地区',
    amount      DECIMAL(12,2) NULL COMMENT '交易金额(仅 transaction)',
    detail      JSON         NULL COMMENT '扩展明细',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_user_time  (user_id, event_time),
    KEY idx_type_time  (event_type, event_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户行为日志';

-- ------------------------------------------------------------
-- 审计规则表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_rules (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name        VARCHAR(64)  NOT NULL COMMENT '规则名称',
    rule_type   VARCHAR(32)  NOT NULL COMMENT '规则类型',
    event_type  VARCHAR(32)  NULL COMMENT '适用事件类型',
    description TEXT         NULL COMMENT '规则说明',
    params      JSON         NOT NULL COMMENT '规则参数(窗口、阈值等)',
    enabled     TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用',
    severity    VARCHAR(16)  NOT NULL DEFAULT 'medium' COMMENT '告警级别',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_rule_type (rule_type),
    KEY idx_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='审计规则';

-- ------------------------------------------------------------
-- 异常事件表（原始检测结果，未聚合）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS anomaly_events (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id     VARCHAR(64)  NOT NULL COMMENT '用户标识',
    event_type  VARCHAR(32)  NULL COMMENT '事件类型',
    rule_id     BIGINT UNSIGNED NULL COMMENT '触发规则',
    rule_name   VARCHAR(64)  NULL COMMENT '规则名称',
    severity    VARCHAR(16)  NOT NULL DEFAULT 'medium' COMMENT '严重程度',
    score       FLOAT        NOT NULL DEFAULT 0 COMMENT '异常分数',
    detail      JSON         NULL COMMENT '检测详情(基线、阈值、实际值等)',
    event_time  DATETIME(3)  NOT NULL COMMENT '异常发生时间',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_user_time (user_id, event_time),
    KEY idx_rule (rule_id),
    KEY idx_severity (severity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='异常事件';

-- ------------------------------------------------------------
-- 告警表（聚合 + 去重后的结果）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    alert_key     VARCHAR(128) NOT NULL COMMENT '去重指纹',
    user_id       VARCHAR(64)  NOT NULL COMMENT '用户标识',
    rule_id       BIGINT UNSIGNED NULL COMMENT '触发规则',
    rule_name     VARCHAR(64)  NULL COMMENT '规则名称',
    severity      VARCHAR(16)  NOT NULL DEFAULT 'medium' COMMENT '严重程度',
    anomaly_count INT          NOT NULL DEFAULT 1 COMMENT '聚合的异常数量',
    first_time    DATETIME(3)  NOT NULL COMMENT '首次发生时间',
    last_time     DATETIME(3)  NOT NULL COMMENT '最近发生时间',
    status        VARCHAR(16)  NOT NULL DEFAULT 'open' COMMENT 'open/acknowledged/resolved/suppressed',
    summary       TEXT         NULL COMMENT '告警摘要',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_alert_key (alert_key),
    KEY idx_status (status),
    KEY idx_user (user_id),
    KEY idx_last_time (last_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='告警(聚合去重)';

-- ------------------------------------------------------------
-- 通知表（告警产生时写入）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    alert_id    BIGINT UNSIGNED NULL COMMENT '关联告警',
    user_id     VARCHAR(64)  NOT NULL COMMENT '用户标识',
    rule_name   VARCHAR(64)  NULL COMMENT '规则名称',
    severity    VARCHAR(16)  NOT NULL DEFAULT 'medium' COMMENT '严重程度',
    channel     VARCHAR(16)  NOT NULL DEFAULT 'web' COMMENT '通知渠道',
    content     TEXT         NULL COMMENT '通知内容',
    status      VARCHAR(16)  NOT NULL DEFAULT 'unread' COMMENT 'unread/read',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_user (user_id),
    KEY idx_status (status),
    KEY idx_alert (alert_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='告警通知';
