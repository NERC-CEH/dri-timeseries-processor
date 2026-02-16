from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable


def run_threaded_tasks(
    tasks: Iterable,
    func: Callable,
    max_workers: int = 10,
    max_submitted: int = 64,
) -> None:
    """Executes tasks concurrently using multiple threads.

    Args:
        tasks: The tasks to execute.
        func: Function to execute.
        max_workers: Maximum number of threads to use.
        max_submitted: Maximum number of submitted tasks.
    """

    def await_submission_slot(_submitted_tasks: list) -> None:
        """Helper function to wait for any submitted task to complete, propagate any errors, and free one slot.

        Args:
            _submitted_tasks: List of submitted tasks.
        """
        done = next(as_completed(_submitted_tasks))  # get the next finished task
        done.result()  # propagate any potential errors from this task
        _submitted_tasks.remove(done)  # remove it from the submitted tasks so that a new task can be added

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        # Keep track of number of tasks being submitted, otherwise can run into memory issues because each
        # submitted task contains everything it needs in memory and is not garbage-collected until the task
        # executes
        submitted_tasks = []

        # Loop over collection of save tasks to submit to the pool
        for task in tasks:
            submitted_task = pool.submit(func, *task)
            submitted_tasks.append(submitted_task)

            if len(submitted_tasks) >= max_submitted:
                await_submission_slot(submitted_tasks)

        # Tidy up remaining tasks
        for task in as_completed(submitted_tasks):
            task.result()
