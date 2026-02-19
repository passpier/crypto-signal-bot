"""Trade journal — persists live signals and tracks their outcomes."""
import sqlite3
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils import get_project_root, IS_CLOUD_RUN

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS journal_trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id     TEXT UNIQUE,
    created_at    TEXT NOT NULL,
    action        TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    interval      TEXT NOT NULL,
    entry_price   REAL NOT NULL,
    stop_loss     REAL NOT NULL,
    take_profit   REAL NOT NULL,
    strength      INTEGER,
    status        TEXT DEFAULT 'OPEN',
    exit_price    REAL,
    exit_reason   TEXT,
    profit_pct    REAL,
    resolved_at   TEXT
)
"""

_GCS_OBJECT = "trade-journal/trade_journal.db"


class TradeJournal:
    """SQLite-backed live trade journal with optional GCS sync for Cloud Run."""

    def __init__(self, db_path: Optional[str] = None, gcs_bucket: Optional[str] = None):
        if db_path is None:
            if IS_CLOUD_RUN:
                db_path = str(Path('/tmp') / 'trade_journal.db')
            else:
                data_dir = get_project_root() / 'data'
                data_dir.mkdir(parents=True, exist_ok=True)
                db_path = str(data_dir / 'trade_journal.db')

        self.db_path = db_path
        self.gcs_bucket = gcs_bucket
        self.conn: Optional[sqlite3.Connection] = None

        if gcs_bucket:
            self._download_from_gcs()

        self._init_database()

    # ── GCS sync ──────────────────────────────────────────────────────────────

    def _download_from_gcs(self):
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(self.gcs_bucket)
            blob = bucket.blob(_GCS_OBJECT)
            if blob.exists():
                blob.download_to_filename(self.db_path)
                logger.info(f"✓ Downloaded trade journal from gs://{self.gcs_bucket}/{_GCS_OBJECT}")
            else:
                logger.info("No existing trade journal in GCS — starting fresh")
        except Exception as e:
            logger.warning(f"⚠ GCS download failed (continuing without): {e}")

    def _upload_to_gcs(self):
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(self.gcs_bucket)
            blob = bucket.blob(_GCS_OBJECT)
            blob.upload_from_filename(self.db_path)
            logger.info(f"✓ Uploaded trade journal to gs://{self.gcs_bucket}/{_GCS_OBJECT}")
        except Exception as e:
            logger.warning(f"⚠ GCS upload failed (data may be lost on next Cloud Run restart): {e}")

    # ── Database ──────────────────────────────────────────────────────────────

    def _init_database(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_CREATE_TABLE)
        self.conn.commit()
        logger.info(f"Trade journal DB ready: {self.db_path}")

    # ── Public API ────────────────────────────────────────────────────────────

    def record_signal(self, signal: Dict, symbol: str, interval: str) -> bool:
        """
        Record a BUY/SELL signal to the journal.

        Returns True on new insert, False if the hour-slot already exists
        (idempotent — safe to call multiple times per hour).
        """
        action = signal.get('action', 'HOLD')
        if action not in ('BUY', 'SELL'):
            return False

        trade_plan = signal.get('trade_plan') or {}
        stops = trade_plan.get('stops') or {}
        targets = trade_plan.get('targets') or {}

        stop_loss = stops.get('hard_stop')
        take_profit = targets.get('T2')
        entry_price = signal.get('price')

        if stop_loss is None or take_profit is None or entry_price is None:
            logger.warning(
                "⚠ Cannot record signal: missing entry_price, hard_stop, or T2 target"
            )
            return False

        now = datetime.now(timezone.utc)
        # Round to hour for dedup key
        hour_slot = now.replace(minute=0, second=0, microsecond=0)
        signal_id = f"{symbol}_{interval}_{hour_slot.strftime('%Y%m%dT%H')}"
        created_at = now.isoformat()

        try:
            cursor = self.conn.execute(
                """
                INSERT OR IGNORE INTO journal_trades
                    (signal_id, created_at, action, symbol, interval,
                     entry_price, stop_loss, take_profit, strength)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id, created_at, action, symbol, interval,
                    float(entry_price), float(stop_loss), float(take_profit),
                    int(signal.get('strength') or 0),
                ),
            )
            self.conn.commit()
            inserted = cursor.rowcount > 0
            if inserted:
                logger.info(
                    f"✓ Recorded {action} signal to journal (id={signal_id}, "
                    f"entry={entry_price}, stop={stop_loss}, tp={take_profit})"
                )
            else:
                logger.info(f"Signal already recorded this hour (id={signal_id}) — skipped")
            return inserted
        except Exception as e:
            logger.warning(f"⚠ Failed to record signal: {e}")
            return False

    def resolve_open_trades(self, fetcher) -> int:
        """
        Check all OPEN trades against historical price data and resolve them.

        Returns the number of trades resolved.
        """
        cursor = self.conn.execute(
            "SELECT * FROM journal_trades WHERE status = 'OPEN' ORDER BY created_at ASC"
        )
        open_trades: List[sqlite3.Row] = cursor.fetchall()

        if not open_trades:
            logger.info("No open trades to resolve")
            return 0

        now = datetime.now(timezone.utc)

        # Find oldest open trade to determine how much history to fetch
        oldest_dt = datetime.fromisoformat(open_trades[0]['created_at'])
        days_needed = max(3, int((now - oldest_dt).total_seconds() / 86400) + 2)

        # Assume all trades share the same interval (they should in practice)
        interval = open_trades[0]['interval']

        try:
            df = fetcher.fetch_historical_data(days=days_needed, interval=interval)
        except Exception as e:
            logger.warning(f"⚠ Could not fetch history for trade resolution: {e}")
            return 0

        resolved_count = 0
        for trade in open_trades:
            trade_dict = dict(trade)
            resolved = self._resolve_single_trade(trade_dict, df, now)
            if resolved:
                resolved_count += 1

        logger.info(f"Resolved {resolved_count}/{len(open_trades)} open trades")
        return resolved_count

    def _resolve_single_trade(self, trade: Dict, df, now: datetime) -> bool:
        """
        Resolve a single open trade against candle data.

        Resolution rules (first hit wins, candle-by-candle):
        - BUY: low < stop_loss → LOSS; high > take_profit → WIN
        - SELL: high > stop_loss → LOSS; low < take_profit → WIN
        - Same candle: use relative distance from entry (closer = hit first)
        - After 24 elapsed candles (1 day on 1h): EXPIRED
        """
        created_at = datetime.fromisoformat(trade['created_at'])
        # Filter candles strictly after signal creation
        candles_after = df[df['timestamp'] > created_at].copy()

        action = trade['action']
        entry = trade['entry_price']
        stop = trade['stop_loss']
        tp = trade['take_profit']

        status = None
        exit_price = None
        exit_reason = None
        resolved_at = None

        expiry_candles = 24  # ~1 trading day on 1h interval
        elapsed = 0

        for _, row in candles_after.iterrows():
            high = float(row['high'])
            low = float(row['low'])
            close = float(row['close'])
            elapsed += 1

            if action == 'BUY':
                stop_hit = low < stop
                tp_hit = high > tp
            else:  # SELL
                stop_hit = high > stop
                tp_hit = low < tp

            if stop_hit and tp_hit:
                # Same candle: determine which level is closer to entry
                dist_stop = abs(entry - stop)
                dist_tp = abs(entry - tp)
                if dist_stop <= dist_tp:
                    stop_hit, tp_hit = True, False
                else:
                    stop_hit, tp_hit = False, True

            if stop_hit:
                status = 'LOSS'
                exit_price = stop
                exit_reason = 'STOP_HIT'
                resolved_at = row['timestamp'].isoformat()
                break
            elif tp_hit:
                status = 'WIN'
                exit_price = tp
                exit_reason = 'TARGET_HIT'
                resolved_at = row['timestamp'].isoformat()
                break

            if elapsed >= expiry_candles:
                status = 'EXPIRED'
                exit_price = close
                exit_reason = 'EXPIRED'
                resolved_at = row['timestamp'].isoformat()
                break

        if status is None:
            # Not enough history yet — leave OPEN
            return False

        # Compute profit percentage
        if action == 'BUY':
            profit_pct = (exit_price - entry) / entry * 100
        else:
            profit_pct = (entry - exit_price) / entry * 100

        try:
            self.conn.execute(
                """
                UPDATE journal_trades
                SET status=?, exit_price=?, exit_reason=?, profit_pct=?, resolved_at=?
                WHERE id=?
                """,
                (status, exit_price, exit_reason, profit_pct, resolved_at, trade['id']),
            )
            self.conn.commit()
            logger.info(
                f"Resolved trade #{trade['id']} ({trade['action']}): "
                f"{status} | profit={profit_pct:+.2f}% | reason={exit_reason}"
            )
            return True
        except Exception as e:
            logger.warning(f"⚠ Failed to update trade #{trade['id']}: {e}")
            return False

    def compute_live_stats(self, days: int = 30) -> Optional[Dict]:
        """
        Compute live performance stats from closed trades in the last `days` days.

        WIN and LOSS count toward win_rate; EXPIRED are excluded (inconclusive).
        Returns None if there are no decisive (WIN/LOSS) trades.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        cursor = self.conn.execute(
            """
            SELECT status, profit_pct
            FROM journal_trades
            WHERE resolved_at >= ? AND status IN ('WIN', 'LOSS', 'EXPIRED')
            ORDER BY resolved_at ASC
            """,
            (cutoff,),
        )
        rows = cursor.fetchall()

        wins = [r['profit_pct'] for r in rows if r['status'] == 'WIN']
        losses = [r['profit_pct'] for r in rows if r['status'] == 'LOSS']
        expired_count = sum(1 for r in rows if r['status'] == 'EXPIRED')

        total = len(wins) + len(losses)
        if total == 0:
            return None  # No decisive trades

        all_decisive = wins + losses
        win_rate = len(wins) / total * 100 if total else 0.0
        avg_profit = sum(all_decisive) / len(all_decisive) if all_decisive else 0.0
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        best_trade = max(all_decisive) if all_decisive else 0.0
        worst_trade = min(all_decisive) if all_decisive else 0.0

        # Equity curve (cumulative return starting from 0)
        equity = 0.0
        equity_curve = []
        for r in rows:
            if r['status'] in ('WIN', 'LOSS'):
                equity += r['profit_pct']
                equity_curve.append(equity)

        # Max drawdown from equity curve
        max_drawdown = 0.0
        peak = float('-inf')
        for val in equity_curve:
            if val > peak:
                peak = val
            drawdown = peak - val
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        total_return = equity_curve[-1] if equity_curve else 0.0

        return {
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'max_drawdown': max_drawdown,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'total_trades': total,
            'total_return': total_return,
            'equity_curve': equity_curve,
            'expired_count': expired_count,
        }

    def close(self):
        """Commit, close DB, and optionally upload to GCS."""
        if self.conn:
            try:
                self.conn.commit()
                self.conn.close()
                self.conn = None
            except Exception as e:
                logger.warning(f"⚠ Error closing DB: {e}")

        if self.gcs_bucket:
            self._upload_to_gcs()
