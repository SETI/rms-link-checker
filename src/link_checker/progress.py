"""Periodic stderr progress reporting during crawl."""

from __future__ import annotations

import sys
import threading
import time


class ProgressReporter:
    """Emits periodic progress updates to stderr.

    Updates are written approximately every *interval* seconds.

    Args:
        interval: Time in seconds between progress updates.
    """

    def __init__(self, interval: float = 5.0) -> None:
        """Initialise the reporter.

        Args:
            interval: Seconds between automatic updates.
        """
        self._interval = interval
        self._checked = 0
        self._queued = 0
        self._active_threads = 0
        self._elapsed = 0.0
        self._stopped = False
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def update(
        self,
        *,
        checked: int,
        queued: int,
        active_threads: int,
        elapsed: float,
    ) -> None:
        """Update the current progress values.

        Args:
            checked: Number of URLs checked so far.
            queued: Number of URLs currently in queue.
            active_threads: Number of active worker threads.
            elapsed: Elapsed time in seconds.
        """
        with self._lock:
            self._checked = checked
            self._queued = queued
            self._active_threads = active_threads
            self._elapsed = elapsed

    def _emit(self) -> None:
        """Write a single progress line to stderr."""
        with self._lock:
            checked = self._checked
            queued = self._queued
            threads = self._active_threads
            elapsed = self._elapsed

        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        estimate = checked + queued
        line = (
            f'[Progress] {checked}/~{estimate} URLs checked'
            f' | {queued} in queue'
            f' | {threads} threads active'
            f' | {minutes}m {seconds}s elapsed'
        )
        print(line, file=sys.stderr, flush=True)

    def _schedule(self) -> None:
        if self._stopped:
            return
        self._emit()
        self._timer = threading.Timer(self._interval, self._schedule)
        self._timer.daemon = True
        self._timer.start()

    def start(self) -> None:
        """Start emitting periodic progress updates."""
        self._stopped = False
        self._timer = threading.Timer(self._interval, self._schedule)
        self._timer.daemon = True
        self._timer.start()

    def stop(self) -> None:
        """Stop emitting progress updates."""
        self._stopped = True
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
