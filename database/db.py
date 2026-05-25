import sqlite3
import json
from datetime import datetime

DB_PATH = "sales_bot.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            first_seen TEXT,
            last_seen TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            customer_name TEXT,
            order_details TEXT,
            status TEXT DEFAULT 'new',
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()


def upsert_customer(chat_id: int, username: str, full_name: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("""
        INSERT INTO customers (chat_id, username, full_name, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            username=excluded.username,
            full_name=excluded.full_name,
            last_seen=excluded.last_seen
    """, (chat_id, username, full_name, now, now))
    conn.commit()
    conn.close()


def save_message(chat_id: int, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (chat_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (chat_id, role, content, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_history(chat_id: int, limit: int = 20) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT role, content FROM messages
        WHERE chat_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (chat_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{"role": row[0], "content": row[1]} for row in reversed(rows)]


def save_order(chat_id: int, customer_name: str, order_details: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO orders (chat_id, customer_name, order_details, timestamp) VALUES (?, ?, ?, ?)",
        (chat_id, customer_name, order_details, datetime.now().isoformat())
    )
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    return order_id


def get_all_orders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, customer_name, order_details, status, timestamp FROM orders ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows
