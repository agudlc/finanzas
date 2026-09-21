async def test_settings_start_with_ars_as_the_display_currency(client):
    response = await client.get("/settings/")

    assert response.status_code == 200
    assert response.json()["display_currency"] == "ARS"


async def test_settings_start_with_the_card_rate_for_estimates(client):
    response = await client.get("/settings/")

    assert response.json()["default_rate_type"] == "card"


async def test_the_display_currency_can_be_changed(client):
    response = await client.patch("/settings/", json={"display_currency": "USD"})

    assert response.status_code == 200
    assert response.json()["display_currency"] == "USD"
    assert (await client.get("/settings/")).json()["display_currency"] == "USD"


async def test_the_default_rate_type_can_be_changed(client):
    await client.patch("/settings/", json={"default_rate_type": "blue"})

    assert (await client.get("/settings/")).json()["default_rate_type"] == "blue"


async def test_settings_start_with_a_quarter_of_history_for_the_agent(client):
    response = await client.get("/settings/")

    assert response.json()["agent_lookback"] == "quarter", (
        "the smaller of the two: history leaving the app is the user's to widen"
    )


async def test_the_agent_lookback_can_be_widened_to_a_year(client):
    await client.patch("/settings/", json={"agent_lookback": "year"})

    assert (await client.get("/settings/")).json()["agent_lookback"] == "year"


async def test_one_setting_can_be_changed_without_touching_the_others(client):
    await client.patch("/settings/", json={"default_rate_type": "mep"})

    settings = (await client.get("/settings/")).json()
    assert settings == {
        "display_currency": "ARS",
        "default_rate_type": "mep",
        "agent_lookback": "quarter",
    }


async def test_a_fresh_database_already_holds_the_settings_record(client):
    """The migrations seed it, so it is never conjured up by the first read."""
    response = await client.get("/settings/")

    assert response.json() == {
        "display_currency": "ARS",
        "default_rate_type": "card",
        "agent_lookback": "quarter",
    }


async def test_the_display_currency_cannot_be_blanked(client):
    response = await client.patch("/settings/", json={"display_currency": None})

    assert response.status_code == 422
