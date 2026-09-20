# Finanzas — Project Documentation
 
> A personal finance coach web app built for the Argentine reality.
> Tracks how money flows in and out across ARS and USD, holds that flow against budgets and goals,
> and runs an ambient agent that reviews your data and proposes improvements for you to accept.
 
Domain vocabulary lives in [`CONTEXT.md`](./CONTEXT.md); hard-to-reverse decisions live in [`docs/adr/`](./docs/adr/). When this document and those disagree, they win.
 
---
 
## What this is
 
A desktop-first personal finance webapp built primarily for personal use and open-sourced so others can self-host their own instance. It is not a SaaS product — there are no accounts, no branding, no onboarding flows. It is designed to be minimal, snappy, and data-forward.
 
It is also a study project: learning Python (FastAPI), modern React, and **ambient agents** — agents that run on events and schedules, not only when you chat with them. The rule for balancing both goals: **build a useful core first, then let learning drive the later phases.** Real data has to exist before an agent is worth pointing at it.
 
---
 
## The problem it solves
 
Argentina's fintech ecosystem makes it very hard to get programmatic access to your own financial data. Banks and fintechs are hostile to automation, multiple dollar rates coexist (official, blue, MEP, CCL, card), purchases are routinely split into cuotas, and inflation makes both historical comparisons and fixed monthly amounts misleading. Most personal finance apps are built for stable single-currency economies and fail here.
 
This app starts from that reality: manual entry and file import (Mercado Pago, Lemon) are the data sources, every USD transaction keeps the exchange rate it actually happened at, and inflation is taken into account when recurring amounts and budgets are proposed.
 
---
 
## Design principles
 
- **No chrome** — no header, no footer, no avatar, no username display. The OS and browser handle that.
- **Data is the UI** — color and typography do the visual separation, not cards and borders.
- **Shame over blocking** — budgets are enforced through radical visibility, not hard limits.
- **The agent proposes, the user decides** — the agent never changes data directly; everything goes through Suggestions (ADR-0002).
- **Honest history** — past numbers never change because today's dollar rate changed (ADR-0001).
- **Desktop-first** — designed for a 1280px+ browser viewport. Mobile is a future iteration.
- **One user** — no multi-tenancy, no auth complexity in early phases. Built for yourself.
- **Spanish UI, English code** — the UI and the agent speak Spanish; code and domain names are in English.
- **Phases over perfection** — each phase ships something real and useful before adding complexity.
---
 
## Domain at a glance
 
See `CONTEXT.md` for precise definitions. The essentials:
 
- **Money flow only, no Accounts (yet).** The app records Transactions (Expenses and Incomes), not where money is held. The headline number is the **Monthly Result** (income − expenses), not a balance.
- **Not recorded:** buying or selling dollars or crypto — without Accounts it is neither income nor expense. A card purchase paid from a crypto balance is an Expense in the currency charged; crypto cashback is ignored.
- **Currencies:** ARS and USD. Every USD Transaction stores an **Exchange Rate** with its rate type, first **estimated** (dolarapi.com) and later **confirmed** (e.g. from the card statement). Everything is shown in one **Display Currency** (ARS by default) using those stored rates.
- **Categories are typed:** expense Categories only classify Expenses, income Categories only Incomes. The app ships editable **Default Categories**.
- **Refunds** are negative Expenses in the original Category, never Income.
- **Installment Purchases** (cuotas) create one Expense per month starting in the purchase month; each cuota is an estimate until the statement or import confirms it.
- **Budgets** are per Category per month, judged against **Pace** (how much "should" be spent by today), escalating at 80% and 100%.
- **Goals** progress through **Contributions**. A Contribution is not an Expense and does not change the Monthly Result.
- **Recurring Expenses** are templates that produce a monthly Suggestion — amount = last amount paid, or an **Adjustment Rule** (every N months by % or by IPC) for contract-indexed costs like rent.
- **Agent:** a **Review** is one run that produces **Suggestions** (pending → accepted, possibly edited / rejected with optional reason / expired) and **Insights** (read-only observations, shown during their month, kept as history). Some Reviews run the agent, others are plain arithmetic (ADR-0003). Both wait in the **Inbox**. Rejections and past Insights feed later Reviews.
 
---
 
## User stories
 
### Expense & income tracking
- As a user I want to log daily expenses quickly with amount, category, currency and an optional note
- As a user I want to log income entries with an income category, amount and currency
- As a user I want to see what I already entered today when I open the app
- As a user I want to tag expenses as fixed (rent, bills, taxes) so I can distinguish unavoidable costs
- As a user I want to record a purchase in cuotas once and see each monthly cuota land in its month
- As a user I want to record a refund so the category's spending reflects what I really spent
### Import
- As a user I want to import my Mercado Pago and Lemon exports so I don't type months of history by hand
- As a user I want the app to remember how to read each source's file (Import Profile)
- As a user I want imported rows categorized automatically by rules learned from my past choices
- As a user I want re-importing an overlapping period to skip duplicates and show me what was skipped
- As a user I want PDF-only statements read by the agent and turned into Suggestions I can accept
### Currency
- As a user I want to record expenses in ARS or USD
- As a user I want USD transactions to get an estimated rate automatically and let me confirm the real one later
- As a user I want all totals in one display currency, never mixing ARS and USD misleadingly
### Budgets
- As a user I want to set a monthly budget per category
- As a user I want the app to make it very visible and uncomfortable when I'm ahead of pace or over budget — shame me with data, not block me
- As a user I want to see budget progress at a glance on the main dashboard
- As a user I want next month's budgets proposed from what I actually spent and inflation, not copied blindly
### Recurring expenses
- As a user I want to define recurring expenses once and get a monthly suggestion to add them
- As a user I want the suggested amount to follow inflation or my rent contract's adjustment rule
### Savings goals
- As a user I want to create named savings goals (e.g. "new laptop", "course") with a target amount and optional deadline
- As a user I want to record contributions to a goal and see my progress and pace toward the deadline
### Ambient agent
- As a user I want the agent to review my data after an import, when I go over a budget, at month end, or when I ask
- As a user I want an Inbox with pending Suggestions and recent Insights
- As a user I want to accept (optionally editing), reject (optionally saying why) or ignore each Suggestion
- As a user I want the agent to remember what I rejected and what it already told me
- As a user I want to chat about an Insight or Suggestion when I need more context
- As a user I want a CLI tool for deep terminal-based analysis sessions
### Analysis
- As a user I want to see monthly and yearly expense summaries with charts
- As a user I want to break down spending by category visually
- As a user I want inflation-adjusted views so historical comparisons are honest
- As a user I want to see future commitments from remaining cuotas
---
 
## Information architecture
 
```
Dashboard (home)
├── Hero — Monthly Result + income/expense breakdown + mood illustration
├── Left column — spending by category (donut chart)
├── Right column — budgets (shame bars vs pace) + savings goals
└── Bottom — recent activity (expandable rows, full width)
 
Transactions
├── Expense / income list with filters
├── Quick add form (incl. cuotas and refunds)
├── Import (profiles, categorization rules, duplicate review)
└── Recurring expenses
 
Budgets
├── Category budget list
└── Set / edit budget per category
 
Analysis
├── Monthly view
├── Yearly view
├── Category breakdown over time
└── Future commitments (remaining cuotas)
 
Goals
├── Goal list with progress
├── New / edit goal
└── Contributions
 
Inbox (agent)
├── Pending Suggestions — accept / edit / reject
├── Recent Insights — dismiss
└── Run a Review now
 
Settings (global)
└── Display currency · categories · import profiles · categorization rules · data export
 
Chat (phase 3 — secondary layer)
└── Opened from an Insight or Suggestion, or from a floating button
```
 
### Navigation
Transparent floating pill at the bottom center of the viewport. Active page shown as a white inner pill. The Inbox shows a badge with pending Suggestions. Display currency is a global setting, not a per-component toggle. Period filters are local to each component that needs them.
 
---
 
## Stack
 
### Frontend
| Concern | Choice | Why |
|---|---|---|
| Framework | React 19 + TypeScript | Current, widely used, good learning target |
| Build tool | Vite | Fast, simple |
| Routing | TanStack Router | Type-safe, modern alternative to React Router |
| Data fetching | TanStack Query | Best-in-class async state management |
| Styling | Tailwind CSS v4 | Utility-first, pairs well with shadcn |
| Components | shadcn/ui | You own the code, fully customizable |
| Charts | Recharts | React-native, composable, TypeScript-first |
| Chat streaming | Vercel AI SDK (useChat) | Best DX for streaming chat UI, backend-agnostic (phase 3) |
| Package manager | pnpm | Fast, efficient |
 
### Backend
| Concern | Choice | Why |
|---|---|---|
| Framework | FastAPI + Python 3.12 | Async, typed, great for AI/ML ecosystem |
| Validation | Pydantic v2 | First-class with FastAPI, fast |
| ORM | SQLAlchemy 2.0 | Industry standard Python ORM |
| Migrations | Alembic | Pairs with SQLAlchemy, essential habit |
| Database | PostgreSQL 16 | Solid, boring, right choice |
| Async driver | asyncpg | PostgreSQL async driver |
| Package manager | uv | New standard, extremely fast |
 
### Agent layer (phase 2+)
| Concern | Choice | Why |
|---|---|---|
| Background jobs | Redis + ARQ worker | Reviews are slow LLM calls; a real worker with retries and cron is the learning target |
| Agent loop | Hand-written tool-use loop with the Anthropic Python SDK | Learn what an agent framework actually adds before adopting one |
| LLM | Claude API (Anthropic) | Tool use, PDF reading |
| Agent framework | LangGraph (phase 4) | Migration once the hand-written loop's pain points are clear |
| Chat protocol | Data Stream Protocol (AI SDK) | Frontend/backend streaming contract (phase 3) |
| MCP server | FastAPI MCP (phase 4) | Expose financial data to any MCP client |
 
### Infra & external data
| Concern | Choice | Why |
|---|---|---|
| Local orchestration | Docker Compose | One command to run everything |
| Dev script | Makefile | `make dev` starts all services |
| Dollar rates | dolarapi.com | Free blue/MEP/CCL/card rates for estimated Exchange Rates |
| Inflation (IPC) | datos.gob.ar series `145.3_INGNACUAL_DICI_M_38`, with manual override | Official INDEC series at full precision; fails loudly. No automatic failover: argentinadatos rounds, uses other units and has served stale data |
 
---
 
## Phases
 
### Phase 1 — Useful core
Goal: real data flowing in, visible and judged against budgets. No agent yet.
 
- Docker Compose with Postgres + FastAPI + React, `make dev` starts everything *(done)*
- Model fixes: typed Categories, Exchange Rate (estimated/confirmed + rate type), Refunds, Installment Purchases, Default Categories
- dolarapi.com fetch for estimated Exchange Rates
- Dashboard with hero (Monthly Result), category donut, budget bars vs pace, recent activity
- Quick add form (expense, income, cuotas, refund)
- Budgets with the shame UI; month rollover copies last month's budgets
- Import of Mercado Pago and Lemon CSV/XLSX exports via Import Profiles, Categorization Rules and duplicate detection
### Phase 2a — Suggestions without the agent
Goal: a working Inbox fed by deterministic Reviews, before any LLM is involved.

- Redis + ARQ worker in Docker Compose; Review producers are plain functions so tests stay Postgres-only
- Review, Suggestion (closed kinds: `add_transaction`, `set_budget`) and the Inbox at `/bandeja`, polled
- Accept (whole payload editable, applied through the existing services) / reject ("not this month") / lazy expiry per kind; dedupe key per kind
- Recurring Expenses with Adjustment Rules; a `recurring_monthly` Review on the 1st proposes each month's payments
- IPC fetch from datos.gob.ar with staleness check and manual override (manual wins); unpublished months leave the adjustment pending, not the Suggestion
- `month_end` Review on the 1st proposes adjusting the copied Budgets: last Budget × (1 + latest IPC), ARS only, rounded to $1.000
- Manual "Revisar ahora"; reading the Inbox queues any of this month's scheduled Reviews that are missing (the cron usually got there first)
### Phase 2b — Ambient agent
Goal: the agent reviews your data on its own and proposes improvements.

- Hand-written Claude tool-use loop (API key, Sonnet by default, 10-iteration cap, retries only on 429/529)
- Tailored seed brief per trigger plus read-only tools; history capped by a quarterly/annual setting
- Triggers: `import_finished` (coalesced), `budget_exceeded` (100%, once per Budget), `month_end`, `manual`
- Insights, shown during their month; rejections and past Insights feed later Reviews
- New kinds: `recategorize_transaction`, `add_categorization_rule` (future imports only), `add_recurring_expense`
- Agent month-end budgets supersede the arithmetic producer, which becomes its fallback
- Transcript, tokens and `prompt_version` stored per Review; `LLMClient` Protocol with a scripted fake for tests, manual `make eval` for judgment
### Phase 3 — Complete the picture
Goal: the remaining tracking and analysis features.
 
- Goals with Contributions and progress/pace toward the deadline
- PDF statements read by the agent and turned into Suggestions
- Full Transactions, Budgets, Analysis and Goals views; period filters per component
- Future commitments view (remaining cuotas)
- Chat about Inbox items (Vercel AI SDK useChat), context-aware of the current screen
### Phase 4 — Go deeper
Goal: agent framework, MCP, CLI, honest history.
 
- LangGraph migration of the Review loop
- MCP server exposing financial data to any MCP client
- CLI tool for terminal-based deep analysis sessions
- Inflation-adjusted historical views
### Phase 5 — Just for fun
Goal: bigger model changes and edge experiments.
 
- Accounts, transfers and currency exchange (dollars and crypto)
- HTMX alternative frontend (same FastAPI backend)
- Telegram bot for quick expense entry
- Full mobile layout
- i18n if anyone outside Argentina asks
- Anything else that seems interesting at the time
---
 
## Folder structure
 
```
finanzas/
├── docker-compose.yml
├── Makefile
├── README.md
├── CONTEXT.md           ← domain glossary
├── root-idea.md         ← this file
├── docs/
│   ├── adr/             ← architecture decision records
│   └── agents/          ← instructions for coding agents
├── samples/             ← real exports for designing imports (git-ignored)
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── routes/
│   │   ├── hooks/
│   │   ├── lib/
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
│
└── backend/
    ├── app/
    │   ├── api/
    │   │   └── routes/
    │   ├── models/
    │   ├── schemas/
    │   ├── services/
    │   ├── agent/       ← Review loop, tools (phase 2)
    │   ├── worker.py    ← ARQ worker (phase 2)
    │   └── main.py
    ├── alembic/
    ├── pyproject.toml
    └── Dockerfile
```
 
---
 
## Data model
 
### Phase 1
 
#### Category
```
id              uuid, pk
name            text
type            enum: expense | income
color           text (hex)
icon            text, optional
is_default      boolean
```
 
#### Transaction
```
id                      uuid, pk
amount                  numeric(12, 2)          negative only for refunds
currency                enum: ARS | USD
type                    enum: expense | income
category_id             fk → Category           category.type must equal type
description             text, optional
notes                   text, optional
is_fixed                boolean, default false
date                    date
exchange_rate           numeric, optional       ARS per USD; required when currency = USD
exchange_rate_type      enum, optional          official | blue | mep | ccl | card | manual
exchange_rate_status    enum, optional          estimated | confirmed
refund_of_id            fk → Transaction, optional
installment_purchase_id fk → InstallmentPurchase, optional
installment_number      int, optional           e.g. 3 (of 6)
amount_status           enum: estimated | confirmed, default confirmed   estimated for future cuotas
import_id               fk → Import, optional
created_at              timestamp
```
 
#### InstallmentPurchase
```
id              uuid, pk
description     text
total_amount    numeric(12, 2)
currency        enum: ARS | USD
installments    int
category_id     fk → Category
purchase_date   date                    cuota 1 lands in this month
created_at      timestamp
```
 
#### Budget
```
id              uuid, pk
category_id     fk → Category           expense categories only
amount          numeric(12, 2)
currency        enum: ARS | USD
month           date (first day of month)
```
 
#### ImportProfile
```
id              uuid, pk
name            text                    e.g. "Mercado Pago — actividad"
source          text                    e.g. mercadopago | lemon
column_mapping  jsonb
date_format     text
number_format   text                    e.g. "1.234,56"
sign_convention text
```
 
#### Import
```
id              uuid, pk
profile_id      fk → ImportProfile
filename        text
imported_count  int
skipped_count   int
created_at      timestamp
```
 
#### CategorizationRule
```
id              uuid, pk
pattern         text                    description contains
category_id     fk → Category
origin          enum: manual | suggestion
created_at      timestamp
```
 
### Phase 2
 
#### Transaction (additions)
```
recurring_expense_id    fk → RecurringExpense, optional   set when accepted from its Suggestion
```
 
#### Budget (additions)
```
exceeded_review_id      fk → Review, optional   the Review fired when it crossed 100%; fires once
```
 
#### Settings (additions)
```
agent_lookback          enum: quarter | year, default quarter   hard cap on what the agent reads
```
 
#### RecurringExpense
```
id                  uuid, pk
description         text
category_id         fk → Category
currency            enum: ARS | USD
reference_amount    numeric(12, 2)      stands in until a linked Transaction exists
expected_day        int
is_fixed            boolean
adjustment_kind     enum: none | percentage | index, default none
adjustment_every    int, optional       months
adjustment_value    numeric, optional   % when percentage
adjustment_index    text, optional      e.g. IPC
active              boolean
```
 
#### InflationIndex
```
month           date (first day of month), pk
index           text, pk                e.g. IPC
value           numeric                 monthly variation in percentage points (1.659 = 1.659%)
source          enum: api | manual      manual is never overwritten by a fetch
```
 
#### Review
```
id              uuid, pk
trigger         enum: recurring_monthly | month_end | manual | import_finished | budget_exceeded
status          enum: queued | running | done | failed
uses_agent      boolean
error           text, optional
note            text, optional          e.g. "hit the iteration cap"
messages        jsonb, optional         agent transcript
input_tokens    int, optional
output_tokens   int, optional
prompt_version  text, optional
created_at      timestamp
started_at      timestamp, optional
finished_at     timestamp, optional
```
 
#### Suggestion
```
id              uuid, pk
review_id       fk → Review
kind            enum: add_transaction | set_budget | recategorize_transaction | add_categorization_rule | add_recurring_expense
month           date (first day of month)       the month it is about
dedupe_key      text                    per kind, e.g. recurring_expense_id + month
payload         jsonb                   validated per kind
rationale       text
status          enum: pending | accepted | rejected | expired
rejection_reason text, optional
expires_at      timestamp
resolved_at     timestamp, optional
created_at      timestamp
```
 
#### Insight (2b)
```
id              uuid, pk
review_id       fk → Review
month           date (first day of month)
topic           text
body            text
dismissed_at    timestamp, optional
created_at      timestamp
```
 
### Phase 3
 
#### Goal
```
id              uuid, pk
name            text
target_amount   numeric(12, 2)
currency        enum: ARS | USD
deadline        date, optional
created_at      timestamp
```
 
#### Contribution
```
id              uuid, pk
goal_id         fk → Goal
amount          numeric(12, 2)          in the goal's currency
date            date
created_at      timestamp
```
 
---
 
## Dashboard layout
 
```
┌─────────────────────────────────────────────────────┐
│  HERO — full width                                  │
│  Monthly Result (big) + income/expense  mood image  │
│  breakdown on the left                 on the right │
├──────────────────────────┬──────────────────────────┤
│  CATEGORY BREAKDOWN      │  BUDGETS                 │
│  donut chart + legend    │  shame bars vs pace      │
│  period filter           │                          │
│                          ├──────────────────────────┤
│                          │  GOALS                   │
│                          │  progress bars           │
├──────────────────────────┴──────────────────────────┤
│  RECENT ACTIVITY — full width                       │
│  lean text rows, click to expand inline             │
└─────────────────────────────────────────────────────┘
      ○ Transactions  ● Dashboard  ○ Analysis  ○ Goals  ○ Inbox (3)
```
 
---
 
## Key decisions log
 
| Decision | Choice | Reasoning |
|---|---|---|
| Learning vs usefulness | Useful core first, learning drives later phases | The agent needs real data to be worth building |
| Entry model | Manual + file import (Mercado Pago, Lemon) | Argentine banks don't expose APIs; privacy-friendly |
| Accounts | Money flow only for now; Accounts in phase 5 | Keeps the model small; exchanges aren't recorded meanwhile |
| Multi-currency | ARS + USD, stored rate per transaction (ADR-0001) | Honest history despite daily-moving rates |
| Crypto | Outside the model | USDT behaves as "dollars"; holdings need Accounts |
| Refunds | Negative expense in the original category | Budgets and charts reflect real spending |
| Cuotas | Installment Purchase → one estimated expense per month | Inflation makes cuotas a strategy; budgets see the monthly share |
| Goals | Progress = sum of Contributions; not expenses | Saving isn't spending; gives the agent real history |
| Budget enforcement | Visible shame vs pace, no hard blocks | Reflection over friction |
| Budget rollover | Copy last month's as a floor; month-end Review suggests adjustments | Never an empty month; inflation makes copied amounts wrong |
| Recurring amounts | Last amount paid, or adjustment rule (% / IPC) | Inflation; rent follows contracts |
| Import | CSV/XLSX via profiles + rules; PDF via agent Suggestions (phase 3) | Real export formats vary and are often PDF |
| Uncategorized Transactions | Never; the agent improves rules after an Import (ADR-0004) | Every view assumes a Category |
| Agent authority | Suggestions only, user accepts (ADR-0002) | Silent mistakes in financial data are costly and hard to notice |
| Review scope | Every Suggestion comes from a Review, agent or not (ADR-0003) | One lifecycle for the Inbox |
| Suggestion kinds | Closed list, typed payloads, applied via the normal services | Makes ADR-0002 enforceable |
| Agent triggers | Import (coalesced), budget over 100% once, month end, manual | Ambient but not noisy or expensive |
| LLM access | Console API key, not the Claude subscription | Subscriptions don't include API access |
| Agent history | Hard cap, quarterly or annual (setting) | Bounds cost and data sent to the API |
| Inbox updates | Polling | One user, one tab; streaming waits for chat |
| Agent surface | Inbox first, chat secondary | The inbox is the new pattern to learn; chat is well-trodden |
| Background jobs | Redis + ARQ from phase 2 | Reviews are slow; real worker is the learning goal |
| Agent framework | Hand-written loop first, LangGraph in phase 4 | Understand what the framework adds |
| Language | Spanish UI and agent, English code | Built for Argentina; i18n only on demand |
| Navigation | Transparent floating pill | Minimal chrome, currently fashionable |
| Period control | Local filter per component | Components can show different periods independently |
| Display currency | Global setting | It's a preference, not a filter |
| Transaction detail | Inline expandable row | No modal, no context loss |
| Frontend alt | HTMX planned for phase 5 | Different architectural paradigm, portfolio value |
 
---
 
## Running locally
 
```bash
# clone and enter
git clone https://github.com/agudlc/finanzas
cd finanzas
 
# start everything
make dev
 
# frontend:  http://localhost:5173
# backend:   http://localhost:8000
# api docs:  http://localhost:8000/docs
```
 
---
 
*Last updated: September 2026 — Phase 1 done; Phase 2 grilled and split into 2a (deterministic Suggestions and Inbox) and 2b (the agent). See CONTEXT.md and docs/adr/.*
