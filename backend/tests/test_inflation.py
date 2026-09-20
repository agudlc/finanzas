"""
The Inflation Index: the published IPC, and the user's own values over it.

TODAY is the 15th of March 2026 and the fake series carries November 2025 to
February 2026, so "the month being lived" is March and "the newest published
month" is February.
"""

from decimal import Decimal


async def values_in(client, **params) -> dict[str, str]:
    """The listed months, as {"2026-02": "1.659"}."""
    response = await client.get("/inflation-indexes/", params=params)
    response.raise_for_status()
    return {row["month"][:7]: row["value"] for row in response.json()}


async def test_a_month_comes_from_the_official_series(client):
    response = await client.get(
        "/inflation-indexes/", params={"from_month": "2026-02", "to_month": "2026-02"}
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": response.json()[0]["id"],
            "name": "IPC",
            "month": "2026-02-01",
            "value": "1.659",
            "source": "api",
            "updated_at": response.json()[0]["updated_at"],
        }
    ]


async def test_the_range_defaults_to_the_last_twelve_months(client):
    response = await client.get("/inflation-indexes/")

    months = [row["month"] for row in response.json()]
    assert months == ["2025-11-01", "2025-12-01", "2026-01-01", "2026-02-01"]


async def test_the_range_is_answered_in_order_by_month(client):
    values = await values_in(client, from_month="2025-12", to_month="2026-02")

    assert list(values) == ["2025-12", "2026-01", "2026-02"]
    assert values == {"2025-12": "2.100", "2026-01": "1.900", "2026-02": "1.659"}


async def test_a_range_that_ends_before_it_starts_is_refused(client):
    response = await client.get(
        "/inflation-indexes/", params={"from_month": "2026-02", "to_month": "2026-01"}
    )

    assert response.status_code == 422


async def test_a_month_that_is_not_a_month_is_refused(client):
    response = await client.get(
        "/inflation-indexes/", params={"from_month": "2026-13"}
    )

    assert response.status_code == 422


async def test_a_value_can_be_typed_by_hand(client):
    response = await client.put(
        "/inflation-indexes/2026-02", json={"value": "2.000"}
    )

    assert response.status_code == 200
    assert response.json()["month"] == "2026-02-01"
    assert response.json()["value"] == "2.000"
    assert response.json()["source"] == "manual"


async def test_a_hand_entered_value_wins_over_the_published_one(client):
    await client.put("/inflation-indexes/2026-02", json={"value": "2.000"})

    response = await client.get(
        "/inflation-indexes/", params={"from_month": "2026-02", "to_month": "2026-02"}
    )

    assert response.json()[0]["value"] == "2.000"
    assert response.json()[0]["source"] == "manual"


async def test_a_fetch_never_overwrites_a_hand_entered_value(client, index_source):
    """The months around it are missing, so listing them does go and fetch."""
    await client.put("/inflation-indexes/2026-02", json={"value": "2.000"})

    values = await values_in(client, from_month="2025-11", to_month="2026-02")

    assert index_source.fetches == 1, "the series was read"
    assert values["2026-01"] == "1.900", "the fetched months were stored"
    assert values["2026-02"] == "2.000", "the hand-entered month was left alone"


async def test_a_hand_entered_value_can_be_corrected(client):
    await client.put("/inflation-indexes/2026-02", json={"value": "2.000"})

    response = await client.put(
        "/inflation-indexes/2026-02", json={"value": "2.500"}
    )

    assert response.json()["value"] == "2.500"
    values = await values_in(client, from_month="2026-02", to_month="2026-02")
    assert values == {"2026-02": "2.500"}


async def test_a_month_the_series_does_not_publish_can_still_be_typed(client):
    await client.put("/inflation-indexes/2026-03", json={"value": "1.800"})

    values = await values_in(client, from_month="2026-03", to_month="2026-03")

    assert values == {"2026-03": "1.800"}


async def test_stored_months_are_not_fetched_again(client, index_source):
    await values_in(client, from_month="2025-11", to_month="2026-02")
    index_source.fail_with("datos.gob.ar is down")

    values = await values_in(client, from_month="2025-11", to_month="2026-02")

    assert index_source.fetches == 1, "the second read did not ask again"
    assert values["2026-02"] == "1.659"


async def test_one_fetch_answers_every_missing_month(client, index_source):
    await values_in(client, from_month="2025-11", to_month="2026-02")

    assert index_source.fetches == 1


async def test_the_month_being_lived_is_not_a_reason_to_fetch_again(
    client, index_source
):
    """March has no published IPC yet, so its absence is expected, not a gap."""
    await values_in(client, from_month="2026-02", to_month="2026-03")

    values = await values_in(client, from_month="2026-02", to_month="2026-03")

    assert index_source.fetches == 1
    assert "2026-03" not in values


async def test_a_month_the_series_will_never_carry_is_asked_for_once(
    client, index_source
):
    """The IPC series starts long after 2020, so those gaps never close."""
    await values_in(client, from_month="2020-01", to_month="2020-06")

    await values_in(client, from_month="2020-01", to_month="2020-06")

    assert index_source.fetches == 1, "the second read did not ask again"


async def test_the_series_is_asked_again_while_last_month_is_missing(
    client, index_source
):
    """February's IPC is not out yet: that is worth coming back for."""
    index_source.points = index_source.points[:-1]

    await values_in(client, from_month="2025-11", to_month="2026-02")
    await values_in(client, from_month="2025-11", to_month="2026-02")

    assert index_source.fetches == 2


async def test_a_series_that_cannot_be_read_leaves_the_months_unknown(
    client, index_source
):
    index_source.fail_with("datos.gob.ar is down")

    response = await client.get("/inflation-indexes/")

    assert response.status_code == 200
    assert response.json() == []


async def test_a_stale_series_counts_as_unavailable(client, index_source):
    """Nothing newer than November, in the middle of March: it has stopped."""
    index_source.points = [(index_source.points[0][0], Decimal("2.400"))]

    response = await client.get("/inflation-indexes/")

    assert response.json() == [], "a series that has stopped is not stored"


async def test_an_empty_series_counts_as_unavailable(client, index_source):
    index_source.points = []

    response = await client.get("/inflation-indexes/")

    assert response.json() == []


async def test_a_hand_entered_value_survives_the_series_being_unreachable(
    client, index_source
):
    await client.put("/inflation-indexes/2026-02", json={"value": "2.000"})
    index_source.fail_with("datos.gob.ar is down")

    values = await values_in(client, from_month="2026-02", to_month="2026-02")

    assert values == {"2026-02": "2.000"}


async def test_an_index_the_app_cannot_fetch_lives_entirely_by_hand(
    client, index_source
):
    await client.put(
        "/inflation-indexes/2026-02", json={"value": "3.100", "name": "ICL"}
    )

    values = await values_in(
        client, from_month="2026-02", to_month="2026-02", name="ICL"
    )

    assert values == {"2026-02": "3.100"}
    assert index_source.fetches == 0, "there is no series to ask for"


async def test_an_absurd_value_is_refused(client):
    response = await client.put(
        "/inflation-indexes/2026-02", json={"value": "5000"}
    )

    assert response.status_code == 422
