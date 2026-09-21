"""
What a Review cannot work out from the database alone.

The clock, the published inflation series, the model and waiting are the four
things a producer has to be handed rather than do: they are outside the app,
and a test that wants a Review to be about February, with the IPC stale and the
model saying one particular thing, sets all of them here and nowhere else.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.clock import Clock
from app.inflation import IndexProvider
from app.llm import LLMClient

# How the loop waits before asking a busy model again. Real seconds in the
# worker; a test hands in one that records the wait instead of taking it, so
# the backoff can be asserted rather than sat through.
Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class Outside:
    clock: Clock
    indexes: IndexProvider
    llm: LLMClient
    sleep: Sleep = asyncio.sleep
