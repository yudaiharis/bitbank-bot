import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trades.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loop_num INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            pair TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            amount_jpy REAL NOT NULL,
            fee REAL DEFAULT 0,
            pnl REAL,
            balance_after REAL,
            status TEXT DEFAULT 'open',
            reason TEXT
        );

        CREATE TABLE IF NOT EXISTS pair_switches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loop_num INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            from_pair TEXT,
            to_pair TEXT NOT NULL,
            from_score REAL,
            to_score REAL,
            reason TEXT
        );

        CREATE TABLE IF NOT EXISTS volatility_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loop_num INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            pair TEXT NOT NULL,
            score REAL,
            volume_jpy REAL,
            spread_pct REAL,
            last_price REAL
        );

        CREATE TABLE IF NOT EXISTS loop_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loop_num INTEGER UNIQUE NOT NULL,
            timestamp TEXT NOT NULL,
            total_trades INTEGER,
            win_trades INTEGER,
            win_rate REAL,
            total_pnl REAL,
            max_drawdown REAL,
            sharpe_ratio REAL,
            final_balance REAL,
            target_achieved INTEGER DEFAULT 0,
            improvements TEXT
        );
        """)


def save_trade(trade: dict):
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO trades
            (loop_num, timestamp, pair, side, entry_price, amount_jpy, fee, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'open')
        """, (
            trade["loop_num"], datetime.now().isoformat(),
            trade["pair"], trade["side"],
            trade["entry_price"], trade["amount_jpy"],
            trade.get("fee", 0),
        ))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def close_trade(trade_id: int, exit_price: float, pnl: float, balance: float, reason: str):
    with get_conn() as conn:
        conn.execute("""
        UPDATE trades SET
            exit_price=?, pnl=?, balance_after=?, status='closed', reason=?
        WHERE id=?
        """, (exit_price, pnl, balance, reason, trade_id))


def get_trades(loop_num: int = None) -> list:
    with get_conn() as conn:
        if loop_num is not None:
            rows = conn.execute(
                "SELECT * FROM trades WHERE loop_num=? AND status='closed' ORDER BY timestamp",
                (loop_num,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='closed' ORDER BY timestamp"
            ).fetchall()
        return [dict(r) for r in rows]


def save_loop_result(result: dict):
    with get_conn() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO loop_results
            (loop_num, timestamp, total_trades, win_trades, win_rate,
             total_pnl, max_drawdown, sharpe_ratio, final_balance,
             target_achieved, improvements)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result["loop_num"], datetime.now().isoformat(),
            result["total_trades"], result["win_trades"], result["win_rate"],
            result["total_pnl"], result["max_drawdown"], result["sharpe_ratio"],
            result["final_balance"], result["target_achieved"],
            result.get("improvements", ""),
        ))


def get_all_loop_results() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM loop_results ORDER BY loop_num").fetchall()
        return [dict(r) for r in rows]
