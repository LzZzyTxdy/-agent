"""Small bounded exponential-backoff helper."""

import time
from typing import Callable, Iterable, Type, TypeVar

T = TypeVar("T")


def retry_call(
    operation: Callable[[], T],
    attempts: int,
    retry_on: Iterable[Type[BaseException]],
    base_delay: float = 1.0,
) -> T:
    """Run operation with delays base_delay, 2*base_delay, 4*base_delay."""
    accepted = tuple(retry_on)
    last_error: BaseException
    for attempt in range(attempts):
        try:
            return operation()
        except accepted as exc:
            last_error = exc
            if attempt + 1 >= attempts:
                raise
            time.sleep(base_delay * (2**attempt))
    raise last_error  # pragma: no cover
