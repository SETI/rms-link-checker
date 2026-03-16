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


def test_progress_format(capfd: pytest.CaptureFixture[str]) -> None:
    reporter = ProgressReporter(interval=0.05)
    reporter.update(checked=10, queued=5, active_threads=2, elapsed=30.0)
    reporter._emit()
    captured = capfd.readouterr()
    assert '[Progress]' in captured.err
    assert '10/~15' in captured.err
    assert 'URLs/s' in captured.err
    assert '5 in queue' in captured.err
    assert '2 threads active' in captured.err
    assert '0m 30s elapsed' in captured.err


def test_progress_stop_no_more_output(capfd: pytest.CaptureFixture[str]) -> None:
    reporter = ProgressReporter(interval=0.05)
    reporter.start()
    reporter.stop()
    time.sleep(0.15)
    capfd.readouterr()
    time.sleep(0.15)
    captured2 = capfd.readouterr()
    assert captured2.err.count('[Progress]') == 0


def test_progress_update_values(capfd: pytest.CaptureFixture[str]) -> None:
    reporter = ProgressReporter(interval=60.0)
    reporter.update(checked=42, queued=7, active_threads=3, elapsed=90.5)
    reporter._emit()
    captured = capfd.readouterr()
    assert '42/~49' in captured.err
    assert '7 in queue' in captured.err
    assert '3 threads active' in captured.err
    assert '1m 30s elapsed' in captured.err
