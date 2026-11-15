"""Site-wide limit on paid model calls (AI answers and uploads).

A hosted public deployment allows at most `daily_limit` paid calls per UTC day and at
least `min_interval_s` seconds between them, across all visitors. State is saved on
disk so restarts do not reset it. Admins are exempt (the caller decides). A limit of 0
means unlimited, which is the default for local use.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str | None = None
    retry_after_s: int = 0
    remaining_today: int | None = None


class PaidCallLimiter:
    def __init__(self, path: Path, *, daily_limit: int = 0, min_interval_s: int = 0):
        if daily_limit < 0 or min_interval_s < 0:
            raise ValueError("Limits must be zero (unlimited) or positive")
        self.path = path
        self.daily_limit = daily_limit
        self.min_interval_s = min_interval_s
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.daily_limit > 0 or self.min_interval_s > 0

    def _load(self, today: str) -> dict[str, Any]:
        try:
            state: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        if state.get("date") != today:
            state = {"date": today, "count": 0, "last": state.get("last", 0.0)}
        return state

    def _save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state), encoding="utf-8")
        temporary.replace(self.path)

    def status(self, now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else now
        today = datetime.fromtimestamp(now, UTC).date().isoformat()
        with self._lock:
            state = self._load(today)
        remaining = max(0, self.daily_limit - state["count"]) if self.daily_limit else None
        wait = max(0, int(state["last"] + self.min_interval_s - now)) if self.min_interval_s else 0
        return {
            "enabled": self.enabled,
            "daily_limit": self.daily_limit or None,
            "remaining_today": remaining,
            "min_interval_s": self.min_interval_s or None,
            "next_available_in_s": wait,
        }

    def refund(self, now: float | None = None) -> None:
        """Give back one call (e.g. the AI request failed); spacing is kept."""
        if not self.daily_limit:
            return
        now = time.time() if now is None else now
        today = datetime.fromtimestamp(now, UTC).date().isoformat()
        with self._lock:
            state = self._load(today)
            if state["count"] > 0:
                state["count"] -= 1
                self._save(state)

    def acquire(self, now: float | None = None) -> Decision:
        """Reserve one paid call if allowed; otherwise explain why and when to retry."""
        if not self.enabled:
            return Decision(True)
        now = time.time() if now is None else now
        moment = datetime.fromtimestamp(now, UTC)
        today = moment.date().isoformat()
        with self._lock:
            state = self._load(today)
            remaining = self.daily_limit - state["count"] if self.daily_limit else None
            if remaining is not None and remaining <= 0:
                midnight = datetime.combine(
                    moment.date() + timedelta(days=1), datetime.min.time(), UTC
                )
                return Decision(
                    False,
                    f"The daily limit of {self.daily_limit} AI answers for this site has been "
                    "reached. Keyword search still works; AI answers resume at 00:00 UTC.",
                    int((midnight - moment).total_seconds()),
                    0,
                )
            wait = state["last"] + self.min_interval_s - now
            if self.min_interval_s and wait > 0:
                return Decision(
                    False,
                    "AI answers are limited to one per minute for this site. "
                    f"Showing keyword results; try again in {int(wait) + 1} s.",
                    int(wait) + 1,
                    remaining,
                )
            state["count"] += 1
            state["last"] = now
            self._save(state)
            return Decision(True, None, 0, None if remaining is None else remaining - 1)
