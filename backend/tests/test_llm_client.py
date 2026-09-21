"""
Which failures of the Anthropic API are worth asking about again.

The one place these tests reach below the HTTP seam, and for a reason: what
the API answered is invisible from outside the app — the loop is handed an
`LLMUnavailable` either way — and the whole retry rule rests on this one
classification. A 529 read as final would lose a Review to a busy minute; a
400 read as transient would make the user wait out two backoffs for an answer
that was never going to change.
"""

import anthropic
import httpx

from app.llm import unavailable

REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def answered(status: int) -> anthropic.APIStatusError:
    return anthropic.APIStatusError(
        f"status {status}",
        response=httpx.Response(status, request=REQUEST),
        body=None,
    )


def test_a_rate_limit_is_the_api_being_busy():
    assert unavailable(answered(429)).transient


def test_an_overloaded_model_is_the_api_being_busy():
    assert unavailable(answered(529)).transient


def test_a_request_the_api_refused_is_not_worth_repeating():
    assert not unavailable(answered(400)).transient
    assert not unavailable(answered(401)).transient, "a bad key stays bad"


def test_a_server_error_is_not_assumed_to_be_temporary():
    assert not unavailable(answered(500)).transient, (
        "only the two statuses that mean 'not now' are asked again"
    )


def test_a_connection_that_dropped_never_reached_the_model():
    dropped = anthropic.APIConnectionError(message="connection reset", request=REQUEST)

    failure = unavailable(dropped)

    assert failure.transient
    assert "could not be reached" in str(failure)


def test_what_the_api_said_is_kept_in_the_message():
    assert "status 429" in str(unavailable(answered(429)))
