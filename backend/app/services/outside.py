"""
What a Review cannot work out from the database alone.

The clock, the published inflation series and the model are the three things a
producer has to be handed rather than read: they are outside the app, and a
test that wants a Review to be about February, with the IPC stale and the model
saying one particular thing, sets all three here and nowhere else.
"""

from dataclasses import dataclass

from app.clock import Clock
from app.inflation import IndexProvider
from app.llm import LLMClient


@dataclass(frozen=True)
class Outside:
    clock: Clock
    indexes: IndexProvider
    llm: LLMClient
