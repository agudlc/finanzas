# Every Suggestion and Insight comes from a Review, agent or not

Some Suggestions need no agent: a Recurring Expense's monthly Suggestion and the month-end Budget adjustment are plain arithmetic. Instead of letting those exist outside any Review, a Review is any run that produces Suggestions and Insights, and its trigger says what caused it. Deterministic producers create Reviews too. The Inbox, expiry, deduplication and "what was proposed when" history then have one code path, and adding the agent in 2b adds triggers rather than a second concept.

Deterministic and agent work never share a Review, so "did this Review call the model?" is settled before the run starts and never changes while it goes. It is the Review's own `used_agent` rather than its trigger: a trigger the agent serves can also be the arithmetic standing in for a run that failed, which is how the month-end Budget proposals arrive with no key and no model to ask. Only one of the two ever proposes, because the stand-in is created by the agent run's failure and by nothing else. The agent reads pending Suggestions as input, so it doesn't propose what the arithmetic has already proposed.

## Considered Options

- **Free-standing Suggestions (nullable Review)**: keeps Review meaning "agent run", but gives Suggestions two origins with different lifecycles.
- **A producer field on Suggestion, Review only for the agent**: the same split, only with a label on it.
