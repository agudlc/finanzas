"""An Import Profile is written with a real export in front of the user."""

from tests.api_imports import FIXTURES, LEMON, MERCADO_PAGO, create_profile

UNKNOWN = "00000000-0000-0000-0000-000000000000"


async def test_a_profile_holds_everything_needed_to_read_a_source(client):
    profile = await create_profile(client)

    assert profile["source"] == "mercadopago"
    assert profile["column_mapping"]["debit"] == "Débito"
    assert profile["date_format"] == "%d/%m/%Y"
    assert profile["number_format"] == "comma_decimal"
    assert profile["sign_convention"] == "debit_credit_columns"
    assert profile["ignore_patterns"] == ["Transferencia", "Cripto"]


async def test_profiles_are_listed_edited_and_deleted(client):
    profile = await create_profile(client)

    assert [p["id"] for p in (await client.get("/import-profiles/")).json()] == [
        profile["id"]
    ]

    edited = await client.patch(
        f"/import-profiles/{profile['id']}",
        json={"ignore_patterns": ["Transferencia"]},
    )
    assert edited.status_code == 200
    assert edited.json()["ignore_patterns"] == ["Transferencia"]

    assert (
        await client.delete(f"/import-profiles/{profile['id']}")
    ).status_code == 204
    assert (await client.get("/import-profiles/")).json() == []


async def test_two_profiles_cannot_share_a_name(client):
    await create_profile(client)

    response = await client.post("/import-profiles/", json=MERCADO_PAGO)

    assert response.status_code == 409


async def test_a_debit_credit_profile_needs_both_columns(client):
    broken = {
        **MERCADO_PAGO,
        "column_mapping": {"date": "Fecha", "description": "Descripción",
                           "debit": "Débito"},
    }

    response = await client.post("/import-profiles/", json=broken)

    assert response.status_code == 422


async def test_a_single_amount_profile_needs_its_amount_column(client):
    broken = {
        **LEMON,
        "column_mapping": {"date": "fecha", "description": "detalle"},
    }

    response = await client.post("/import-profiles/", json=broken)

    assert response.status_code == 422


async def test_a_profile_that_does_not_exist_returns_404(client):
    assert (await client.get(f"/import-profiles/{UNKNOWN}")).status_code == 404
    assert (
        await client.patch(f"/import-profiles/{UNKNOWN}", json={"source": "x"})
    ).status_code == 404
    assert (await client.delete(f"/import-profiles/{UNKNOWN}")).status_code == 404


async def test_a_files_columns_are_offered_so_a_profile_is_written_from_it(client):
    """Story 36: setup happens with a real export in front of the user."""
    response = await client.post(
        "/import-profiles/columns",
        files={"file": ("mercadopago.csv", (FIXTURES / "mercadopago.csv").read_bytes())},
    )

    assert response.status_code == 200
    assert response.json() == {
        "filename": "mercadopago.csv",
        "columns": ["Fecha", "Descripción", "Tipo", "Débito", "Crédito"],
    }


async def test_an_xlsx_files_columns_are_read_too(client):
    response = await client.post(
        "/import-profiles/columns",
        files={
            "file": ("mercadopago.xlsx", (FIXTURES / "mercadopago.xlsx").read_bytes())
        },
    )

    assert response.json()["columns"] == [
        "Fecha", "Descripción", "Tipo", "Débito", "Crédito"
    ]


async def test_reading_columns_saves_nothing(client):
    await client.post(
        "/import-profiles/columns",
        files={"file": ("mercadopago.csv", (FIXTURES / "mercadopago.csv").read_bytes())},
    )

    assert (await client.get("/import-profiles/")).json() == []


async def test_a_file_that_is_not_an_export_has_no_columns_to_offer(client):
    response = await client.post(
        "/import-profiles/columns",
        files={"file": ("resumen.pdf", b"%PDF-1.4")},
    )

    assert response.status_code == 422
