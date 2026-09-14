from decimal import Decimal

from app.models.enums import RateType
from tests.conftest import TODAY


async def test_todays_rate_comes_from_the_rate_source(client):
    response = await client.get("/settings/rate", params={"rate_type": "blue"})

    assert response.status_code == 200
    assert response.json() == {
        "rate_type": "blue",
        "date": TODAY.isoformat(),
        "value": "1200.0000",
    }


async def test_the_rate_type_defaults_to_the_settings_default(client):
    await client.patch("/settings/", json={"default_rate_type": "mep"})

    response = await client.get("/settings/rate")

    assert response.json()["rate_type"] == "mep"
    assert response.json()["value"] == "1100.0000"


async def test_a_past_date_is_answered_from_the_stored_snapshot(client, clock,
                                                               rate_source):
    clock.date = TODAY.replace(day=10)
    await client.get("/settings/rate", params={"rate_type": "blue"})

    clock.date = TODAY
    rate_source.rates[RateType.blue] = Decimal("9999.00")

    today = await client.get("/settings/rate", params={"rate_type": "blue"})
    assert today.json()["value"] == "9999.0000", "the rate source did move"

    response = await client.get(
        "/settings/rate", params={"rate_type": "blue", "date": "2026-03-10"}
    )

    assert response.json() == {
        "rate_type": "blue",
        "date": "2026-03-10",
        "value": "1200.0000",
    }


async def test_a_past_date_falls_back_to_the_closest_earlier_snapshot(client, clock):
    clock.date = TODAY.replace(day=10)
    await client.get("/settings/rate", params={"rate_type": "blue"})

    clock.date = TODAY
    response = await client.get(
        "/settings/rate", params={"rate_type": "blue", "date": "2026-03-13"}
    )

    assert response.status_code == 200
    assert response.json()["date"] == "2026-03-10"
    assert response.json()["value"] == "1200.0000"


async def test_a_past_date_with_no_snapshot_at_all_returns_404(client):
    response = await client.get(
        "/settings/rate", params={"rate_type": "blue", "date": "2026-03-01"}
    )

    assert response.status_code == 404


async def test_a_rate_type_that_is_not_published_returns_404(client):
    response = await client.get("/settings/rate", params={"rate_type": "manual"})

    assert response.status_code == 404
