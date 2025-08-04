"""
데이터베이스 핸들러 모듈
운영 모드(PostgreSQL)와 테스트 모드(SQLite)를 전환하여 데이터베이스 상호작용을 관리합니다.
"""
import os
import psycopg2
import psycopg2.pool
import sqlite3
from typing import Dict, Any
from config.config import TestConfig

# --- 전역 변수 ---
db_pool = None
DB_MODE = os.environ.get("APP_MODE", "PRODUCTION")

# --- PostgreSQL 함수들 ---
def pg_init_pool(config):
    global db_pool
    db_pool = psycopg2.pool.SimpleConnectionPool(
        1, 10,
        user=config.DB_USER, password=config.DB_PASSWORD,
        host=config.DB_HOST, port=config.DB_PORT, dbname=config.DB_NAME
    )

def pg_get_conn():
    return db_pool.getconn()

def pg_put_conn(conn):
    db_pool.putconn(conn)

def pg_create_tables(conn):
    with conn.cursor() as cursor:
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS coin_config (
            ticker TEXT PRIMARY KEY,
            is_active BOOLEAN DEFAULT TRUE,
            budget_krw REAL DEFAULT 0,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS grid (
            id SERIAL PRIMARY KEY, ticker TEXT NOT NULL, grid_level INTEGER NOT NULL,
            buy_price_target REAL NOT NULL, sell_price_target REAL NOT NULL,
            order_krw_amount REAL NOT NULL, is_bought BOOLEAN DEFAULT FALSE,
            actual_bought_volume REAL, actual_buy_fill_price REAL,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (ticker, grid_level)
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY, ticker TEXT NOT NULL, buy_sell TEXT NOT NULL,
            grid_level INTEGER NOT NULL, price REAL NOT NULL, amount REAL NOT NULL,
            volume REAL NOT NULL, fee REAL, profit REAL, profit_percentage REAL,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS balance_history (
            id SERIAL PRIMARY KEY, ticker TEXT NOT NULL, krw_balance REAL,
            coin_balance REAL, coin_avg_price REAL, total_assets REAL,
            current_price REAL, timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.commit()

def pg_execute(sql, params):
    conn = pg_get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            conn.commit()
    finally:
        pg_put_conn(conn)

def pg_fetchone(sql, params):
    conn = pg_get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()
    finally:
        pg_put_conn(conn)

# --- SQLite 함수들 (테스트용) ---
def sqlite_init_pool(config):
    global db_pool
    # 테스트용 DB 경로를 config에서 가져와서 사용
    db_dir = TestConfig.get_test_db_dir()
    db_path = db_dir / "test_mode.db"
    print(f"테스트 DB 경로: {db_path}") # DB 경로 확인용 출력
    db_pool = sqlite3.connect(db_path, check_same_thread=False)
    db_pool.row_factory = sqlite3.Row

def sqlite_get_conn():
    return db_pool

def sqlite_put_conn(conn):
    pass # SQLite 인메모리에서는 필요 없음

def sqlite_create_tables(conn):
    conn.execute('''
    CREATE TABLE IF NOT EXISTS coin_config (
        ticker TEXT PRIMARY KEY, is_active BOOLEAN DEFAULT 1,
        budget_krw REAL DEFAULT 0, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''
    CREATE TABLE IF NOT EXISTS grid (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, grid_level INTEGER,
        buy_price_target REAL, sell_price_target REAL, order_krw_amount REAL,
        is_bought BOOLEAN, actual_bought_volume REAL, actual_buy_fill_price REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE (ticker, grid_level)
    )''')
    conn.execute('''
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, buy_sell TEXT,
        grid_level INTEGER, price REAL, amount REAL, volume REAL, fee REAL,
        profit REAL, profit_percentage REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''
    CREATE TABLE IF NOT EXISTS balance_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, krw_balance REAL,
        coin_balance REAL, coin_avg_price REAL, total_assets REAL,
        current_price REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()

def sqlite_execute(sql, params):
    conn = sqlite_get_conn()
    sql = sql.replace("%s", "?")
    # SQLite UPSERT 구문 변환
    if "ON CONFLICT (ticker, grid_level) DO UPDATE" in sql:
        sql = sql.replace("EXCLUDED.", "")
    if "ON CONFLICT (ticker) DO UPDATE" in sql:
        sql = sql.replace("EXCLUDED.", "")
    conn.execute(sql, params)
    conn.commit()

def sqlite_fetchone(sql, params):
    conn = sqlite_get_conn()
    sql = sql.replace("%s", "?")
    cursor = conn.cursor()
    cursor.execute(sql, params)
    return cursor.fetchone()


def get_db_mode():
    return os.environ.get("APP_MODE", "PRODUCTION")

# --- Public 인터페이스 ---
def init_db(config):
    if get_db_mode() == "TEST":
        sqlite_init_pool(config)
    else:
        pg_init_pool(config)

def get_connection():
    if get_db_mode() == "TEST":
        return sqlite_get_conn()
    else:
        return pg_get_conn()

def put_connection(conn):
    if get_db_mode() == "TEST":
        sqlite_put_conn(conn)
    else:
        pg_put_conn(conn)

def create_all_tables():
    conn = get_connection()
    try:
        if get_db_mode() == "TEST":
            sqlite_create_tables(conn)
        else:
            pg_create_tables(conn)
    finally:
        put_connection(conn)

def execute(sql, params=()):
    if get_db_mode() == "TEST":
        sqlite_execute(sql, params)
    else:
        pg_execute(sql, params)

def fetchone(sql, params=()):
    if get_db_mode() == "TEST":
        return sqlite_fetchone(sql, params)
    else:
        return pg_fetchone(sql, params)
