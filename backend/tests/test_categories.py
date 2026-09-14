from tests.api import create_category, create_transaction, default_category

DEFAULT_EXPENSE_CATEGORIES = {
    "Supermercado",
    "Delivery",
    "Alquiler",
    "Servicios",
    "Transporte",
    "Salud",
    "Suscripciones",
    "Ocio",
    "Ropa",
    "Educación",
    "Impuestos",
    "Otros",
}

DEFAULT_INCOME_CATEGORIES = {"Sueldo", "Freelance", "Rendimientos", "Otros"}


def names_of_type(categories: list[dict], type: str) -> set[str]:
    return {c["name"] for c in categories if c["type"] == type}


async def test_a_fresh_database_ships_with_the_default_expense_categories(client):
    response = await client.get("/categories/")

    assert response.status_code == 200
    assert names_of_type(response.json(), "expense") == DEFAULT_EXPENSE_CATEGORIES


async def test_a_fresh_database_ships_with_the_default_income_categories(client):
    response = await client.get("/categories/")

    assert names_of_type(response.json(), "income") == DEFAULT_INCOME_CATEGORIES


async def test_the_default_categories_are_marked_as_defaults(client):
    response = await client.get("/categories/")

    assert all(category["is_default"] for category in response.json())


async def test_every_category_is_either_an_expense_or_an_income_category(client):
    created = await create_category(client, name="Mascotas", type="expense")

    assert created["type"] == "expense"

    read = await client.get(f"/categories/{created['id']}")
    assert read.json()["type"] == "expense"


async def test_a_category_must_state_its_type(client):
    response = await client.post(
        "/categories/", json={"name": "Mascotas", "color": "#123456"}
    )

    assert response.status_code == 422


async def test_a_default_category_can_be_renamed_and_recolored_like_any_other(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    response = await client.patch(
        f"/categories/{supermercado['id']}",
        json={"name": "Chino", "color": "#ABCDEF"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Chino"
    assert response.json()["color"] == "#ABCDEF"


async def test_a_default_category_can_be_deleted_like_any_other(client):
    ocio = await default_category(client, "Ocio", "expense")

    response = await client.delete(f"/categories/{ocio['id']}")

    assert response.status_code == 204
    assert "Ocio" not in names_of_type(
        (await client.get("/categories/")).json(), "expense"
    )


async def test_a_category_that_still_classifies_transactions_cannot_be_deleted(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_transaction(client, category_id=supermercado["id"])

    response = await client.delete(f"/categories/{supermercado['id']}")

    assert response.status_code == 409


async def test_a_category_in_use_cannot_change_type(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_transaction(client, category_id=supermercado["id"])

    response = await client.patch(
        f"/categories/{supermercado['id']}", json={"type": "income"}
    )

    assert response.status_code == 409
    read = await client.get(f"/categories/{supermercado['id']}")
    assert read.json()["type"] == "expense"


async def test_an_unused_category_can_change_type(client):
    category = await create_category(client, name="Varios", type="expense")

    response = await client.patch(
        f"/categories/{category['id']}", json={"type": "income"}
    )

    assert response.status_code == 200
    assert response.json()["type"] == "income"


async def test_a_category_that_does_not_exist_returns_404(client):
    unknown = "00000000-0000-0000-0000-000000000000"

    assert (await client.get(f"/categories/{unknown}")).status_code == 404
    assert (
        await client.patch(f"/categories/{unknown}", json={"name": "X"})
    ).status_code == 404
    assert (await client.delete(f"/categories/{unknown}")).status_code == 404


async def test_a_categorys_name_cannot_be_blanked(client):
    ocio = await default_category(client, "Ocio", "expense")

    response = await client.patch(f"/categories/{ocio['id']}", json={"name": None})

    assert response.status_code == 422
