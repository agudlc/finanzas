"""Rules learned from the user's choices, so repeat merchants need no work."""

from tests.api import default_category

UNKNOWN = "00000000-0000-0000-0000-000000000000"


async def create_rule(client, pattern, category) -> dict:
    response = await client.post(
        "/categorization-rules/",
        json={"pattern": pattern, "category_id": category["id"]},
    )
    response.raise_for_status()
    return response.json()


async def test_a_rule_maps_a_pattern_to_a_category(client):
    delivery = await default_category(client, "Delivery", "expense")

    rule = await create_rule(client, "pedidosya", delivery)

    assert rule["pattern"] == "pedidosya"
    assert rule["category_id"] == delivery["id"]
    assert rule["origin"] == "manual"


async def test_rules_are_listed_longest_pattern_first(client):
    delivery = await default_category(client, "Delivery", "expense")
    ocio = await default_category(client, "Ocio", "expense")
    await create_rule(client, "mercado", ocio)
    await create_rule(client, "mercado libre", delivery)

    listed = (await client.get("/categorization-rules/")).json()

    assert [rule["pattern"] for rule in listed] == ["mercado libre", "mercado"]


async def test_a_rule_is_edited_and_deleted(client):
    delivery = await default_category(client, "Delivery", "expense")
    ocio = await default_category(client, "Ocio", "expense")
    rule = await create_rule(client, "pedidosya", delivery)

    edited = await client.patch(
        f"/categorization-rules/{rule['id']}", json={"category_id": ocio["id"]}
    )
    assert edited.status_code == 200
    assert edited.json()["category_id"] == ocio["id"]

    assert (
        await client.delete(f"/categorization-rules/{rule['id']}")
    ).status_code == 204
    assert (await client.get("/categorization-rules/")).json() == []


async def test_the_same_pattern_is_not_mapped_twice(client):
    delivery = await default_category(client, "Delivery", "expense")
    await create_rule(client, "pedidosya", delivery)

    response = await client.post(
        "/categorization-rules/",
        json={"pattern": "pedidosya", "category_id": delivery["id"]},
    )

    assert response.status_code == 409


async def test_the_same_pattern_is_not_mapped_twice_whatever_its_case(client):
    """Matching ignores case, so those two patterns are one rule."""
    delivery = await default_category(client, "Delivery", "expense")
    await create_rule(client, "pedidosya", delivery)

    response = await client.post(
        "/categorization-rules/",
        json={"pattern": "PedidosYa", "category_id": delivery["id"]},
    )

    assert response.status_code == 409


async def test_a_rule_cannot_point_at_a_category_that_does_not_exist(client):
    response = await client.post(
        "/categorization-rules/",
        json={"pattern": "pedidosya", "category_id": UNKNOWN},
    )

    assert response.status_code == 404


async def test_a_rule_that_does_not_exist_returns_404(client):
    assert (
        await client.patch(f"/categorization-rules/{UNKNOWN}", json={"pattern": "x"})
    ).status_code == 404
    assert (
        await client.delete(f"/categorization-rules/{UNKNOWN}")
    ).status_code == 404
