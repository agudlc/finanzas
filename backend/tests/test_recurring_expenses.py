"""Recurring Expenses: the templates, before anything suggests them."""

from tests.api import create_category, default_category

UNKNOWN = "00000000-0000-0000-0000-000000000000"


def recurring_body(**fields) -> dict:
    return {
        "description": "Alquiler",
        "reference_amount": "450000.00",
        "expected_day": 5,
        "is_fixed": True,
        **fields,
    }


async def create_recurring(client, **fields) -> dict:
    if "category_id" not in fields:
        fields["category_id"] = (
            await default_category(client, "Alquiler", "expense")
        )["id"]
    response = await client.post("/recurring-expenses/", json=recurring_body(**fields))
    response.raise_for_status()
    return response.json()


async def test_a_recurring_expense_keeps_what_it_was_given(client):
    alquiler = await default_category(client, "Alquiler", "expense")

    template = await create_recurring(client, category_id=alquiler["id"])

    assert template["description"] == "Alquiler"
    assert template["reference_amount"] == "450000.00"
    assert template["expected_day"] == 5
    assert template["category_id"] == alquiler["id"]
    assert template["currency"] == "ARS"
    assert template["is_fixed"] is True
    assert template["is_active"] is True


async def test_a_recurring_expense_is_listed_and_can_be_read_back(client):
    template = await create_recurring(client)

    listed = (await client.get("/recurring-expenses/")).json()
    read = await client.get(f"/recurring-expenses/{template['id']}")

    assert [one["id"] for one in listed] == [template["id"]]
    assert read.status_code == 200
    assert read.json() == template


async def test_a_recurring_expense_can_be_edited(client):
    template = await create_recurring(client)

    response = await client.patch(
        f"/recurring-expenses/{template['id']}",
        json={"reference_amount": "520000.00", "expected_day": 10},
    )

    assert response.status_code == 200
    assert response.json()["reference_amount"] == "520000.00"
    assert response.json()["expected_day"] == 10
    assert response.json()["description"] == "Alquiler", "untouched fields stay"


async def test_a_recurring_expense_can_be_held_in_usd(client):
    template = await create_recurring(
        client, currency="USD", reference_amount="120.00"
    )

    assert template["currency"] == "USD"
    assert template["reference_amount"] == "120.00"


async def test_deactivating_a_recurring_expense_keeps_it(client):
    template = await create_recurring(client)

    paused = await client.patch(
        f"/recurring-expenses/{template['id']}", json={"is_active": False}
    )

    assert paused.json()["is_active"] is False
    assert [one["id"] for one in (await client.get("/recurring-expenses/")).json()] == [
        template["id"]
    ], "pausing a template is not deleting it"


async def test_a_deactivated_recurring_expense_can_be_reactivated(client):
    template = await create_recurring(client)
    await client.patch(
        f"/recurring-expenses/{template['id']}", json={"is_active": False}
    )

    resumed = await client.patch(
        f"/recurring-expenses/{template['id']}", json={"is_active": True}
    )

    assert resumed.status_code == 200
    assert resumed.json()["is_active"] is True


async def test_a_recurring_expense_can_be_deleted(client):
    template = await create_recurring(client)

    response = await client.delete(f"/recurring-expenses/{template['id']}")

    assert response.status_code == 204
    assert (await client.get("/recurring-expenses/")).json() == []


async def test_a_recurring_expense_uses_an_expense_category(client):
    sueldo = await default_category(client, "Sueldo", "income")

    response = await client.post(
        "/recurring-expenses/", json=recurring_body(category_id=sueldo["id"])
    )

    assert response.status_code == 422
    assert "Sueldo" in response.json()["detail"]
    assert (await client.get("/recurring-expenses/")).json() == []


async def test_a_recurring_expense_cannot_be_moved_to_an_income_category(client):
    template = await create_recurring(client)
    sueldo = await default_category(client, "Sueldo", "income")

    response = await client.patch(
        f"/recurring-expenses/{template['id']}", json={"category_id": sueldo["id"]}
    )

    assert response.status_code == 422
    read = (await client.get(f"/recurring-expenses/{template['id']}")).json()
    assert read["category_id"] == template["category_id"]


async def test_a_recurring_expense_can_be_moved_to_another_expense_category(client):
    template = await create_recurring(client)
    gimnasio = await create_category(client, name="Gimnasio")

    response = await client.patch(
        f"/recurring-expenses/{template['id']}", json={"category_id": gimnasio["id"]}
    )

    assert response.status_code == 200
    assert response.json()["category_id"] == gimnasio["id"]


async def test_a_category_that_does_not_exist_returns_404(client):
    response = await client.post(
        "/recurring-expenses/", json=recurring_body(category_id=UNKNOWN)
    )

    assert response.status_code == 404


async def test_moving_to_a_category_that_does_not_exist_returns_404(client):
    template = await create_recurring(client)

    response = await client.patch(
        f"/recurring-expenses/{template['id']}", json={"category_id": UNKNOWN}
    )

    assert response.status_code == 404


async def test_a_category_a_recurring_expense_uses_cannot_be_deleted(client):
    gimnasio = await create_category(client, name="Gimnasio")
    await create_recurring(client, category_id=gimnasio["id"])

    response = await client.delete(f"/categories/{gimnasio['id']}")

    assert response.status_code == 409
    assert (await client.get(f"/categories/{gimnasio['id']}")).status_code == 200


async def test_a_category_a_recurring_expense_uses_cannot_become_an_income_one(client):
    gimnasio = await create_category(client, name="Gimnasio")
    await create_recurring(client, category_id=gimnasio["id"])

    response = await client.patch(
        f"/categories/{gimnasio['id']}", json={"type": "income"}
    )

    assert response.status_code == 409, (
        "the type cannot move out from under a template that may only use an "
        "expense Category"
    )


async def test_the_expected_day_is_a_day_of_the_month(client):
    for day in (0, 32):
        response = await client.post(
            "/recurring-expenses/", json=recurring_body(expected_day=day)
        )
        assert response.status_code == 422, f"day {day} is not a day of the month"


async def test_the_expected_day_stays_a_day_of_the_month_when_edited(client):
    template = await create_recurring(client)

    response = await client.patch(
        f"/recurring-expenses/{template['id']}", json={"expected_day": 32}
    )

    assert response.status_code == 422


async def test_the_reference_amount_is_positive(client):
    response = await client.post(
        "/recurring-expenses/", json=recurring_body(reference_amount="-1000.00")
    )

    assert response.status_code == 422


async def test_a_recurring_expense_that_does_not_exist_returns_404(client):
    assert (await client.get(f"/recurring-expenses/{UNKNOWN}")).status_code == 404
    assert (
        await client.patch(
            f"/recurring-expenses/{UNKNOWN}", json={"expected_day": 3}
        )
    ).status_code == 404
    assert (await client.delete(f"/recurring-expenses/{UNKNOWN}")).status_code == 404
