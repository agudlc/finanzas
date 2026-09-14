"""Nothing is saved until the user has seen every row."""

from tests.api import create_transaction, default_category
from tests.api_imports import LEMON, create_profile, preview, row_named
from tests.test_categorization_rules import create_rule


async def test_argentine_numbers_and_dates_are_read(client):
    profile = await create_profile(client)

    seen = await preview(client, profile, "mercadopago.csv")

    coto = row_named(seen, "Supermercado Coto")
    assert coto["date"] == "2026-03-05"
    assert coto["amount"] == "12500.50"
    assert coto["currency"] == "ARS"


async def test_a_debit_is_an_expense_and_a_credit_an_income(client):
    profile = await create_profile(client)

    seen = await preview(client, profile, "mercadopago.csv")

    assert row_named(seen, "Supermercado Coto")["type"] == "expense"
    assert row_named(seen, "Rendimientos")["type"] == "income"


async def test_a_negative_amount_is_an_expense_when_the_profile_says_so(client):
    profile = await create_profile(client, **LEMON)

    seen = await preview(client, profile, "lemon.csv")

    netflix = row_named(seen, "Netflix")
    assert netflix["type"] == "expense"
    assert netflix["amount"] == "15.99"
    assert netflix["currency"] == "USD"
    assert row_named(seen, "Cashback")["type"] == "income"


async def test_rows_the_profile_ignores_are_shown_as_ignored(client):
    profile = await create_profile(client)

    seen = await preview(client, profile, "mercadopago.csv")

    assert row_named(seen, "Transferencia a mi cuenta")["status"] == "ignored"
    assert row_named(seen, "Compra de USDT")["status"] == "ignored"
    assert row_named(seen, "Supermercado Coto")["status"] != "ignored"


async def test_a_row_with_no_rule_needs_a_category(client):
    profile = await create_profile(client)

    seen = await preview(client, profile, "mercadopago.csv")

    coto = row_named(seen, "Supermercado Coto")
    assert coto["category_id"] is None
    assert coto["status"] == "needs_category"


async def test_a_row_matching_a_rule_arrives_with_its_category(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_rule(client, "coto", supermercado)
    profile = await create_profile(client)

    seen = await preview(client, profile, "mercadopago.csv")

    coto = row_named(seen, "Supermercado Coto")
    assert coto["category_id"] == supermercado["id"]
    assert coto["status"] == "new"


async def test_the_longest_matching_pattern_wins(client):
    ocio = await default_category(client, "Ocio", "expense")
    suscripciones = await default_category(client, "Suscripciones", "expense")
    await create_rule(client, "mercado", ocio)
    await create_rule(client, "mercado libre", suscripciones)
    profile = await create_profile(client)

    seen = await preview(client, profile, "mercadopago.csv")

    assert row_named(seen, "Mercado Libre - auriculares")["category_id"] == (
        suscripciones["id"]
    )


async def test_a_row_already_recorded_is_flagged_a_duplicate(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_transaction(
        client,
        category_id=supermercado["id"],
        amount="12500.50",
        date="2026-03-05",
        description="  supermercado coto  ",
    )
    profile = await create_profile(client)

    seen = await preview(client, profile, "mercadopago.csv")

    assert row_named(seen, "Supermercado Coto")["status"] == "duplicate"


async def test_a_refund_already_recorded_does_not_shadow_a_real_purchase(client):
    """A Refund of 12.500,50 is not the same movement as spending 12.500,50."""
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_transaction(
        client,
        category_id=supermercado["id"],
        amount="-12500.50",
        date="2026-03-05",
        description="Supermercado Coto",
    )
    profile = await create_profile(client)

    seen = await preview(client, profile, "mercadopago.csv")

    assert row_named(seen, "Supermercado Coto")["status"] != "duplicate"


async def test_an_xlsx_export_is_read_like_a_csv(client):
    profile = await create_profile(client)

    seen = await preview(client, profile, "mercadopago.xlsx")

    farmacia = row_named(seen, "Farmacia del Pueblo")
    assert farmacia["date"] == "2026-03-12"
    assert farmacia["amount"] == "8750.00"
    assert row_named(seen, "Sueldo")["type"] == "income"
    assert len(seen["rows"]) == 2, "the empty line is not a row"


async def test_a_preview_saves_nothing(client):
    profile = await create_profile(client)

    await preview(client, profile, "mercadopago.csv")

    assert (await client.get("/transactions/")).json() == []
    assert (await client.get("/imports/")).json() == []


async def test_a_file_that_is_neither_csv_nor_xlsx_is_refused(client):
    profile = await create_profile(client)

    response = await client.post(
        "/imports/preview",
        data={"profile_id": profile["id"]},
        files={"file": ("resumen.pdf", b"%PDF-1.4")},
    )

    assert response.status_code == 422


async def test_a_profile_that_does_not_fit_the_file_says_so(client):
    profile = await create_profile(client, **LEMON)

    response = await client.post(
        "/imports/preview",
        data={"profile_id": profile["id"]},
        files={"file": ("mercadopago.csv",
                        (await _fixture("mercadopago.csv")))},
    )

    assert response.status_code == 422
    assert "column" in response.json()["detail"]


async def _fixture(name: str) -> bytes:
    from tests.api_imports import FIXTURES

    return (FIXTURES / name).read_bytes()
