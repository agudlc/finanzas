"""
The agent Review: a hand-written tool-use loop, and the one tool it has.

The loop is deliberately small and ours. It sends the system prompt and the
core brief, runs whatever tools the model asks for, sends the results back, and
stops when the model has nothing left to call. There is no framework under it
yet on purpose (root-idea, phase 2b): what a framework would be doing is meant
to be visible first.

The only tool so far is recording an Insight, which changes no data — the agent
has no write path at all (ADR-0002), so a loop that goes wrong costs the user a
sentence they disagree with and nothing else. Everything the run leaves behind
beyond the Insights — the transcript, what it cost, which prompt asked for it —
is written on the Review, so a strange observation can be read back to the
conversation that produced it.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import Reply, ToolCall
from app.models import Review
from app.services import insights as insights_service
from app.services.brief import core_brief
from app.services.outside import Outside

# Bumped whenever the system prompt changes, so a run can be read against the
# words that produced it rather than against today's.
PROMPT_VERSION = "2026-09-a"

# The model has one tool and a brief that is already complete, so a run that
# has not finished in ten turns is looping rather than working.
MAX_TURNS = 10

RECORD_INSIGHT = "record_insight"

# What the model writes is the user's to read, so the prompt is where the
# language is decided: English instructions, Spanish output.
SYSTEM_PROMPT = """
You are the coach inside Finanzas, a personal finance app used by one person
living in Argentina. You are given a brief about one month of their money and
you say what you notice about it.

You cannot change anything. Your only tool records an Insight: a read-only
observation that waits in the user's Inbox during the month it is about. If
something would need data to change, say it as an observation anyway — do not
pretend to have done it.

How to decide what to say:
- Record an Insight only when you have something specific and useful. Two or
  three is plenty for one month; none at all is a perfectly good answer for a
  quiet month, and better than filling space.
- Point at the numbers in the brief. "Gastaste 120.000 en Delivery, 40% más que
  el límite" is worth saying; "cuidado con los gastos" is not.
- Do not repeat an observation already recorded in the last two months, and do
  not restate a proposal already waiting in the Inbox.
- Take the rejections seriously: the user has already said no to those, so do
  not push them again.
- Never invent a figure. If the brief does not say it, you do not know it.

How to write:
- Rioplatense Spanish, voseo, direct and factual. No greetings, no
  cheerleading, no moralising, no emoji.
- The topic is a few words. The body is one short paragraph.
- Amounts as the app writes them: 475.946,65.

When you have nothing left to record, answer in one short sentence and stop
calling tools.
""".strip()

TOOLS = [
    {
        "name": RECORD_INSIGHT,
        "description": (
            "Record one observation about the month under review. It waits in "
            "the user's Inbox and changes no data. Call it once per "
            "observation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": (
                        "A few words naming what this is about, in Spanish, "
                        "at most 100 characters."
                    ),
                },
                "body": {
                    "type": "string",
                    "description": (
                        "The observation itself, in rioplatense Spanish: one "
                        "short paragraph, with the figures it rests on."
                    ),
                },
            },
            "required": ["topic", "body"],
        },
    }
]

# What the Review says about itself when the model kept calling tools past the
# cap. The run is not a failure: whatever it recorded before the cap stands.
HIT_THE_CAP = "hit the iteration cap"

# Insight.topic is 100 characters, and a model that writes a longer one has
# written a body by mistake; cutting is friendlier than failing the whole run.
TOPIC_LENGTH = 100


async def review_with_agent(
    db: AsyncSession, review: Review, outside: Outside
) -> None:
    """
    Run the loop for this Review, and leave on it everything it did.

    Nothing is committed here. The Insights and the Review's own record of the
    run land in the one commit `run_review` makes, so a turn that raises
    halfway leaves no half-read month behind.
    """
    review.prompt_version = PROMPT_VERSION
    review.input_tokens = 0
    review.output_tokens = 0
    messages: list[dict] = [
        {"role": "user", "content": await core_brief(db, review, outside.clock)}
    ]

    for _ in range(MAX_TURNS):
        reply = await outside.llm.reply(SYSTEM_PROMPT, messages, TOOLS)
        # Added up across turns, so the input count is the brief once per turn
        # rather than once per run. That is deliberate: this is what the run
        # cost, and every turn is billed for the whole conversation it resends.
        review.input_tokens += reply.input_tokens
        review.output_tokens += reply.output_tokens
        messages.append(reply.as_turn())
        if not reply.tool_calls:
            break
        messages.append(_results(db, review, reply))
    else:
        review.note = HIT_THE_CAP

    review.transcript = messages


def _results(db: AsyncSession, review: Review, reply: Reply) -> dict:
    """The user turn that answers every tool the model just called."""
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": _run_tool(db, review, call),
            }
            for call in reply.tool_calls
        ],
    }


def _run_tool(db: AsyncSession, review: Review, call: ToolCall) -> str:
    """
    Do what the model asked, and answer it in a sentence it can act on.

    A tool that cannot be run is answered rather than raised: the model asking
    for something that does not exist is a thing to correct within the run, not
    a reason to lose the Insights it already recorded.
    """
    if call.name != RECORD_INSIGHT:
        return f"There is no tool called {call.name}."
    topic = str(call.arguments.get("topic") or "").strip()
    body = str(call.arguments.get("body") or "").strip()
    if not topic or not body:
        return "An Insight needs both a topic and a body."
    insights_service.record(db, review, topic[:TOPIC_LENGTH], body)
    return "Recorded."
