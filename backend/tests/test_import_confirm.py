"""Confirming an Import: validated like manual entry, and reversible."""

from datetime import date

from tests.api import default_category
from tests.conftest import TODAY
from tests.api_imports import LEMON, confirm_body, create_profile, preview, row_named
from tests.test_categorization_rules import create_rule

UNKNOWN = "00000000-0000-0000-0000-000000000000"


async def categorised_preview(client, profile, fixture="mercadopago.csv") -> dict:
    """Every row of the fixture already matched to a Category by a Rule."""
    supermercado = await default_category(client, "Supermercado", "expense")
    ocio = await default_category(client, "Ocio", "expense")
    rendimientos = await default_category(client, "Rendimientos", "income")
    await create_rule(client, "coto", supermercado)
    await create_rule(client, "mercado libre", ocio)
    await create_rule(client, "rendimientos", rendimientos)
    return await preview(client, profile, fixture)


async def test_a_confirmed_import_records_its_rows(client):
    profile = await create_profile(client)
    seen = await categorised_preview(client, profile)

    response = await client.post("/imports/", json=confirm_body(seen))

    assert response.status_code == 201
    recorded = (await client.get("/transactions/")).json()
    assert {t["description"] for t in recorded} == {
        "Supermercado Coto", "Mercado Libre - auriculares", "Rendimientos"
    }


async def test_the_import_counts_what_it_loaded_and_what_it_skipped(client):
    profile = await create_profile(client)
    seen = await categorised_preview(client, profile)

    created = (await client.post("/imports/", json=confirm_body(seen))).json()

    assert created["imported_count"] == 3
    assert created["skipped_count"] == 2, "the transfer and the crypto buy"
    assert created["filename"] == "mercadopago.csv"
    assert created["profile_id"] == profile["id"]


async def test_an_imported_expense_is_stored_as_money_leaving(client):
    profile = await create_profile(client)
    seen = await categorised_preview(client, profile)

    await client.post("/imports/", json=confirm_body(seen))

    recorded = (await client.get("/transactions/")).json()
    coto = next(t for t in recorded if t["description"] == "Supermercado Coto")
    assert coto["type"] == "expense"
    assert coto["amount"] == "12500.50"


async def test_a_row_marked_as_a_refund_is_stored_negative(client):
    profile = await create_profile(client)
    seen = await categorised_preview(client, profile)

    await client.post(
        "/imports/",
        json=confirm_body(seen, **{"Supermercado Coto": {"is_refund": True}}),
    )

    recorded = (await client.get("/transactions/")).json()
    coto = next(t for t in recorded if t["description"] == "Supermercado Coto")
    assert coto["amount"] == "-12500.50"
    assert coto["type"] == "expense"


async def test_a_usd_row_gets_an_estimated_rate_like_a_manual_entry(client, clock):
    # The export covers days already past, which is what Rate Snapshots are for.
    clock.date = date(2026, 3, 10)
    await client.get("/settings/rate", params={"rate_type": "card"})
    clock.date = TODAY

    profile = await create_profile(client, **LEMON)
    suscripciones = await default_category(client, "Suscripciones", "expense")
    rendimientos = await default_category(client, "Rendimientos", "income")
    await create_rule(client, "netflix", suscripciones)
    await create_rule(client, "cashback", rendimientos)
    seen = await preview(client, profile, "lemon.csv")

    await client.post("/imports/", json=confirm_body(seen))

    netflix = next(
        t for t in (await client.get("/transactions/")).json()
        if t["description"] == "Netflix"
    )
    assert netflix["currency"] == "USD"
    assert netflix["exchange_rate"] == "1500.0000"
    assert netflix["exchange_rate_status"] == "estimated"


async def test_an_import_with_an_uncategorised_row_is_refused(client):
    profile = await create_profile(client)
    seen = await preview(client, profile, "mercadopago.csv")

    response = await client.post("/imports/", json=confirm_body(seen))

    assert response.status_code == 422
    assert "needs a Category" in response.json()["detail"]
    assert (await client.get("/transactions/")).json() == [], "nothing was written"


async def test_an_import_is_validated_like_manual_entry(client):
    profile = await create_profile(client)
    seen = await categorised_preview(client, profile)
    sueldo = await default_category(client, "Sueldo", "income")

    response = await client.post(
        "/imports/",
        json=confirm_body(
            seen, **{"Supermercado Coto": {"category_id": sueldo["id"]}}
        ),
    )

    assert response.status_code == 422, "an Expense cannot use an income Category"
    assert (await client.get("/transactions/")).json() == []
    assert (await client.get("/imports/")).json() == []


async def test_a_flagged_duplicate_can_be_unskipped(client):
    profile = await create_profile(client)
    seen = await categorised_preview(client, profile)
    await client.post("/imports/", json=confirm_body(seen))

    again = await preview(client, profile, "mercadopago.csv")
    assert row_named(again, "Supermercado Coto")["status"] == "duplicate"

    await client.post(
        "/imports/",
        json=confirm_body(
            again, **{"Supermercado Coto": {"skip": False}}
        ),
    )

    recorded = (await client.get("/transactions/")).json()
    assert len([t for t in recorded if t["description"] == "Supermercado Coto"]) == 2


async def test_remembering_a_choice_creates_a_categorization_rule(client):
    profile = await create_profile(client)
    farmacia = await default_category(client, "Salud", "expense")
    sueldo = await default_category(client, "Sueldo", "income")
    seen = await preview(client, profile, "mercadopago.xlsx")

    await client.post(
        "/imports/",
        json=confirm_body(
            seen,
            **{
                "Farmacia del Pueblo": {
                    "category_id": farmacia["id"],
                    "remember": {"pattern": "farmacia"},
                },
                "Sueldo": {"category_id": sueldo["id"]},
            },
        ),
    )

    rules = (await client.get("/categorization-rules/")).json()
    assert [(r["pattern"], r["category_id"], r["origin"]) for r in rules] == [
        ("farmacia", farmacia["id"], "manual")
    ]


async def test_a_file_whose_rows_were_all_skipped_is_still_recorded(client):
    """Story 49: every confirmed import is recorded, even an empty one."""
    profile = await create_profile(client)
    seen = await preview(client, profile, "mercadopago.csv")
    body = confirm_body(seen)
    for row in body["rows"]:
        row["skip"] = True

    response = await client.post("/imports/", json=body)

    assert response.status_code == 201
    assert response.json()["imported_count"] == 0
    assert response.json()["skipped_count"] == 5
    assert (await client.get("/transactions/")).json() == []


async def test_imports_are_listed_newest_first(client):
    profile = await create_profile(client)
    seen = await categorised_preview(client, profile)
    await client.post("/imports/", json=confirm_body(seen))

    listed = (await client.get("/imports/")).json()

    assert len(listed) == 1
    assert listed[0]["filename"] == "mercadopago.csv"


async def test_undoing_an_import_deletes_the_transactions_it_created(client):
    profile = await create_profile(client)
    seen = await categorised_preview(client, profile)
    created = (await client.post("/imports/", json=confirm_body(seen))).json()

    response = await client.delete(f"/imports/{created['id']}")

    assert response.status_code == 204
    assert (await client.get("/transactions/")).json() == []
    assert (await client.get("/imports/")).json() == []


async def test_undoing_an_import_leaves_everything_else_alone(client):
    from tests.api import create_transaction

    profile = await create_profile(client)
    seen = await categorised_preview(client, profile)
    typed_by_hand = await create_transaction(
        client,
        category_id=(await default_category(client, "Ocio", "expense"))["id"],
    )
    created = (await client.post("/imports/", json=confirm_body(seen))).json()

    await client.delete(f"/imports/{created['id']}")

    assert [t["id"] for t in (await client.get("/transactions/")).json()] == [
        typed_by_hand["id"]
    ]


async def test_an_import_that_does_not_exist_returns_404(client):
    assert (await client.delete(f"/imports/{UNKNOWN}")).status_code == 404


async def test_an_import_under_a_profile_that_does_not_exist_returns_404(client):
    response = await client.post(
        "/imports/",
        json={"profile_id": UNKNOWN, "filename": "x.csv", "rows": []},
    )

    assert response.status_code == 404
