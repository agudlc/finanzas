"""
The agent proposing a change, and everything that keeps a bad one out.

Every test here drives the propose tools the way the model would: the scripted
client calls one by name, the Review runs, and what comes back is read either
out of the Inbox — the proposal waiting for the user — or out of the transcript
the run left on the Review, which is what the model was told.

The point of the refusals is that the Inbox never sees them. A proposal that
would fail when the user pressed "Aceptar" is refused where it is made, so the
assertions come in pairs: the model was told what was wrong, and nothing was
stored.
"""

from app.llm import Reply, ToolCall
from tests.api import create_category, create_transaction, default_category
from tests.test_agent_reviews import agent_review, finished, insights
from tests.test_categorization_rules import create_rule
from tests.test_recurring_expenses import create_recurring
from tests.test_reviews import suggestions
from tests.test_suggestions import accept, reject, transactions

UNKNOWN = "00000000-0000-0000-0000-000000000000"


async def proposes(client, llm, tool: str, **arguments) -> str:
    """What one propose tool answers when the model calls it, in its own words."""
    llm.will(
        Reply(tool_calls=(ToolCall(id="call-0", name=tool, arguments=arguments),)),
        Reply(text="Listo."),
    )
    review = await finished(client, await agent_review(client))
    [answer] = review["transcript"][2]["content"]
    return answer


async def recategorizes(client, llm, **arguments) -> str:
    """"Eso está mal categorizado": the agent's first kind of proposal."""
    return await proposes(
        client,
        llm,
        "propose_recategorize_transaction",
        rationale="Pedidos Ya es delivery, no supermercado.",
        **arguments,
    )


async def misfiled(client) -> tuple[dict, dict]:
    """A delivery Expense filed under Supermercado, and where it belongs."""
    supermercado = await default_category(client, "Supermercado", "expense")
    delivery = await default_category(client, "Delivery", "expense")
    expense = await create_transaction(
        client,
        category_id=supermercado["id"],
        amount="45000.00",
        description="Pedidos Ya",
    )
    return expense, delivery


async def test_the_agent_is_offered_one_propose_tool_per_kind(client, llm):
    await agent_review(client)

    offered = {tool["name"] for tool in llm.tools[-1]}
    assert {
        "propose_add_transaction",
        "propose_set_budget",
        "propose_recategorize_transaction",
        "propose_add_categorization_rule",
        "propose_add_recurring_expense",
    } <= offered, "one tool per shape of change the app knows how to apply"


async def test_a_propose_tool_asks_for_the_kinds_payload_and_a_rationale(
    client, llm
):
    await agent_review(client)

    [tool] = [
        one
        for one in llm.tools[-1]
        if one["name"] == "propose_recategorize_transaction"
    ]
    assert set(tool["input_schema"]["required"]) == {
        "transaction_id",
        "category_id",
        "rationale",
    }
    assert tool["input_schema"]["additionalProperties"] is False, (
        "a field the kind does not name is not a field of the proposal"
    )


async def test_a_proposed_recategorization_waits_in_the_inbox(client, llm):
    expense, delivery = await misfiled(client)

    await recategorizes(
        client, llm, transaction_id=expense["id"], category_id=delivery["id"]
    )

    [proposal] = await suggestions(client)
    assert proposal["kind"] == "recategorize_transaction"
    assert proposal["status"] == "pending"
    assert proposal["payload"] == {
        "transaction_id": expense["id"],
        "category_id": delivery["id"],
    }
    assert proposal["rationale"] == "Pedidos Ya es delivery, no supermercado."


async def test_a_proposal_is_about_the_reviews_month_and_expires_with_it(
    client, llm
):
    expense, delivery = await misfiled(client)

    await recategorizes(
        client, llm, transaction_id=expense["id"], category_id=delivery["id"]
    )

    [proposal] = await suggestions(client)
    assert proposal["month"] == "2026-03-01"
    assert proposal["expires_on"] == "2026-03-31"


async def test_accepting_a_recategorization_moves_the_transaction(client, llm):
    expense, delivery = await misfiled(client)
    await recategorizes(
        client, llm, transaction_id=expense["id"], category_id=delivery["id"]
    )
    [proposal] = await suggestions(client)

    response = await accept(client, proposal["id"])

    assert response.status_code == 200
    assert response.json()["result_id"] == expense["id"]
    [moved] = await transactions(client)
    assert moved["id"] == expense["id"]
    assert moved["category_id"] == delivery["id"]
    assert moved["amount"] == "45000.00", "only the Category moves"
    assert moved["description"] == "Pedidos Ya"


async def test_rejecting_a_recategorization_leaves_the_transaction_alone(
    client, llm
):
    expense, delivery = await misfiled(client)
    await recategorizes(
        client, llm, transaction_id=expense["id"], category_id=delivery["id"]
    )
    [proposal] = await suggestions(client)

    await reject(client, proposal["id"], reason="no, era el súper igual")

    [untouched] = await transactions(client)
    assert untouched["category_id"] == expense["category_id"]


async def test_a_category_of_the_wrong_type_is_refused_and_stores_nothing(
    client, llm
):
    expense, _ = await misfiled(client)
    sueldo = await default_category(client, "Sueldo", "income")

    answer = await recategorizes(
        client, llm, transaction_id=expense["id"], category_id=sueldo["id"]
    )

    assert answer["is_error"] is True
    assert "income Category 'Sueldo'" in answer["content"]
    assert await suggestions(client) == [], "the Inbox never sees a refusal"


async def test_a_transaction_that_does_not_exist_is_refused(client, llm):
    _, delivery = await misfiled(client)

    answer = await recategorizes(
        client, llm, transaction_id=UNKNOWN, category_id=delivery["id"]
    )

    assert answer["is_error"] is True
    assert "no Transaction with id" in answer["content"]
    assert await suggestions(client) == []


async def test_a_malformed_payload_is_refused_and_stores_nothing(client, llm):
    expense, delivery = await misfiled(client)

    answer = await recategorizes(
        client, llm, transaction_id="ayer", category_id=delivery["id"]
    )

    assert answer["is_error"] is True
    assert "transaction_id" in answer["content"]
    assert await suggestions(client) == []


async def test_a_field_the_kind_does_not_name_is_refused(client, llm):
    expense, delivery = await misfiled(client)

    answer = await recategorizes(
        client,
        llm,
        transaction_id=expense["id"],
        category_id=delivery["id"],
        amount="45000.00",
    )

    assert answer["is_error"] is True
    assert "amount" in answer["content"]
    assert await suggestions(client) == []


async def test_a_proposal_with_no_rationale_is_refused(client, llm):
    expense, delivery = await misfiled(client)

    answer = await proposes(
        client,
        llm,
        "propose_recategorize_transaction",
        transaction_id=expense["id"],
        category_id=delivery["id"],
    )

    assert answer["is_error"] is True
    assert "rationale" in answer["content"]
    assert await suggestions(client) == [], (
        "the user reads the rationale to decide, so there is no proposal without one"
    )


async def test_proposing_the_same_move_twice_in_a_run_is_refused_once(client, llm):
    expense, delivery = await misfiled(client)
    move = {"transaction_id": expense["id"], "category_id": delivery["id"]}
    llm.will(
        Reply(
            tool_calls=(
                ToolCall(
                    id="call-0",
                    name="propose_recategorize_transaction",
                    arguments={**move, "rationale": "Es delivery."},
                ),
                ToolCall(
                    id="call-1",
                    name="propose_recategorize_transaction",
                    arguments={**move, "rationale": "Lo mismo, dicho de nuevo."},
                ),
            )
        ),
        Reply(text="Listo."),
    )

    review = await finished(client, await agent_review(client))

    first, again = review["transcript"][2]["content"]
    assert "is_error" not in first
    assert again["is_error"] is True
    assert "already been made" in again["content"]
    [proposal] = await suggestions(client)
    assert proposal["rationale"] == "Es delivery."


async def test_a_move_the_user_already_rejected_is_not_proposed_again(client, llm):
    expense, delivery = await misfiled(client)
    await recategorizes(
        client, llm, transaction_id=expense["id"], category_id=delivery["id"]
    )
    [proposal] = await suggestions(client)
    await reject(client, proposal["id"], reason="me gusta contarlo como súper")

    answer = await recategorizes(
        client, llm, transaction_id=expense["id"], category_id=delivery["id"]
    )

    assert answer["is_error"] is True
    assert await suggestions(client) == [], (
        "a Transaction is filed where it is filed, so a no to moving it stands"
    )


async def test_a_refused_proposal_does_not_cost_the_run_its_insights(client, llm):
    expense, _ = await misfiled(client)
    llm.will(
        Reply(
            tool_calls=(
                ToolCall(
                    id="call-0",
                    name="propose_recategorize_transaction",
                    arguments={
                        "transaction_id": expense["id"],
                        "category_id": UNKNOWN,
                        "rationale": "Va acá.",
                    },
                ),
                ToolCall(
                    id="call-1",
                    name="record_insight",
                    arguments={
                        "topic": "Delivery",
                        "body": "Gastaste 45.000 en delivery este mes.",
                    },
                ),
            )
        ),
        Reply(text="Listo."),
    )

    review = await finished(client, await agent_review(client))

    assert review["status"] == "done"
    assert await suggestions(client) == []
    assert [one["topic"] for one in await insights(client)] == ["Delivery"]


async def test_the_agent_can_propose_a_budget_for_a_category(client, llm):
    delivery = await default_category(client, "Delivery", "expense")

    answer = await proposes(
        client,
        llm,
        "propose_set_budget",
        category_id=delivery["id"],
        month="2026-03-01",
        amount="60000.00",
        currency="ARS",
        rationale="Venís gastando 45.000 por mes en delivery.",
    )

    assert "is_error" not in answer
    [proposal] = await suggestions(client)
    assert proposal["kind"] == "set_budget"
    assert proposal["payload"]["amount"] == "60000.00"


async def test_a_budget_for_an_income_category_is_refused(client, llm):
    sueldo = await default_category(client, "Sueldo", "income")

    answer = await proposes(
        client,
        llm,
        "propose_set_budget",
        category_id=sueldo["id"],
        month="2026-03-01",
        amount="60000.00",
        currency="ARS",
        rationale="Para controlar el sueldo.",
    )

    assert answer["is_error"] is True
    assert "income Category" in answer["content"]
    assert await suggestions(client) == []


async def test_a_proposed_expense_in_an_income_category_is_refused(client, llm):
    sueldo = await default_category(client, "Sueldo", "income")

    answer = await proposes(
        client,
        llm,
        "propose_add_transaction",
        description="Spotify",
        category_id=sueldo["id"],
        currency="ARS",
        amount="9000.00",
        date="2026-03-10",
        rationale="Aparece todos los meses.",
    )

    assert answer["is_error"] is True
    assert await suggestions(client) == []


async def test_a_proposal_the_agent_made_is_read_back_in_the_next_brief(
    client, llm
):
    expense, delivery = await misfiled(client)
    await recategorizes(
        client, llm, transaction_id=expense["id"], category_id=delivery["id"]
    )

    llm.will(Reply(text="Nada nuevo."))
    await agent_review(client)

    assert 'move "Pedidos Ya" of 2026-03-15 into Delivery' in llm.brief, (
        "the next Review reads what is waiting, by name, so it does not "
        "propose it again"
    )


async def test_a_rejected_move_is_read_back_by_the_transaction_it_names(
    client, llm
):
    expense, delivery = await misfiled(client)
    await recategorizes(
        client, llm, transaction_id=expense["id"], category_id=delivery["id"]
    )
    [proposal] = await suggestions(client)
    await reject(client, proposal["id"], reason="me gusta contarlo como súper")

    llm.will(Reply(text="Nada nuevo."))
    await agent_review(client)

    assert 'they said no to move "Pedidos Ya" of 2026-03-15 into Delivery' in (
        llm.brief
    ), "two misfiled Transactions moved into the same Category must not read alike"


async def test_a_budget_proposal_for_another_month_is_its_own_proposal(
    client, llm
):
    delivery = await default_category(client, "Delivery", "expense")
    for month, amount in (("2026-03-01", "60000.00"), ("2026-04-01", "66000.00")):
        answer = await proposes(
            client,
            llm,
            "propose_set_budget",
            category_id=delivery["id"],
            month=month,
            amount=amount,
            currency="ARS",
            rationale=f"Para {month}.",
        )
        assert "is_error" not in answer

    assert {one["payload"]["month"] for one in await suggestions(client)} == {
        "2026-03-01",
        "2026-04-01",
    }, "a proposal about April is not the proposal about March"


async def test_the_same_budget_month_is_not_proposed_twice(client, llm):
    delivery = await default_category(client, "Delivery", "expense")
    for amount in ("60000.00", "70000.00"):
        answer = await proposes(
            client,
            llm,
            "propose_set_budget",
            category_id=delivery["id"],
            month="2026-03-01",
            amount=amount,
            currency="ARS",
            rationale=f"Propongo {amount}.",
        )

    assert answer["is_error"] is True
    [proposal] = await suggestions(client)
    assert proposal["payload"]["amount"] == "60000.00"


async def test_a_recategorization_has_no_possible_match(client, llm):
    """Only a proposed payment can already be recorded; a move cannot."""
    expense, delivery = await misfiled(client)

    await recategorizes(
        client, llm, transaction_id=expense["id"], category_id=delivery["id"]
    )

    [proposal] = await suggestions(client)
    assert proposal["possible_match"] is None


async def test_a_category_that_does_not_exist_is_refused(client, llm):
    expense, _ = await misfiled(client)

    answer = await recategorizes(
        client, llm, transaction_id=expense["id"], category_id=UNKNOWN
    )

    assert answer["is_error"] is True
    assert "no Category with id" in answer["content"]
    assert await suggestions(client) == []


async def test_a_move_into_a_category_the_user_made_is_proposed(client, llm):
    expense, _ = await misfiled(client)
    mine = await create_category(client, name="Comida afuera", type="expense")

    await recategorizes(
        client, llm, transaction_id=expense["id"], category_id=mine["id"]
    )

    [proposal] = await suggestions(client)
    assert proposal["payload"]["category_id"] == mine["id"]


# --- add_categorization_rule -----------------------------------------------


async def rules(client) -> list[dict]:
    response = await client.get("/categorization-rules/")
    response.raise_for_status()
    return response.json()


async def learns(client, llm, **arguments) -> str:
    """"Esto siempre va acá": the agent proposing a Categorization Rule."""
    return await proposes(
        client,
        llm,
        "propose_add_categorization_rule",
        rationale="Filaste PedidosYa a mano tres veces este mes.",
        **arguments,
    )


async def test_a_proposed_rule_waits_in_the_inbox(client, llm):
    delivery = await default_category(client, "Delivery", "expense")

    answer = await learns(client, llm, pattern="pedidosya", category_id=delivery["id"])

    assert "is_error" not in answer
    [proposal] = await suggestions(client)
    assert proposal["kind"] == "add_categorization_rule"
    assert proposal["status"] == "pending"
    assert proposal["payload"] == {
        "pattern": "pedidosya",
        "category_id": delivery["id"],
    }
    assert await rules(client) == [], "nothing is learned until the user says so"


async def test_accepting_a_rule_learns_it_as_coming_from_a_suggestion(client, llm):
    delivery = await default_category(client, "Delivery", "expense")
    await learns(client, llm, pattern="pedidosya", category_id=delivery["id"])
    [proposal] = await suggestions(client)

    response = await accept(client, proposal["id"])

    assert response.status_code == 200
    [rule] = await rules(client)
    assert response.json()["result_id"] == rule["id"]
    assert rule["pattern"] == "pedidosya"
    assert rule["category_id"] == delivery["id"]
    assert rule["origin"] == "suggestion", (
        "a rule the user accepted came from a Suggestion, not from their hand"
    )


async def test_accepting_a_rule_leaves_the_transactions_already_recorded_alone(
    client, llm
):
    """A rule reaches forward only: what is recorded stays where it is (ADR-0004)."""
    expense, delivery = await misfiled(client)

    await learns(client, llm, pattern="Pedidos Ya", category_id=delivery["id"])
    [proposal] = await suggestions(client)
    await accept(client, proposal["id"])

    [untouched] = await transactions(client)
    assert untouched["id"] == expense["id"]
    assert untouched["category_id"] == expense["category_id"], (
        "the Expense the pattern matches is not recategorized by learning it"
    )


async def test_an_edited_rule_is_learned_as_the_user_edited_it(client, llm):
    delivery = await default_category(client, "Delivery", "expense")
    ocio = await default_category(client, "Ocio", "expense")
    await learns(client, llm, pattern="pedidosya", category_id=delivery["id"])
    [proposal] = await suggestions(client)

    await accept(client, proposal["id"], category_id=ocio["id"])

    [rule] = await rules(client)
    assert rule["category_id"] == ocio["id"]


async def test_an_edited_rule_is_revalidated(client, llm):
    delivery = await default_category(client, "Delivery", "expense")
    await learns(client, llm, pattern="pedidosya", category_id=delivery["id"])
    [proposal] = await suggestions(client)

    response = await accept(client, proposal["id"], pattern="")

    assert response.status_code == 422
    assert await rules(client) == [], (
        "an edited proposal is no looser than a proposed one"
    )


async def test_a_pattern_already_mapped_is_refused(client, llm):
    delivery = await default_category(client, "Delivery", "expense")
    await create_rule(client, "pedidosya", delivery)

    answer = await learns(client, llm, pattern="PedidosYa", category_id=delivery["id"])

    assert answer["is_error"] is True
    assert "already exists" in answer["content"]
    assert await suggestions(client) == [], (
        "matching ignores case, so that rule is already learned"
    )


async def test_the_same_pattern_is_not_proposed_twice_whatever_its_case(
    client, llm
):
    delivery = await default_category(client, "Delivery", "expense")
    ocio = await default_category(client, "Ocio", "expense")
    await learns(client, llm, pattern="pedidosya", category_id=delivery["id"])

    answer = await learns(client, llm, pattern="PedidosYa", category_id=ocio["id"])

    assert answer["is_error"] is True
    assert "already been made" in answer["content"]
    [proposal] = await suggestions(client)
    assert proposal["payload"]["category_id"] == delivery["id"]


async def test_a_rule_pointing_at_a_category_that_does_not_exist_is_refused(
    client, llm
):
    answer = await learns(client, llm, pattern="pedidosya", category_id=UNKNOWN)

    assert answer["is_error"] is True
    assert "no Category with id" in answer["content"]
    assert await suggestions(client) == []


async def test_a_proposed_rule_is_read_back_in_the_next_brief(client, llm):
    delivery = await default_category(client, "Delivery", "expense")
    await learns(client, llm, pattern="pedidosya", category_id=delivery["id"])

    llm.will(Reply(text="Nada nuevo."))
    await agent_review(client)

    assert 'send imported Transactions saying "pedidosya" to Delivery' in llm.brief


# --- add_recurring_expense -------------------------------------------------


async def templates(client) -> list[dict]:
    response = await client.get("/recurring-expenses/")
    response.raise_for_status()
    return response.json()


async def expects(client, llm, **arguments) -> str:
    """"Esto te llega todos los meses": the agent proposing a template."""
    return await proposes(
        client,
        llm,
        "propose_add_recurring_expense",
        rationale="Netflix te llegó los últimos tres meses por el mismo monto.",
        **{
            "description": "Netflix",
            "currency": "ARS",
            "reference_amount": "7999.00",
            "expected_day": 12,
            **arguments,
        },
    )


async def test_a_proposed_recurring_expense_waits_in_the_inbox(client, llm):
    ocio = await default_category(client, "Ocio", "expense")

    answer = await expects(client, llm, category_id=ocio["id"])

    assert "is_error" not in answer
    [proposal] = await suggestions(client)
    assert proposal["kind"] == "add_recurring_expense"
    assert proposal["status"] == "pending"
    assert proposal["payload"]["description"] == "Netflix"
    assert proposal["payload"]["expected_day"] == 12
    assert await templates(client) == [], "nothing is set up until the user says so"


async def test_accepting_a_recurring_expense_sets_the_template_up(client, llm):
    ocio = await default_category(client, "Ocio", "expense")
    await expects(client, llm, category_id=ocio["id"])
    [proposal] = await suggestions(client)

    response = await accept(client, proposal["id"])

    assert response.status_code == 200
    [template] = await templates(client)
    assert response.json()["result_id"] == template["id"]
    assert template["description"] == "Netflix"
    assert template["category_id"] == ocio["id"]
    assert template["reference_amount"] == "7999.00"
    assert template["expected_day"] == 12
    assert template["currency"] == "ARS"
    assert template["is_active"] is True
    assert template["adjustment"] is None


async def test_accepting_a_recurring_expense_records_no_expense(client, llm):
    """A template produces Suggestions, not Transactions: accepting spends nothing."""
    ocio = await default_category(client, "Ocio", "expense")
    await expects(client, llm, category_id=ocio["id"])
    [proposal] = await suggestions(client)

    await accept(client, proposal["id"])

    assert await transactions(client) == []


async def test_an_edited_recurring_expense_is_set_up_as_the_user_edited_it(
    client, llm
):
    ocio = await default_category(client, "Ocio", "expense")
    await expects(client, llm, category_id=ocio["id"])
    [proposal] = await suggestions(client)

    await accept(client, proposal["id"], reference_amount="9499.00", expected_day=15)

    [template] = await templates(client)
    assert template["reference_amount"] == "9499.00"
    assert template["expected_day"] == 15


async def test_an_edited_recurring_expense_is_revalidated(client, llm):
    ocio = await default_category(client, "Ocio", "expense")
    await expects(client, llm, category_id=ocio["id"])
    [proposal] = await suggestions(client)

    response = await accept(client, proposal["id"], expected_day=44)

    assert response.status_code == 422
    assert await templates(client) == []


async def test_a_template_the_user_already_has_is_refused(client, llm):
    """Two templates for one charge would each propose a payment every month."""
    ocio = await default_category(client, "Ocio", "expense")
    await create_recurring(client, description="netflix", category_id=ocio["id"])

    answer = await expects(client, llm, category_id=ocio["id"])

    assert answer["is_error"] is True
    assert "already a Recurring Expense" in answer["content"]
    assert [one["kind"] for one in await suggestions(client)] == ["add_transaction"], (
        "only the template's own monthly payment is waiting, proposed by the "
        "arithmetic; no second template was proposed"
    )


async def test_a_recurring_expense_in_an_income_category_is_refused(client, llm):
    sueldo = await default_category(client, "Sueldo", "income")

    answer = await expects(client, llm, category_id=sueldo["id"])

    assert answer["is_error"] is True
    assert "income Category" in answer["content"]
    assert await suggestions(client) == []


async def test_the_same_template_is_not_proposed_twice(client, llm):
    ocio = await default_category(client, "Ocio", "expense")
    await expects(client, llm, category_id=ocio["id"])

    answer = await expects(
        client, llm, category_id=ocio["id"], reference_amount="9499.00"
    )

    assert answer["is_error"] is True
    assert "already been made" in answer["content"]
    [proposal] = await suggestions(client)
    assert proposal["payload"]["reference_amount"] == "7999.00", (
        "the same charge in the same Category is the same template, whatever it costs"
    )


async def test_the_same_charge_in_another_category_is_its_own_proposal(client, llm):
    ocio = await default_category(client, "Ocio", "expense")
    servicios = await default_category(client, "Servicios", "expense")
    await expects(client, llm, category_id=ocio["id"])

    answer = await expects(client, llm, category_id=servicios["id"])

    assert "is_error" not in answer
    assert len(await suggestions(client)) == 2


async def test_a_proposed_recurring_expense_is_read_back_in_the_next_brief(
    client, llm
):
    ocio = await default_category(client, "Ocio", "expense")
    await expects(client, llm, category_id=ocio["id"])

    llm.will(Reply(text="Nada nuevo."))
    await agent_review(client)

    assert 'expect "Netflix" in Ocio every month, 7999.00 ARS on day 12' in llm.brief
