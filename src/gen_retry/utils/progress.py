"""Small stdout progress meter with elapsed time and ETA."""

from __future__ import annotations

import sys
import time
from typing import TextIO


class ProgressMeter:
    """Print coarse-grained total progress for long-running local jobs."""

    def __init__(
        self,
        total: int,
        *,
        label: str,
        update_interval: float = 30.0,
        width: int = 28,
        stream: TextIO | None = None,
    ) -> None:
        self.total = max(0, int(total))
        self.label = label
        self.update_interval = max(0.0, float(update_interval))
        self.width = max(10, int(width))
        self.stream = stream or sys.stdout
        self.started_at = time.time()
        self.last_printed_at = 0.0
        self.completed = 0

    def update(
        self,
        *,
        completed: int | None = None,
        increment: int = 1,
        force: bool = False,
        extra: str = "",
    ) -> None:
        if completed is None:
            self.completed += increment
        else:
            self.completed = int(completed)
        if self.total:
            self.completed = min(max(0, self.completed), self.total)
        else:
            self.completed = max(0, self.completed)

        now = time.time()
        should_print = force or self.completed >= self.total
        should_print = should_print or (now - self.last_printed_at >= self.update_interval)
        if not should_print:
            return
        self.last_printed_at = now
        print(self.render(extra=extra), file=self.stream, flush=True)

    def render(self, *, extra: str = "") -> str:
        elapsed = max(0.0, time.time() - self.started_at)
        rate = self.completed / elapsed if elapsed > 0 else 0.0
        percent = (self.completed / self.total * 100.0) if self.total else 100.0
        filled = int(round(self.width * percent / 100.0)) if self.total else self.width
        filled = min(self.width, max(0, filled))
        bar = "#" * filled + "-" * (self.width - filled)
        eta = _format_duration((self.total - self.completed) / rate) if rate > 0 and self.total else "unknown"
        suffix = f" {extra}" if extra else ""
        return (
            f"[{self.label}] [{bar}] {self.completed}/{self.total} "
            f"{percent:5.1f}% elapsed={_format_duration(elapsed)} eta={eta} "
            f"rate={rate:.3f}/s{suffix}"
        )


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days:
        return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
