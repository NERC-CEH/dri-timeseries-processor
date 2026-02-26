import time
from unittest.mock import MagicMock

import pytest

from dritimeseriesprocessor.utils.task_pool import run_threaded_tasks


class TestRunThreadedTasks:
    def test_executes_all_tasks(self) -> None:
        """Test that all tasks are executed with correct arguments."""
        mock_func = MagicMock()
        tasks = [(1, "a"), (2, "b"), (3, "c")]

        run_threaded_tasks(tasks, mock_func)

        assert mock_func.call_count == 3
        mock_func.assert_any_call(1, "a")
        mock_func.assert_any_call(2, "b")
        mock_func.assert_any_call(3, "c")

    def test_propagates_exceptions(self) -> None:
        """Test that exceptions from tasks are propagated."""

        def failing_func(*args) -> None:
            if args[0] == 2:
                raise ValueError("Test error")

        tasks = [(1,), (2,), (3,)]
        with pytest.raises(ValueError):
            run_threaded_tasks(tasks, failing_func)

    def test_empty_task_list(self) -> None:
        """Test that empty task list is handled correctly."""
        mock_func = MagicMock()
        tasks = []
        run_threaded_tasks(tasks, mock_func)
        mock_func.assert_not_called()

    def test_single_task(self) -> None:
        """Test single task."""
        mock_func = MagicMock(return_value="result")
        tasks = [(1, "a")]
        run_threaded_tasks(tasks, mock_func)
        mock_func.assert_called_once_with(1, "a")

    def test_concurrent_execution(self) -> None:
        """Test that tasks actually run concurrently."""
        mock_func = MagicMock()

        def timed_func(*args) -> None:
            mock_func()
            time.sleep(0.2)

        tasks = [(i,) for i in range(5)]

        start = time.time()
        run_threaded_tasks(tasks, timed_func, max_workers=5)
        duration = time.time() - start

        # Total time taken should be ~0.2s with concurrency, not 1s sequentially
        assert abs(duration - 0.2) < 0.1
        assert mock_func.call_count == 5

    def test_concurrent_execution_with_max_submitted_limit(self) -> None:
        """Test that tasks actually run concurrently."""
        mock_func = MagicMock()

        def timed_func(*args) -> None:
            mock_func()
            time.sleep(0.2)

        tasks = [(i,) for i in range(5)]

        start = time.time()
        run_threaded_tasks(tasks, timed_func, max_submitted=2)
        duration = time.time() - start

        # Should limit number of submitted jobs to 2 at a time, so has 3 sets of concurrences to process 5 jobs
        # Total time taken should be ~0.2 * 3 = 0.6s with concurrency, not 1s sequentially
        assert abs(duration - 0.6) < 0.1
        assert mock_func.call_count == 5

    def test_concurrent_execution_with_max_workers_limit(self) -> None:
        """Test that tasks actually run concurrently."""
        mock_func = MagicMock()

        def timed_func(*args) -> None:
            mock_func()
            time.sleep(0.2)

        tasks = [(i,) for i in range(5)]

        start = time.time()
        run_threaded_tasks(tasks, timed_func, max_workers=2)
        duration = time.time() - start

        # Should limit number of workers to 2 at a time, so has 3 sets of concurrences to process 5 jobs
        # Total time taken should be ~0.2 * 3 = 0.6s with concurrency, not 1s sequentially
        assert abs(duration - 0.6) < 0.1
        assert mock_func.call_count == 5
