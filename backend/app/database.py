"""MySQL 连接池（基于 PyMySQL 的轻量线程安全实现）"""
import threading

import pymysql
from pymysql.cursors import DictCursor

from .config import config


class ConnectionPool:
    """极简线程安全连接池，避免引入额外依赖。"""

    def __init__(self, size: int = 10):
        self._size = size
        self._lock = threading.Lock()
        self._pool = []
        self._in_use = 0

    def _new_connection(self):
        return pymysql.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            charset=config.DB_CHARSET,
            cursorclass=DictCursor,
            autocommit=True,
        )

    def get(self):
        with self._lock:
            if self._pool:
                return self._pool.pop()
            if self._in_use < self._size:
                self._in_use += 1
                return self._new_connection()
        # 池已满：直接新建临时连接（上限之外的连接由调用方负责归还/关闭）
        return self._new_connection()

    def put(self, conn):
        with self._lock:
            if len(self._pool) < self._size:
                self._pool.append(conn)
            else:
                conn.close()

    def close(self, conn):
        with self._lock:
            self._in_use = max(0, self._in_use - 1)
        try:
            conn.close()
        except Exception:
            pass


pool = ConnectionPool(size=config.DB_POOL_SIZE)


class Database:
    """提供带上下文管理器的查询入口。"""

    def connection(self):
        return pool.get()

    @staticmethod
    def execute(sql: str, params: tuple = ()):
        conn = pool.get()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        finally:
            pool.put(conn)

    @staticmethod
    def query(sql: str, params: tuple = ()):
        conn = pool.get()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        finally:
            pool.put(conn)

    @staticmethod
    def query_one(sql: str, params: tuple = ()):
        rows = Database.query(sql, params)
        return rows[0] if rows else None

    @staticmethod
    def insert(sql: str, params: tuple = ()):
        """执行插入并返回自增主键。"""
        conn = pool.get()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                conn.commit()
                return cur.lastrowid
        finally:
            pool.put(conn)


db = Database()
