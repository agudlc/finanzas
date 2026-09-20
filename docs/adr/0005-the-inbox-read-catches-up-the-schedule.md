# Reading the Inbox catches up the schedule and expires what is stale

The recurring Review is due on the 1st at 06:00 and an ARQ cron starts it. That cron is a single process on a laptop that may well be asleep, so "the worker was down" cannot mean "this month has no proposals". Reading the Inbox therefore creates and enqueues any of the month's scheduled Reviews that don't exist yet, and marks pending Suggestions past their expiry as expired before listing. The cron and the read call the same function, so being on time and being late take one code path.

This is what keeps the app free of a sweeper job. Expiry has no moment it must happen at: a Suggestion nobody looks at is a Suggestion nobody is being misled by, and the read that would show it is the read that retires it first. Accepting checks the date as well, so nothing rests on the sweep having run — the worst a long silence costs is rows that say pending a little longer than they mean it. Nothing outside a request ever has to be running for the data the user sees to be right.

"At most one per trigger per month" is the database's to keep, not the check's: a Review carries the month it is about, and a partial unique index over the scheduled triggers settles a cron and a read that decide at the same moment that the month is missing its Review.

## Considered Options

- **Cron only**: a worker down on the 1st costs the month its Recurring Expense Suggestions, and nothing ever notices.
- **A sweeper job for expiry**: a second scheduled thing that can be down, to keep rows tidy nobody is reading.
- **Expire on write, when a Review runs**: proposals go stale in the Inbox between runs, which is exactly where the user is looking.
