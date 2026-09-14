# Finanzas

A personal finance coach for a single user living in Argentina: it records how money flows in and out across ARS and USD, holds that flow against budgets and savings goals, and runs an ambient agent that reviews the data and proposes improvements.

## Language

### Money flow

**Transaction**:
A single recorded movement of money in or out, either an Expense or an Income, on a given date.
_Avoid_: Movement, entry, record

**Expense**:
A Transaction where money leaves.
_Avoid_: Spend, cost, outflow

**Income**:
A Transaction where money arrives.
_Avoid_: Earning, inflow, source

**Category**:
A label that classifies Transactions. It has a type: an expense Category can only classify Expenses, and an income Category only Incomes.
_Avoid_: Tag, source (for Income)

**Default Category**:
A Category the app ships with (e.g. Supermercado, Delivery, Alquiler; Sueldo, Rendimientos). Users can edit or remove it like any other. Yields from a Mercado Pago balance are Income in "Rendimientos".
_Avoid_: System category, built-in

**Categorization Rule**:
A mapping "description contains X → Category Y" that assigns Categories to imported Transactions. Rules are learned from the user's manual choices and from accepted Suggestions.
_Avoid_: Mapping, filter, auto-tag

**Import**:
Bulk-loading Transactions from a bank or fintech export. CSV/XLSX files are read through an Import Profile; PDF statements are read by the agent and become Suggestions. Rows matching an existing Transaction (same date, amount and description) are skipped and shown to the user.
_Avoid_: Upload, sync

**Import Profile**:
The saved settings for reading exports from one source (e.g. Mercado Pago, Lemon): column mapping, date and number formats, and sign convention.
_Avoid_: Parser, template, bank config

**Refund**:
An Expense with a negative amount, in the same Category as the purchase it reverses and linked to it when known. It is never an Income, and the original Expense is never deleted.
_Avoid_: Reimbursement, return, chargeback

**Installment Purchase**:
A purchase paid in cuotas (e.g. 600k in 6). It creates one Expense per cuota, the first in the purchase month and one per month after, so Budgets see the monthly share and remaining cuotas show future commitments. Each cuota's amount (and Exchange Rate, if in USD) starts as an estimate and is confirmed when the statement or Import arrives.
_Avoid_: Cuotas (as a model name), financing, loan

**Fixed Expense**:
An Expense the user considers unavoidable (rent, bills, taxes).
_Avoid_: Mandatory expense

**Monthly Result**:
Total Income minus total Expenses for a month. It describes flow, not how much money the user holds.
_Avoid_: Balance, net balance, net worth

### Currency

**Original Amount**:
The amount and currency (ARS or USD) in which a Transaction actually happened.
_Avoid_: Raw amount

**Exchange Rate**:
The ARS-per-USD rate stored on a USD Transaction, with its rate type (blue, MEP, card...). It is filled in automatically as an estimate and can be replaced by the confirmed figure (e.g. from the card statement); once confirmed it never changes.
_Avoid_: Current rate, conversion

**Display Currency**:
The single currency (ARS by default) in which Monthly Results and Budgets are shown, converted through each Transaction's stored Exchange Rate.
_Avoid_: Currency toggle, base currency

Buying or selling dollars or crypto is not recorded: without accounts it is neither Income nor Expense. Crypto never appears as a currency; a card purchase paid from a crypto balance is an Expense in the currency charged, and crypto cashback is ignored.

### Planning

**Budget**:
A spending limit for one expense Category in one month. Going over it is shown loudly, never blocked. Next month's Budgets come from the month-end Review as Suggestions (inflation and actual spending in mind), or are copied unchanged when no Review exists.
_Avoid_: Limit, cap

**Pace**:
The share of a Budget that "should" be spent by a given day of the month. Budget progress is judged against Pace, and warnings escalate at 80% and 100% of the Budget; crossing 100% triggers a Review.
_Avoid_: Burn rate, expected spend

**Goal**:
A named savings target with a target amount and an optional deadline.
_Avoid_: Objective, savings account

**Contribution**:
Money the user sets aside toward one Goal on a date, in the Goal's currency. A Goal's progress is the sum of its Contributions. It is not an Expense and does not change the Monthly Result.
_Avoid_: Deposit, current amount, savings expense

**Recurring Expense**:
A template for an Expense expected every month (Category, expected day, reference amount). It never creates Transactions directly; each month it produces a Suggestion. The suggested amount is the last amount actually paid, unless the template has an Adjustment Rule.
_Avoid_: Fixed expense (that is a flag on a Transaction), subscription

**Adjustment Rule**:
An optional rule on a Recurring Expense saying how its amount changes over time: every N months by a fixed percentage or by an index (e.g. IPC), as in a rent contract.
_Avoid_: Indexation, update rule

### Agent

**Review**:
One run of the agent over the user's data. It starts either from an event (import finished, Budget threshold crossed, month end) or manually by the user.
_Avoid_: Job, analysis, scan

**Insight**:
A read-only observation the agent produces during a Review. It changes no data. The user can dismiss it; it leaves the Inbox after the next month-end Review but stays as history later Reviews can read.
_Avoid_: Tip, alert, notification

**Suggestion**:
A change the agent proposes (for example recategorizing a Transaction). It is pending until the user accepts it (possibly after editing), rejects it (optionally with a reason), or it expires. Rejections are remembered and inform later Reviews.
_Avoid_: Recommendation, action

**Inbox**:
The place where pending Suggestions and recent Insights wait for the user. Chat is a secondary way to discuss them.
_Avoid_: Feed, notifications, coach
