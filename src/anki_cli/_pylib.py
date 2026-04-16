"""Helpers for calling the Anki pylib backend without tripping its
'blocked main thread' warning."""

from __future__ import annotations

import concurrent.futures
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def run_off_main(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a pylib call on a worker thread and return its result.

    The Anki Rust backend prints a stack trace whenever a backend call
    blocks the main thread for more than 200 ms. Desktop Anki sidesteps
    this via Qt's worker pool; we use a one-shot executor instead.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(fn, *args, **kwargs).result()
