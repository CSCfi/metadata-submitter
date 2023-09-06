"""Decorator for function retry call."""
# Copyright 2021 Fabian Bosler https://gist.github.com/FBosler/be10229aba491a8c912e3a1543bbc74e

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
# Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
# OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, Optional, TypeVar

from aiohttp import ClientConnectorError
from aiohttp.web import HTTPServerError
from typing_extensions import ParamSpec

from ..helpers.logger import LOG

T = TypeVar("T")
P = ParamSpec("P")


def retry(
    exceptions: tuple[Any, Any] = (HTTPServerError, ClientConnectorError),
    total_tries: int = 4,
    initial_wait: float = 0.5,
    backoff_factor: int = 2,
) -> Callable:  # type: ignore
    """Call the decorated function and apply an exponential backoff.

    :param exceptions: Exception(s) that trigger a retry, can be a tuple
    :param total_tries: Total tries
    :param initial_wait: Time to first retry
    :param backoff_factor: Backoff multiplier (e.g. value of 2 will double the delay each retry).
    """

    def retry_decorator(f: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[Optional[T]]]:
        @wraps(f)
        async def func_with_retries(*args: P.args, **kwargs: P.kwargs) -> Optional[T]:
            _tries, _delay = total_tries, initial_wait
            while _tries > 1:
                try:
                    LOG.debug("Function: %s {total_tries + 1 - _tries}. try", f.__name__)
                    return await f(*args, **kwargs)
                except exceptions as e:
                    _tries -= 1
                    print_args = args if args else "no args"
                    if _tries == 1:
                        msg = str(
                            f"Function: {f.__name__} failed after {total_tries} tries. "
                            f"args: {print_args}, kwargs: {kwargs}"
                        )
                        LOG.exception(msg)
                        raise
                    msg = str(
                        f"Function: {f.__name__}, Exception: {e}\n"
                        f"Retrying in {_delay} seconds!, args: {print_args}, kwargs: {kwargs}\n"
                    )
                    LOG.debug(msg)
                    time.sleep(_delay)
                    _delay *= backoff_factor

            return None

        return func_with_retries

    return retry_decorator
