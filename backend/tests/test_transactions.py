from tests.api import (
    create_category,
    create_transaction,
    default_category,
    transaction_body,
)

UNKNOWN = "00000000-0000-0000-0000-000000000000"


def usd_fields(**overrides) -> dict:
    return {
        "currency": "USD",
        "exchange_rate": "1500.00",
        "exchange_rate_type": "card",
        "exchange_rate_status": "estimated",
        **overrides,
    }


async def test_an_expense_uses_an_expense_category(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    created = await create_transaction(client, category_id=supermercado["id"])

    assert created["type"] == "expense"
    assert created["category_id"] == supermercado["id"]


async def test_an_expense_cannot_use_an_income_category(client):
    sueldo = await default_category(client, "Sueldo", "income")

    response = await client.post(
        "/transactions/",
        json=transaction_body(type="expense", category_id=sueldo["id"]),
    )

    assert response.status_code == 422


async def test_an_income_cannot_use_an_expense_category(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    response = await client.post(
        "/transactions/",
        json=transaction_body(type="income", category_id=supermercado["id"]),
    )

    assert response.status_code == 422


async def test_a_transaction_cannot_use_a_category_that_does_not_exist(client):
    response = await client.post(
        "/transactions/", json=transaction_body(category_id=UNKNOWN)
    )

    assert response.status_code == 404


async def test_a_transaction_cannot_be_moved_into_a_mismatched_category(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    sueldo = await default_category(client, "Sueldo", "income")
    expense = await create_transaction(client, category_id=supermercado["id"])

    response = await client.patch(
        f"/transactions/{expense['id']}", json={"category_id": sueldo["id"]}
    )

    assert response.status_code == 422


async def test_a_usd_transaction_carries_an_exchange_rate(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    created = await create_transaction(
        client, category_id=supermercado["id"], **usd_fields()
    )

    assert created["exchange_rate"] == "1500.0000"
    assert created["exchange_rate_type"] == "card"
    assert created["exchange_rate_status"] == "estimated"


async def test_an_ars_transaction_carries_no_exchange_rate(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    response = await client.post(
        "/transactions/",
        json=transaction_body(
            category_id=supermercado["id"],
            currency="ARS",
            exchange_rate="1500.00",
            exchange_rate_type="card",
            exchange_rate_status="estimated",
        ),
    )

    assert response.status_code == 422


async def test_an_estimated_exchange_rate_is_confirmed_with_the_real_figure(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    expense = await create_transaction(
        client, category_id=supermercado["id"], **usd_fields()
    )

    response = await client.patch(
        f"/transactions/{expense['id']}",
        json={"exchange_rate": "1620.50", "exchange_rate_status": "confirmed"},
    )

    assert response.status_code == 200
    assert response.json()["exchange_rate"] == "1620.5000"
    assert response.json()["exchange_rate_status"] == "confirmed"


async def test_a_confirmed_exchange_rate_never_changes_again(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    expense = await create_transaction(
        client,
        category_id=supermercado["id"],
        **usd_fields(exchange_rate_status="confirmed"),
    )

    response = await client.patch(
        f"/transactions/{expense['id']}", json={"exchange_rate": "1620.50"}
    )

    assert response.status_code == 409
    read = await client.get(f"/transactions/{expense['id']}")
    assert read.json()["exchange_rate"] == "1500.0000"


async def test_a_confirmed_exchange_rate_cannot_be_dropped_by_switching_currency(
    client,
):
    supermercado = await default_category(client, "Supermercado", "expense")
    expense = await create_transaction(
        client,
        category_id=supermercado["id"],
        **usd_fields(exchange_rate_status="confirmed"),
    )

    response = await client.patch(
        f"/transactions/{expense['id']}",
        json={
            "currency": "ARS",
            "exchange_rate": None,
            "exchange_rate_type": None,
            "exchange_rate_status": None,
        },
    )

    assert response.status_code == 409


async def test_an_amount_is_confirmed_unless_it_is_said_to_be_an_estimate(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    confirmed = await create_transaction(client, category_id=supermercado["id"])
    estimated = await create_transaction(
        client, category_id=supermercado["id"], amount_status="estimated"
    )

    assert confirmed["amount_status"] == "confirmed"
    assert estimated["amount_status"] == "estimated"


async def test_an_income_cannot_have_a_negative_amount(client):
    sueldo = await default_category(client, "Sueldo", "income")

    response = await client.post(
        "/transactions/",
        json=transaction_body(
            type="income", category_id=sueldo["id"], amount="-1000.00"
        ),
    )

    assert response.status_code == 422


async def test_a_refund_is_an_expense_with_a_negative_amount(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    purchase = await create_transaction(client, category_id=supermercado["id"])

    refund = await create_transaction(
        client,
        category_id=supermercado["id"],
        amount="-250.00",
        refund_of_id=purchase["id"],
    )

    assert refund["amount"] == "-250.00"
    assert refund["refund_of_id"] == purchase["id"]


async def test_a_refund_is_in_the_same_category_as_the_expense_it_reverses(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    ropa = await default_category(client, "Ropa", "expense")
    purchase = await create_transaction(client, category_id=supermercado["id"])

    response = await client.post(
        "/transactions/",
        json=transaction_body(
            category_id=ropa["id"], amount="-250.00", refund_of_id=purchase["id"]
        ),
    )

    assert response.status_code == 422


async def test_a_refund_cannot_reverse_an_income(client):
    sueldo = await default_category(client, "Sueldo", "income")
    supermercado = await default_category(client, "Supermercado", "expense")
    salary = await create_transaction(
        client, type="income", category_id=sueldo["id"]
    )

    response = await client.post(
        "/transactions/",
        json=transaction_body(
            category_id=supermercado["id"],
            amount="-250.00",
            refund_of_id=salary["id"],
        ),
    )

    assert response.status_code == 422


async def test_a_positive_expense_cannot_claim_to_reverse_another(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    purchase = await create_transaction(client, category_id=supermercado["id"])

    response = await client.post(
        "/transactions/",
        json=transaction_body(
            category_id=supermercado["id"],
            amount="250.00",
            refund_of_id=purchase["id"],
        ),
    )

    assert response.status_code == 422


async def test_a_refund_cannot_reverse_an_expense_that_does_not_exist(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    response = await client.post(
        "/transactions/",
        json=transaction_body(
            category_id=supermercado["id"], amount="-250.00", refund_of_id=UNKNOWN
        ),
    )

    assert response.status_code == 404


async def test_a_cuota_needs_both_its_purchase_and_its_number(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    response = await client.post(
        "/transactions/",
        json=transaction_body(
            category_id=supermercado["id"], installment_purchase_id=UNKNOWN
        ),
    )
    assert response.status_code == 422

    response = await client.post(
        "/transactions/",
        json=transaction_body(category_id=supermercado["id"], installment_number=2),
    )
    assert response.status_code == 422


async def test_a_cuota_cannot_belong_to_a_purchase_that_does_not_exist(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    response = await client.post(
        "/transactions/",
        json=transaction_body(
            category_id=supermercado["id"],
            installment_purchase_id=UNKNOWN,
            installment_number=1,
        ),
    )

    assert response.status_code == 404


async def test_a_transaction_that_does_not_exist_returns_404(client):
    assert (await client.get(f"/transactions/{UNKNOWN}")).status_code == 404
    assert (
        await client.patch(f"/transactions/{UNKNOWN}", json={"notes": "x"})
    ).status_code == 404
    assert (await client.delete(f"/transactions/{UNKNOWN}")).status_code == 404


async def test_a_transaction_is_listed_read_and_deleted(client):
    category = await create_category(client, name="Mascotas", type="expense")
    created = await create_transaction(
        client, category_id=category["id"], description="Veterinaria"
    )

    listed = await client.get("/transactions/")
    assert [t["id"] for t in listed.json()] == [created["id"]]

    assert (await client.get(f"/transactions/{created['id']}")).json()[
        "description"
    ] == "Veterinaria"

    assert (await client.delete(f"/transactions/{created['id']}")).status_code == 204
    assert (await client.get("/transactions/")).json() == []


async def test_a_required_field_cannot_be_blanked(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    expense = await create_transaction(client, category_id=supermercado["id"])

    for field in ("date", "amount", "currency", "type", "category_id"):
        response = await client.patch(
            f"/transactions/{expense['id']}", json={field: None}
        )
        assert response.status_code == 422, field
