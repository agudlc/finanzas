# The agent never changes data directly

The ambient agent runs Reviews on its own (on events, month end, or manual trigger), which makes silent mistakes likely and hard to notice in personal financial data. So the agent has no write access to transactions, budgets or goals: every change it wants is a Suggestion that the user accepts (optionally edited), rejects, or lets expire. Rejections are kept and fed back into later Reviews so the agent learns what not to propose.

## Consequences

- Recurring expenses and adjustments to next month's budgets reach the data only through accepted Suggestions. (The plain copy of last month's budgets into a new month is not the agent's doing and stays automatic.)
- Anything the agent would do "automatically" needs an Inbox entry and a user action, which is slower but auditable.
- Suggestion kinds are a closed list, each with a typed payload the app knows how to apply; the model is only offered those kinds. Anything else it wants to say is an Insight.
- Accepting a Suggestion (possibly edited) goes through the same services the API routes use, so the agent has no write path the user lacks and skips no validation.
