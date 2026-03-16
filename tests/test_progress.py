"""Tests for progress module."""

from __future__ import annotations

import time

import pytest

from link_checker.progress import ProgressReporter


def test_progress_emits_to_stderr(capfd: pytest.CaptureFixture[str]) -> None:
    reporter = ProgressReporter(interval=0.05)
    reporter.start()
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if '[Progress]' in capfd.readouterr().err:
                break
            time.sleep(0.01)
        else:
            pytest.fail('ProgressReporter did not emit within 2 seconds')
    finally:
        reporter.stop()


@pytest.mark.parametrize(
    ('checked', 'queued', 'active_threads', 'elapsed', 'expected_fragments'),
    [
        # Basic formatting: elapsed under 60 s, minute portion is '0m'.
        (10, 5, 2, 30.0, ['10/~15', 'URLs/s', '5 in queue', '2 threads active', '0m 30s elapsed']),
        # Minute-boundary: 90.5 s formats as '1m 30s'.
        (42, 7, 3, 90.5, ['42/~49', '7 in queue', '3 threads active', '1m 30s elapsed']),
    ],
)
def test_progress_format(
    capfd: pytest.CaptureFixture[str],
    checked: int,
    queued: int,
    active_threads: int,
    elapsed: float,
    expected_fragments: list[str],
) -> None:
    """Progress line must contain the correct formatted fields for given inputs."""
    reporter = ProgressReporter(interval=0.05)
    reporter.update(checked=checked, queued=queued, active_threads=active_threads, elapsed=elapsed)
    reporter._emit()
    captured = capfd.readouterr()
    for fragment in expected_fragments:
        assert fragment in captured.err
    reporter = ProgressReporter(interval=0.05)
    reporter.start()
    reporter.stop()
    time.sleep(0.15)
    capfd.readouterr()
    time.sleep(0.15)
    captured2 = capfd.readouterr()
    assert captured2.err.count('[Progress]') == 0
