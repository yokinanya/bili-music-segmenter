"""Bounded scan submission that drains running work before surfacing errors."""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextvars import copy_context


def scan_windows(windows: list, worker, concurrency: int) -> list:
    queued, results = iter(enumerate(windows, 1)), {}
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        active = {}
        for _ in range(concurrency):
            _submit(executor, active, queued, worker)
        while active:
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            errors = [future.exception() for future in done if future.exception() is not None]
            for future in done:
                index = active.pop(future)
                if future.exception() is None:
                    results[index] = future.result()
            if errors:
                for future in active:
                    future.cancel()
                raise errors[0]
            for _ in done:
                _submit(executor, active, queued, worker)
    return [results[index] for index in sorted(results)]


def _submit(executor, active: dict, queued, worker) -> None:
    item = next(queued, None)
    if item is not None:
        active[executor.submit(copy_context().run, worker, item)] = item[0]
