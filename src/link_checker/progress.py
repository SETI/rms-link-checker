"""Periodic stderr progress reporting during crawl."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable


class ProgressReporter:
    """Emits periodic progress updates to stderr.

    Updates are written approximately every *interval* seconds.

    Parameters:
        interval: Time in seconds between progress updates.
        output: Callable that accepts a string and writes it somewhere.
            Defaults to printing to :data:`sys.stderr`.
    """

    def __init__(
        self,
        interval: float = 5.0,
        output: Callable[[str], None] | None = None,
    ) -> None:
        """Initialise the reporter.

        Parameters:
            interval: Seconds between automatic updates.
            output: Optional callable for writing progress lines.  Defaults to
                printing to :data:`sys.stderr` with flushing.
        """
        self._interval = interval
        self._output: Callable[[str], None] = (
            output if output is not None else lambda line: print(line, file=sys.stderr, flush=True)
        )
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

        Parameters:
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
        self._emit_unlocked(checked=checked, queued=queued, threads=threads, elapsed=elapsed)

    def _emit_unlocked(self, *, checked: int, queued: int, threads: int, elapsed: float) -> None:
        """Write a progress line using already-captured values (no locking)."""
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        estimate = checked + queued
        urls_per_sec = checked / elapsed if elapsed > 0 else 0.0
        line = (
            f'[Progress] {checked}/~{estimate} URLs checked'
            f' | {urls_per_sec:.1f} URLs/s'
            f' | {queued} in queue'
            f' | {threads} threads active'
            f' | {minutes}m {seconds}s elapsed'
        )
        self._output(line)

    def _schedule(self) -> None:
        """Emit one progress line and schedule the next emission.

        Called by the periodic :class:`~threading.Timer`.  Re-arms the timer
        unless :meth:`stop` has been called.  All state access is protected by
        :attr:`_lock` to avoid races with :meth:`stop`.
        """
        with self._lock:
            if self._stopped:
                return
            checked = self._checked
            queued = self._queued
            threads = self._active_threads
            elapsed = self._elapsed
            self._timer = threading.Timer(self._interval, self._schedule)
            self._timer.daemon = True
            self._timer.start()
        self._emit_unlocked(checked=checked, queued=queued, threads=threads, elapsed=elapsed)

    def start(self) -> None:
        """Start emitting periodic progress updates."""
        with self._lock:
            self._stopped = False
            self._timer = threading.Timer(self._interval, self._schedule)
            self._timer.daemon = True
            self._timer.start()

    def stop(self) -> None:
        """Stop emitting progress updates."""
        with self._lock:
            self._stopped = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
