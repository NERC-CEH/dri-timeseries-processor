import logging

import pytest

import dritimeseriesprocessor.utils.timer as timer


def patch_perf_counter(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, times: tuple[float, float] = (1.0, 10.0)
) -> None:
    caplog.set_level(logging.INFO, logger=timer.logger.name)
    times = iter(times)
    monkeypatch.setattr(timer.time, "perf_counter", lambda: next(times))


def get_caplog_messages(caplog_records: list) -> list:
    return [r.getMessage() for r in caplog_records]


class TestElapsedTimer:
    def test_logs_elapsed_time(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        patch_perf_counter(monkeypatch, caplog)
        with timer.ElapsedTimer("Time taken") as t:
            pass

        assert t.elapsed == 9.0

        messages = get_caplog_messages(caplog.records)
        assert len(messages) == 1
        assert messages[0] == "Time taken: 9.00 seconds"

    def test_header(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        patch_perf_counter(monkeypatch, caplog)
        with timer.ElapsedTimer("Time taken", header=True, separator="---") as t:
            pass

        assert t.elapsed == 9.0

        messages = get_caplog_messages(caplog.records)
        assert len(messages) == 2
        assert messages[0] == "---"
        assert messages[1] == "Time taken: 9.00 seconds"

    def test_footer(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        patch_perf_counter(monkeypatch, caplog)
        with timer.ElapsedTimer("Time taken", footer=True, separator="---") as t:
            pass

        assert t.elapsed == 9.0

        messages = get_caplog_messages(caplog.records)
        assert len(messages) == 2
        assert messages[0] == "Time taken: 9.00 seconds"
        assert messages[1] == "---"

    def test_header_and_footer(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        patch_perf_counter(monkeypatch, caplog)
        with timer.ElapsedTimer("Time taken", header=True, footer=True, separator="---") as t:
            pass

        assert t.elapsed == 9.0

        messages = get_caplog_messages(caplog.records)
        assert len(messages) == 3
        assert messages[0] == "---"
        assert messages[1] == "Time taken: 9.00 seconds"
        assert messages[2] == "---"

    def test_function_exceptions(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        patch_perf_counter(monkeypatch, caplog)
        with pytest.raises(ValueError):
            with timer.ElapsedTimer("Time taken"):
                raise ValueError

        messages = get_caplog_messages(caplog.records)
        assert len(messages) == 1
        assert messages[0] == "Time taken: 9.00 seconds"


class TestLogDuration:
    def test_decorator_logs_duration(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        patch_perf_counter(monkeypatch, caplog)

        @timer.log_duration("Time taken")
        def temp() -> None:
            return

        temp()

        messages = get_caplog_messages(caplog.records)
        assert len(messages) == 1
        assert messages[0] == "Time taken: 9.00 seconds"

    def test_decorator_header_footer(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        patch_perf_counter(monkeypatch, caplog)

        @timer.log_duration("Time taken", header=True, footer=True, separator="---")
        def temp() -> None:
            return

        temp()

        messages = get_caplog_messages(caplog.records)
        assert len(messages) == 3
        assert messages[0] == "---"
        assert messages[1] == "Time taken: 9.00 seconds"
        assert messages[2] == "---"
