# The agent never changes data directly

The ambient agent runs Reviews on its own (on events, month end, or manual trigger), which makes silent mistakes likely and hard to notice in personal financial data. So the agent has no write access to transactions, budgets or goals: every change it wants is a Suggestion that the user accepts (optionally edited), rejects, or lets expire. Rejections are kept and fed back into later Reviews so the agent learns what not to propose.

## Consequences

- Recurring expenses and next month's budgets reach the data only through accepted Suggestions.
- Anything the agent would do "automatically" needs an Inbox entry and a user action, which is slower but auditable.
