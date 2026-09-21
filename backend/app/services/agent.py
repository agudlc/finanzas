"""
The agent Review: a hand-written tool-use loop, and the one tool it has.

The loop is deliberately small and ours. It sends the system prompt and the
brief its trigger asks for, runs whatever tools the model asks for, sends the
results back, and stops when the model has nothing left to call. There is no
framework under it yet on purpose (root-idea, phase 2b): what a framework would
be doing is meant to be visible first.

The tools are a handful of reads (`agent_tools`), recording an Insight, and
proposing a change (`agent_proposals`). None of them changes anything the user
has recorded: the agent has no write path at all (ADR-0002), and the most a
loop that goes wrong can leave behind is a sentence the user disagrees with and
a proposal they reject. What the reads may reach is the user's call, and the
loop settles it once at the top of the run: everything past the lookback is
refused by the tool rather than fetched. Everything the run leaves behind
beyond the Insights and the Suggestions — the transcript, what it cost, which
prompt asked for it — is written on the Review, so a strange observation can be
read back to the conversation that produced it.

The one thing the loop insists on is ending. It stops after ten turns and keeps
whatever those turns produced, and it asks a busy API again rather than losing a
Review to a 429. Anything else that goes wrong ends the run there and leaves the
error on the Review, because a Review that quietly half-ran is worse than one
that says it failed.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import LLMUnavailable, Reply, ToolCall
from app.models import Review
from app.services import insights as insights_service
from app.services.agent_proposals import (
    KIND_OF,
    TOOLS as PROPOSE_TOOLS,
    Refused,
    propose_through_tool,
)
from app.services.agent_tools import TOOLS as READ_TOOLS, Reading, read
from app.services.brief import brief
from app.services.outside import Outside

# Bumped whenever the system prompt changes, so a run can be read against the
# words that produced it rather than against today's.
PROMPT_VERSION = "2026-09-e"

# The brief is already complete and the tools only fill in around it, so a run
# that has not finished in ten turns is looping rather than working.
MAX_TURNS = 10

# How long a turn waits before asking again when the API says it is busy: two
# waits, so three asks, and then the Review fails with what the API last said.
# Anything that is not the API being busy is not retried at all — a key that is
# missing stays missing, and a request the API refused would be refused again.
RETRY_DELAYS = (1.0, 4.0)

RECORD_INSIGHT = "record_insight"

# What the model writes is the user's to read, so the prompt is where the
# language is decided: English instructions, Spanish output.
SYSTEM_PROMPT = """
You are the coach inside Finanzas, a personal finance app used by one person
living in Argentina. You are given a brief about one month of their money and
you say what you notice about it.

You cannot change anything yourself. You have two ways of saying something.

Record an Insight: a read-only observation that waits in the user's Inbox
during the month it is about. It changes no data.

Or propose a change, with one of the `propose_` tools. Each one is a shape of
change the app knows how to apply; the proposal waits in the Inbox until the
user accepts it, edits it or rejects it, and nothing happens until they do.
Anything you want that no `propose_` tool covers is an Insight instead — say
it as an observation and do not pretend to have done it.

A proposal you make may be refused: the payload is wrong, the change breaks a
rule, or you have proposed it before. The tool says which, and nothing is
stored. Fix it and call the tool again, or drop it and say it as an
observation; do not keep sending the same thing.

The other tools read. The brief already holds the month under review, so reach
for them when a figure in it raises a question — what those Delivery expenses
actually were, how the month compares with the one before it — and not to
gather everything first. The user decides how far back you may read; the brief
says where that floor is, and a tool asked for an older month will tell you so
instead of answering.

How to decide what to say:
- Record an Insight only when you have something specific and useful. Two or
  three is plenty for one month; none at all is a perfectly good answer for a
  quiet month, and better than filling space.
- Propose only what you are sure of and the user would plainly want. A
  proposal is a question they have to answer, so a doubtful one costs them
  more than saying nothing. Recategorize a Transaction only when its
  description makes the right Category obvious and the one it is in wrong.
  Propose a Categorization Rule only for a pattern that has arrived more than
  once and always belongs in the same Category; it files what is imported
  from then on and moves nothing already recorded, so a Transaction sitting
  in the wrong place is a recategorization as well. Propose a Recurring
  Expense only for a charge you can see in several months, and read the
  templates first: one that exists is not proposed again.
- When the brief says an Import has just finished, that is what the run is
  about: go through those Transactions for one filed in the wrong Category,
  for a description that keeps arriving and belongs in a Categorization Rule,
  and for a charge that looks like it comes every month. The rest of the month
  is context for those, not the subject.
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

When you have nothing left to record or propose, answer in one short
sentence and stop calling tools.
""".strip()

RECORD = {
    "name": RECORD_INSIGHT,
    "description": (
        "Record one observation about the month under review. It waits in "
        "the user's Inbox and changes no data. Call it once per observation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": (
                    "A few words naming what this is about, in Spanish, at "
                    "most 100 characters."
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

# What the model is offered: the reads, the one tool that records an
# observation, and one tool per shape of change it may propose.
TOOLS = [RECORD, *PROPOSE_TOOLS, *READ_TOOLS]

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
        {"role": "user", "content": await brief(db, review, outside.clock)}
    ]
    # Settled before the first turn and kept for the whole run: what the tools
    # may read cannot move under the model halfway through a conversation.
    reading = await Reading.of(db, review, outside.clock)

    for _ in range(MAX_TURNS):
        reply = await _ask(outside, messages)
        # Added up across turns, so the input count is the brief once per turn
        # rather than once per run. That is deliberate: this is what the run
        # cost, and every turn is billed for the whole conversation it resends.
        review.input_tokens += reply.input_tokens
        review.output_tokens += reply.output_tokens
        messages.append(reply.as_turn())
        if not reply.tool_calls:
            break
        messages.append(await _results(db, review, reading, reply))
    else:
        review.note = HIT_THE_CAP

    review.transcript = messages


async def _ask(outside: Outside, messages: list[dict]) -> Reply:
    """
    One turn, asked again while the API is only busy.

    A 429 or a 529 says "not now", and the conversation so far is still good:
    the same turn is sent again after waiting, and only when the waits run out
    does the run fail. Every other failure is raised on the first try, because
    the second would fail the same way and the user would wait for nothing.
    """
    waits = iter(RETRY_DELAYS)
    while True:
        try:
            return await outside.llm.reply(SYSTEM_PROMPT, messages, TOOLS)
        except LLMUnavailable as unavailable:
            if not unavailable.transient:
                raise
            delay = next(waits, None)
            if delay is None:
                raise
            await outside.sleep(delay)


@dataclass(frozen=True)
class Answer:
    """
    What one tool said back, and whether it is telling the model it failed.

    The flag is what keeps a refusal from reading like a success. A read that
    answers with the lookback instead of the rows is still an answer; a
    proposal that was refused stored nothing, and the model has to know that
    to either fix it or let it go.
    """

    content: str
    is_error: bool = False

    def block(self, call_id: str) -> dict:
        return {
            "type": "tool_result",
            "tool_use_id": call_id,
            "content": self.content,
            **({"is_error": True} if self.is_error else {}),
        }


async def _results(
    db: AsyncSession, review: Review, reading: Reading, reply: Reply
) -> dict:
    """The user turn that answers every tool the model just called."""
    return {
        "role": "user",
        "content": [
            (await _run_tool(db, review, reading, call)).block(call.id)
            for call in reply.tool_calls
        ],
    }


async def _run_tool(
    db: AsyncSession, review: Review, reading: Reading, call: ToolCall
) -> Answer:
    """
    Do what the model asked, and answer it in a sentence it can act on.

    A tool that cannot be run is answered rather than raised: the model asking
    for something that does not exist, for a month it is not allowed, or for a
    change the app cannot apply is a thing to correct within the run, not a
    reason to lose the Insights and proposals it already got right.
    """
    if call.name == RECORD_INSIGHT:
        return _record(db, review, call.arguments)
    if call.name in KIND_OF:
        return await _propose(db, review, call.name, call.arguments)
    return Answer(await read(reading, call.name, call.arguments))


def _record(db: AsyncSession, review: Review, arguments: dict) -> Answer:
    topic = str(arguments.get("topic") or "").strip()
    body = str(arguments.get("body") or "").strip()
    if not topic or not body:
        return Answer("An Insight needs both a topic and a body.", is_error=True)
    insights_service.record(db, review, topic[:TOPIC_LENGTH], body)
    return Answer("Recorded.")


async def _propose(
    db: AsyncSession, review: Review, name: str, arguments: dict
) -> Answer:
    try:
        await propose_through_tool(db, review, name, arguments)
    except Refused as refusal:
        return Answer(str(refusal), is_error=True)
    return Answer("Proposed. It is waiting in the user's Inbox.")
