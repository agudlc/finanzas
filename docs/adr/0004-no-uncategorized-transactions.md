# Transactions are never uncategorized; the agent works after an Import, not inside it

The original plan had the agent suggest Categories for "uncategorized imports", but Phase 1 already refuses to confirm an Import until every row has a Category, and the donut, Budgets and Monthly Result all assume every Transaction has one. We keep that invariant. The user categorizes while importing (helped by Categorization Rules), and the Review that follows the Import works on what was just confirmed: it proposes new rules for patterns the user didn't save, and recategorizations for rows that look misfiled. Import stays synchronous and never waits on the model.

## Considered Options

- **Allow uncategorized Transactions and let the agent fill them in**: removes typing at import time, but every view needs a "Sin categoría" bucket and numbers are wrong until the Inbox is cleared.
- **The agent fills categories inside the import preview**: synchronous, slow, and not a Review, so it bypasses Suggestions entirely.
