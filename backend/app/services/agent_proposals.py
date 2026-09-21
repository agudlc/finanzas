"""
The propose tools: how the agent asks for a change instead of making one.

The agent never writes to Transactions, Budgets or anything else. What it can
do is propose, and only one of the kinds the app already knows how to apply
(ADR-0002), so there is exactly one tool here per kind and its input schema is
that kind's own payload with a rationale added. The model fills in the fields
the user will see and can edit, and there is nothing else to fill in: a change
the kinds do not cover is not a tool the model has, it is an Insight.

Nothing a proposal says is taken on trust. It is validated against the kind and
held to the domain rules accepting it would check, and one already made is
refused, so a bad proposal never reaches the Inbox — the model is told what was
wrong and can put it right inside the run. Which is the point of refusing here
rather than at accept time: the user should never be shown a proposal that
would fail the moment they press "Aceptar".
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Review, Suggestion
from app.models.enums import SuggestionKind
from app.services.errors import DomainError
from app.services.kinds import KINDS, Kind
from app.services.suggestions import propose

# What every propose tool is called: the kind, said as a verb. A name the model
# cannot confuse with doing the thing itself.
PREFIX = "propose_"

RATIONALE = "rationale"


class Refused(Exception):
    """The proposal was not stored, and this is what the model is told."""


def _name(kind: SuggestionKind) -> str:
    return f"{PREFIX}{kind.value}"


def _tool(kind: SuggestionKind, definition: Kind) -> dict:
    """
    One kind as a tool: its payload, plus why the user should say yes.

    The schema is the payload model's own, so the tool and the thing the app
    stores can never drift apart — and a field the kind does not name is
    rejected rather than quietly dropped, because the payload forbids extras.
    """
    schema = definition.payload.model_json_schema()
    # The payload model's docstring and title are written for whoever reads the
    # code, not for the model, and the tool has a description of its own.
    schema.pop("description", None)
    schema.pop("title", None)
    schema["properties"][RATIONALE] = {
        "type": "string",
        "description": (
            "Why you are proposing this, in rioplatense Spanish: one or two "
            "sentences, with the figures they rest on. The user reads it next "
            "to the proposal and decides on it."
        ),
    }
    schema["required"] = [*schema.get("required", []), RATIONALE]
    return {
        "name": _name(kind),
        "description": (
            f"{definition.purpose} It changes nothing on its own: it waits in "
            f"the user's Inbox until they accept, edit or reject it."
        ),
        "input_schema": schema,
    }


TOOLS = [_tool(kind, definition) for kind, definition in KINDS.items()]

# The kind behind each tool name, which is also how the loop tells a propose
# call from a read: a name in here is a proposal and nothing else is.
KIND_OF = {_name(kind): kind for kind in KINDS}


async def propose_through_tool(
    db: AsyncSession, review: Review, name: str, arguments: dict
) -> Suggestion:
    """
    Make the proposal the model asked for, or refuse it and say why.

    Refusing stores nothing: everything that could go wrong is settled before
    the Suggestion is added to the session, so a run whose every proposal was
    refused leaves a Review that proposed nothing rather than a half-written
    one.
    """
    payload = dict(arguments)
    rationale = str(payload.pop(RATIONALE, "") or "").strip()
    if not rationale:
        raise Refused(
            "A proposal needs a rationale: one or two sentences the user will "
            "read next to it. Nothing was proposed."
        )
    try:
        suggestion = await propose(
            db, review.id, KIND_OF[name], review.month, payload, rationale
        )
    except DomainError as error:
        raise Refused(
            f"That is not a proposal this app can apply, so nothing was "
            f"proposed: {error.detail}"
        ) from error
    if suggestion is None:
        raise Refused(
            "That exact proposal has already been made, so nothing was "
            "proposed again. It is either waiting in the Inbox or the user "
            "has already answered it."
        )
    return suggestion
