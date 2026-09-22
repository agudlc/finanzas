"""
The month the agent is judged on, and the four Reviews it is asked about.

One dataset, written down rather than generated, because the whole point is
that two runs of `make eval` differ only in what the model said. It is a
plausible three months of one person's money in Buenos Aires: a quarter of
history to compare against, an Import that just landed with a Transaction
filed in the wrong Category and a description that keeps arriving, a Delivery
Budget well past its limit, and the Inbox already holding a proposal and a
rejection so a run has something to avoid repeating.

The dates are fixed with it. Today is the 18th of March 2026: far enough into
the month that there is something to say about it, and not so far that the
Import has stopped being news.

That one day is what the month-end case pays for. A month-end Review usually
runs on the 1st, over a month that has barely started; here it runs late, which
is a path the app has — the schedule is due on a day and the next Inbox read
catches it up (ADR-0005) — but it means the model proposing March's Budgets
sees eighteen days of March as well as the February that ended. One dataset and
one day is the trade: a second month, complete, would make that case truer and
the other three about a month nobody is living.

Nothing here goes through the HTTP API: this is a database as the app would
have left it, written in the fewest rows that make the month true.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date as Date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Budget,
    CategorizationRule,
    Category,
    Import,
    ImportProfile,
    RateSnapshot,
    RecurringExpense,
    Review,
    Transaction,
)
from app.models.enums import (
    AdjustmentKind,
    ConfirmationStatus,
    Currency,
    NumberFormat,
    RateType,
    ReviewStatus,
    ReviewTrigger,
    RuleOrigin,
    SignConvention,
    SuggestionKind,
    SuggestionStatus,
)
from app.months import month_of
from app.services import insights as insights_service
from app.services.budgets import budget_for
from app.services.reviews import create_review
from app.services.suggestions import propose

# The day the whole fixture is read from. Everything below is dated against it.
TODAY = Date(2026, 3, 18)

MONTH = month_of(TODAY)
FEBRUARY = Date(2026, 2, 1)
JANUARY = Date(2026, 1, 1)

# The IPC as the fixture's own source publishes it, standing in for
# datos.gob.ar: February is the newest month out by the middle of March, which
# is what a month-end Review moves Budgets by.
IPC_POINTS = [
    (Date(2025, 11, 1), Decimal("2.400")),
    (Date(2025, 12, 1), Decimal("2.100")),
    (Date(2026, 1, 1), Decimal("1.900")),
    (Date(2026, 2, 1), Decimal("1.659")),
]

# One card rate per month, so the USD rows and the Budget in dollars convert
# without anything reaching dolarapi.com.
CARD_RATES = [
    (Date(2026, 1, 1), Decimal("1350.00")),
    (Date(2026, 2, 1), Decimal("1420.00")),
    (Date(2026, 3, 1), Decimal("1500.00")),
]

# What the March Import brought in, and what it was filed as. "FARMACITY" in
# Supermercado is the row in the wrong Category; "RAPPI" is the description
# that has arrived every month and has no Categorization Rule yet.
IMPORTED = [
    (Date(2026, 3, 11), "Servicios", "EDENOR SERVICIOS", "31500.00"),
    (Date(2026, 3, 12), "Suscripciones", "OPENAI *CHATGPT SUBSCR", "20.00", "USD"),
    (Date(2026, 3, 13), "Transporte", "MERPAGO*CABIFY", "6400.00"),
    (Date(2026, 3, 14), "Supermercado", "COTO DIGITAL", "63200.00"),
    (Date(2026, 3, 15), "Delivery", "RAPPI*RESTAURANTES", "12900.00"),
    (Date(2026, 3, 16), "Supermercado", "FARMACITY SUC 45", "24300.00"),
    (Date(2026, 3, 16), "Delivery", "PEDIDOSYA*ORDER 8821", "18400.00"),
    (Date(2026, 3, 17), "Transporte", "SUBE CARGA", "8000.00"),
]

# Everything the user recorded themselves, oldest month first: the three
# months the default lookback reaches, with March stopping at the 10th because
# the file above is the rest of it.
RECORDED = [
    # January
    (Date(2026, 1, 4), "Supermercado", "Coto", "62000.00"),
    (Date(2026, 1, 5), "Sueldo", "Sueldo enero", "1850000.00"),
    (Date(2026, 1, 5), "Alquiler", "Alquiler enero", "450000.00"),
    (Date(2026, 1, 6), "Servicios", "Edenor", "21000.00"),
    (Date(2026, 1, 7), "Transporte", "SUBE carga", "8000.00"),
    (Date(2026, 1, 8), "Servicios", "Metrogas", "14500.00"),
    (Date(2026, 1, 9), "Delivery", "PedidosYa", "14500.00"),
    (Date(2026, 1, 10), "Servicios", "Personal Flow", "42500.00"),
    (Date(2026, 1, 10), "Suscripciones", "Netflix", "12.99", "USD"),
    (Date(2026, 1, 11), "Supermercado", "Carrefour", "58500.00"),
    (Date(2026, 1, 12), "Suscripciones", "Spotify", "7500.00"),
    (Date(2026, 1, 14), "Transporte", "Cabify", "12000.00"),
    (Date(2026, 1, 17), "Delivery", "Rappi", "19500.00"),
    (Date(2026, 1, 18), "Supermercado", "Coto", "71000.00"),
    (Date(2026, 1, 19), "Salud", "Farmacity", "15400.00"),
    (Date(2026, 1, 21), "Transporte", "SUBE carga", "8000.00"),
    (Date(2026, 1, 24), "Delivery", "PedidosYa", "18000.00"),
    (Date(2026, 1, 24), "Ocio", "Cine", "18000.00"),
    (Date(2026, 1, 25), "Supermercado", "Dia", "46500.00"),
    (Date(2026, 1, 28), "Transporte", "Uber", "10000.00"),
    (Date(2026, 1, 29), "Supermercado", "Verdulería", "47000.00"),
    (Date(2026, 1, 31), "Rendimientos", "Rendimientos Mercado Pago", "24500.00"),
    # February
    (Date(2026, 2, 3), "Supermercado", "Coto", "64000.00"),
    (Date(2026, 2, 4), "Transporte", "SUBE carga", "8000.00"),
    (Date(2026, 2, 5), "Sueldo", "Sueldo febrero", "1850000.00"),
    (Date(2026, 2, 5), "Alquiler", "Alquiler febrero", "450000.00"),
    (Date(2026, 2, 6), "Servicios", "Edenor", "26000.00"),
    (Date(2026, 2, 7), "Delivery", "PedidosYa", "16000.00"),
    (Date(2026, 2, 9), "Servicios", "Metrogas", "15000.00"),
    (Date(2026, 2, 10), "Servicios", "Personal Flow", "45000.00"),
    (Date(2026, 2, 10), "Supermercado", "Carrefour", "62000.00"),
    (Date(2026, 2, 10), "Suscripciones", "Netflix", "12.99", "USD"),
    (Date(2026, 2, 11), "Transporte", "Cabify", "14000.00"),
    (Date(2026, 2, 12), "Suscripciones", "Spotify", "7900.00"),
    (Date(2026, 2, 13), "Delivery", "Rappi", "21000.00"),
    (Date(2026, 2, 14), "Ocio", "Teatro", "32000.00"),
    (Date(2026, 2, 17), "Supermercado", "Coto", "78000.00"),
    (Date(2026, 2, 18), "Transporte", "SUBE carga", "8000.00"),
    (Date(2026, 2, 20), "Delivery", "PedidosYa", "17500.00"),
    (Date(2026, 2, 20), "Freelance", "Proyecto web", "300000.00"),
    (Date(2026, 2, 21), "Ropa", "Zara", "68000.00"),
    (Date(2026, 2, 24), "Supermercado", "Dia", "52000.00"),
    (Date(2026, 2, 25), "Transporte", "Uber", "11000.00"),
    (Date(2026, 2, 26), "Delivery", "Rappi", "13500.00"),
    (Date(2026, 2, 27), "Supermercado", "Verdulería", "54000.00"),
    (Date(2026, 2, 28), "Rendimientos", "Rendimientos Mercado Pago", "26800.00"),
    # March, up to the day the file was loaded
    (Date(2026, 3, 2), "Delivery", "PedidosYa", "15200.00"),
    (Date(2026, 3, 3), "Supermercado", "Carrefour", "68000.00"),
    (Date(2026, 3, 4), "Transporte", "Cabify", "13500.00"),
    (Date(2026, 3, 5), "Sueldo", "Sueldo marzo", "2100000.00"),
    (Date(2026, 3, 5), "Alquiler", "Alquiler marzo", "520000.00"),
    (Date(2026, 3, 6), "Delivery", "Rappi", "22000.00"),
    (Date(2026, 3, 8), "Servicios", "Metrogas", "15500.00"),
    (Date(2026, 3, 9), "Supermercado", "Dia", "49500.00"),
    (Date(2026, 3, 10), "Servicios", "Personal Flow", "47000.00"),
    (Date(2026, 3, 10), "Delivery", "PedidosYa", "28000.00"),
    (Date(2026, 3, 10), "Suscripciones", "Netflix", "12.99", "USD"),
    (Date(2026, 3, 12), "Suscripciones", "Spotify", "8200.00"),
    (Date(2026, 3, 14), "Ocio", "Bar con amigos", "24000.00"),
]

# The limits each month ran on. March's Delivery is the one that broke: 96.500
# spent against 60.000, which is what the budget_exceeded Review is about.
BUDGETS = [
    (FEBRUARY, "Alquiler", "450000.00", "ARS"),
    (FEBRUARY, "Supermercado", "300000.00", "ARS"),
    (FEBRUARY, "Delivery", "55000.00", "ARS"),
    (FEBRUARY, "Servicios", "85000.00", "ARS"),
    (FEBRUARY, "Transporte", "45000.00", "ARS"),
    (FEBRUARY, "Suscripciones", "45.00", "USD"),
    (MONTH, "Alquiler", "520000.00", "ARS"),
    (MONTH, "Supermercado", "320000.00", "ARS"),
    (MONTH, "Delivery", "60000.00", "ARS"),
    (MONTH, "Servicios", "95000.00", "ARS"),
    (MONTH, "Transporte", "45000.00", "ARS"),
    (MONTH, "Suscripciones", "45.00", "USD"),
]

# The Categories whose Expenses the user considers unavoidable. Everything
# else about a row follows from its Category, which is where its type lives.
FIXED_CATEGORIES = ("Alquiler", "Servicios")

# The Rules that filed the Import. "RAPPI" and "FARMACITY" are deliberately
# missing: one is the pattern worth learning, the other the row worth moving.
RULES = [
    ("PEDIDOSYA", "Delivery"),
    ("COTO", "Supermercado"),
    ("SUBE", "Transporte"),
    ("EDENOR", "Servicios"),
]


async def seed(db: AsyncSession) -> None:
    """Write the whole dataset, as the app would have left it."""
    categories = await _categories(db)
    _rates(db)
    templates = _templates(db, categories)
    _budgets(db, categories)
    _rules(db, categories)
    _recorded(db, categories)
    await db.flush()
    await _imported(db, categories)
    await db.commit()
    await _history(db, categories, templates)


async def _categories(db: AsyncSession) -> dict[str, Category]:
    """
    The default Categories by name, which is how the rows above name them.

    The Category itself rather than its id, because what a row is follows from
    it: an expense Category only classifies Expenses, so naming the Category
    is the whole of saying which a row is.
    """
    result = await db.execute(select(Category))
    return {one.name: one for one in result.scalars().all()}


def _rates(db: AsyncSession) -> None:
    for day, value in CARD_RATES:
        db.add(
            RateSnapshot(date=day, rate_type=RateType.card, value=value)
        )


def _templates(
    db: AsyncSession, categories: dict[str, Category]
) -> dict[str, RecurringExpense]:
    """
    What comes every month: the rent, with the contract's Adjustment Rule, and
    the internet, which the Inbox is already proposing.
    """
    rent = RecurringExpense(
        description="Alquiler",
        category_id=categories["Alquiler"].id,
        currency=Currency.ARS,
        reference_amount=Decimal("520000.00"),
        expected_day=5,
        is_fixed=True,
        adjustment_kind=AdjustmentKind.index,
        adjustment_period_months=3,
        adjustment_index_name="IPC",
        adjustment_start_month=Date(2026, 1, 1),
    )
    internet = RecurringExpense(
        description="Internet Fibertel",
        category_id=categories["Servicios"].id,
        currency=Currency.ARS,
        reference_amount=Decimal("28000.00"),
        expected_day=20,
        is_fixed=True,
    )
    db.add_all([rent, internet])
    return {"rent": rent, "internet": internet}


def _budgets(db: AsyncSession, categories: dict[str, Category]) -> None:
    for month, category, amount, currency in BUDGETS:
        db.add(
            Budget(
                category_id=categories[category].id,
                amount=Decimal(amount),
                currency=Currency(currency),
                month=month,
            )
        )


def _rules(db: AsyncSession, categories: dict[str, Category]) -> None:
    for pattern, category in RULES:
        db.add(
            CategorizationRule(
                pattern=pattern,
                category_id=categories[category].id,
                origin=RuleOrigin.manual,
            )
        )


def _recorded(db: AsyncSession, categories: dict[str, Category]) -> None:
    for row in RECORDED:
        db.add(_transaction(categories, *row))


async def _imported(db: AsyncSession, categories: dict[str, Category]) -> None:
    """The file that landed on the 17th, and the rows it brought in."""
    profile = ImportProfile(
        name="Mercado Pago",
        source="Mercado Pago",
        column_mapping={
            "date": "Fecha",
            "description": "Descripción",
            "amount": "Monto",
        },
        date_format="%d/%m/%Y",
        number_format=NumberFormat.comma_decimal,
        sign_convention=SignConvention.negative_is_expense,
        ignore_patterns=["Transferencia a"],
    )
    db.add(profile)
    await db.flush()
    record = Import(
        profile_id=profile.id,
        filename="mercadopago-marzo.csv",
        imported_count=len(IMPORTED),
        skipped_count=3,
    )
    db.add(record)
    await db.flush()
    for row in IMPORTED:
        transaction = _transaction(categories, *row)
        transaction.import_id = record.id
        db.add(transaction)


def _transaction(
    categories: dict[str, Category],
    day: Date,
    name: str,
    description: str,
    amount: str,
    currency: str = "ARS",
) -> Transaction:
    """
    One row, with everything that follows from its Category and its currency.

    Whether it is an Expense or an Income is the Category's to say, so the rows
    above name a Category and nothing else. A USD row carries the card rate of
    its month as a confirmed Exchange Rate, the way one read off a statement
    would (ADR-0001).
    """
    category = categories[name]
    money = Currency(currency)
    rate = _card_rate(day) if money is Currency.USD else None
    return Transaction(
        amount=Decimal(amount),
        currency=money,
        type=category.type,
        category_id=category.id,
        description=description,
        is_fixed=name in FIXED_CATEGORIES,
        date=day,
        exchange_rate=rate,
        exchange_rate_type=None if rate is None else RateType.card,
        exchange_rate_status=(
            None if rate is None else ConfirmationStatus.confirmed
        ),
    )


def _card_rate(day: Date) -> Decimal:
    """The card rate of that row's month, as the statement settled it."""
    return next(
        value for month, value in reversed(CARD_RATES) if month <= day
    )


async def _history(
    db: AsyncSession,
    categories: dict[str, Category],
    templates: dict[str, RecurringExpense],
) -> None:
    """
    What earlier Reviews left behind: an observation, a proposal still waiting
    and one the user said no to.

    Every run reads all three — they are what keeps it from saying the same
    thing again, proposing what is already in the Inbox, or pushing what has
    already been refused — so a month without them would be judging the agent
    on an easier month than the real one.
    """
    february = await _finished_review(db, FEBRUARY)
    insights_service.record(
        db,
        february,
        "Delivery arriba del promedio",
        "En febrero gastaste 68.000 en Delivery contra un límite de 55.000. "
        "Es el segundo mes seguido por encima.",
    )
    rejected = await propose(
        db,
        february.id,
        SuggestionKind.set_budget,
        FEBRUARY,
        {
            "category_id": str(categories["Ocio"].id),
            "amount": "25000.00",
            "currency": "ARS",
            "month": FEBRUARY.isoformat(),
        },
        "Ocio no tiene límite y viene creciendo.",
    )
    rejected.status = SuggestionStatus.rejected
    rejected.rejection_reason = "No quiero un límite para salir."

    march = await _finished_review(db, MONTH)
    await propose(
        db,
        march.id,
        SuggestionKind.add_transaction,
        MONTH,
        {
            "category_id": str(categories["Servicios"].id),
            "amount": "28000.00",
            "currency": "ARS",
            "date": Date(2026, 3, 20).isoformat(),
            "description": "Internet Fibertel",
            "is_fixed": True,
            "recurring_expense_id": str(templates["internet"].id),
        },
        "Internet Fibertel vence el 20 y todavía no está registrado.",
    )
    await db.commit()


async def _finished_review(db: AsyncSession, month: Date) -> Review:
    """A deterministic Review of that month, already done."""
    review = await create_review(db, ReviewTrigger.recurring_monthly, month)
    review.status = ReviewStatus.done
    await db.commit()
    return review


@dataclass(frozen=True)
class Case:
    """
    One trigger, and how the Review that stands for it is wired up.

    Wiring is where the triggers differ: an Import Review is about the file
    that points at it, a budget_exceeded one about the Budget that points at
    it, and the other two about the month alone. The trigger is the Case's own
    and is handed to the wiring, so a Case cannot stand for one trigger and
    prepare a Review of another.
    """

    trigger: ReviewTrigger
    prepare: Callable[[AsyncSession, ReviewTrigger], Awaitable[Review]]

    async def review(self, db: AsyncSession) -> Review:
        """The Review this case is about, ready to be run."""
        return await self.prepare(db, self.trigger)


async def _about_the_month(db: AsyncSession, trigger: ReviewTrigger) -> Review:
    return await create_review(db, trigger, MONTH)


async def _about_the_import(
    db: AsyncSession, trigger: ReviewTrigger
) -> Review:
    review = await create_review(db, trigger, MONTH)
    record = (await db.execute(select(Import))).scalars().one()
    record.review_id = review.id
    await db.commit()
    return review


async def _about_the_broken_budget(
    db: AsyncSession, trigger: ReviewTrigger
) -> Review:
    review = await create_review(db, trigger, MONTH)
    categories = await _categories(db)
    budget = await budget_for(db, categories["Delivery"].id, MONTH)
    budget.exceeded_review_id = review.id
    await db.commit()
    return review


CASES = [
    Case(ReviewTrigger.manual_agent, _about_the_month),
    Case(ReviewTrigger.import_finished, _about_the_import),
    Case(ReviewTrigger.budget_exceeded, _about_the_broken_budget),
    Case(ReviewTrigger.month_end, _about_the_month),
]
