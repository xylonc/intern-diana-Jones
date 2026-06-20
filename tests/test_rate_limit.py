"""Unit tests for the per-chat /keyword rate limiter (_over_rate_limit).

Dependency-free (stdlib unittest). Run from the repo root:
    .venv/bin/python -m unittest tests.test_rate_limit -v

The limiter persists its state in the `meta` table, reads the clock via
time.time(), and may call send_message(). We give it an in-memory meta table,
a fake clock we control, and a stubbed send_message so the test stays offline
and deterministic.
"""
import sqlite3
import unittest
from unittest.mock import patch

from bot import pipeline
from bot.pipeline import _over_rate_limit, RATE_LIMIT, RATE_WINDOW


def _mem_conn():
    """A throwaway in-memory DB with just the `meta` table _over_rate_limit needs."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
    return conn


class FakeClock:
    """A clock we can advance by hand, standing in for time.time()."""

    def __init__(self, now=1_000):
        self.now = now

    def time(self):
        return self.now


class OverRateLimitTest(unittest.TestCase):
    def setUp(self):
        self.conn = _mem_conn()
        self.addCleanup(self.conn.close)

        self.clock = FakeClock()
        clock_patch = patch.object(pipeline.time, "time", self.clock.time)
        clock_patch.start()
        self.addCleanup(clock_patch.stop)

        # Stub the network send so a warning doesn't hit Telegram; also lets us
        # count exactly how many warnings were emitted.
        send_patch = patch.object(pipeline, "send_message")
        self.send_message = send_patch.start()
        self.addCleanup(send_patch.stop)

    def test_allows_up_to_limit_then_blocks(self):
        chat = "111"
        for i in range(RATE_LIMIT):
            self.assertFalse(
                _over_rate_limit(self.conn, chat),
                f"message {i + 1} of {RATE_LIMIT} should be allowed",
            )
        # The (RATE_LIMIT + 1)th crosses the line...
        self.assertTrue(_over_rate_limit(self.conn, chat))
        # ...and every message after it stays blocked within the same window.
        self.assertTrue(_over_rate_limit(self.conn, chat))

    def test_warns_exactly_once_per_window(self):
        chat = "222"
        for _ in range(RATE_LIMIT + 3):
            _over_rate_limit(self.conn, chat)
        # The warning fires only on the single crossing message (count == LIMIT + 1),
        # not on every blocked message after it.
        self.assertEqual(self.send_message.call_count, 1)

    def test_window_resets_after_it_expires(self):
        chat = "333"
        for _ in range(RATE_LIMIT + 1):          # exhaust the window and cross it
            _over_rate_limit(self.conn, chat)
        self.assertTrue(_over_rate_limit(self.conn, chat))  # still blocked

        self.clock.now += RATE_WINDOW            # jump to the next window
        self.assertFalse(_over_rate_limit(self.conn, chat))  # fresh allowance
        # A new window means a new warning is allowed when it's next crossed.
        self.send_message.reset_mock()
        for _ in range(RATE_LIMIT):
            _over_rate_limit(self.conn, chat)
        self.assertEqual(self.send_message.call_count, 1)

    def test_chats_are_tracked_independently(self):
        # Chat "b" blowing through its limit must not spend chat "a"'s allowance.
        for _ in range(RATE_LIMIT + 2):
            _over_rate_limit(self.conn, "b")
        self.assertFalse(_over_rate_limit(self.conn, "a"))


if __name__ == "__main__":
    unittest.main()