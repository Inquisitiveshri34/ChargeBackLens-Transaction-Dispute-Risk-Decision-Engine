"""Shared fixtures. One server boot for the whole run; the artifacts are read-only."""

import pytest
from fastapi.testclient import TestClient

import api.main as api_main


@pytest.fixture(autouse=True, scope="session")
def no_anthropic_key():
    """
    Force the template path for the reviewer note. With a key in the
    environment the note comes from a model and no test could assert its text.
    """
    patcher = pytest.MonkeyPatch()
    patcher.delenv("ANTHROPIC_API_KEY", raising=False)
    yield
    patcher.undo()


@pytest.fixture(scope="session")
def client(no_anthropic_key):
    with TestClient(api_main.create_app()) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def meta(client):
    response = client.get("/api/meta")
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def default_form(meta):
    """The Score screen's defaults, with merchant fields from the API's own table."""
    travel = meta["merchant_defaults"]["travel"]
    return {
        "amount": 8500,
        "method": "upi",
        "merchant_category": "travel",
        "created_at": "2026-09-15T22:00:00",
        "retry_count": 0,
        "checkout_latency_ms": 2600,
        "merchant_avg_ticket_size": travel["avg_ticket_size"],
        "email_domain_type": "personal",
        "phone_verified": True,
        "account_age_days_at_txn": 450,
        "is_first_txn_for_device": False,
        "is_foreign_bin": False,
        "is_physical_goods": bool(travel["is_physical_goods"]),
        "refund_window_days": travel["refund_window_days"],
        "delivery_sla_days": travel["delivery_sla_days"],
        "txns_last_24h": 0,
        "txns_last_7d": 0,
        "distinct_devices_30d": 1,
        "prior_disputes_before_this_txn": 0,
        "has_prior_history": True,
        "ip_state_changed_from_prev_txn": True,
        "amount_vs_own_avg": 1.0,
        "merchant_dispute_rate_trailing_90d": 0.007,
    }


@pytest.fixture
def default_economics(meta):
    params = meta["economics_params"]
    return {
        "dispute_fee": params["dispute_fee"],
        "ops_review_cost": params["ops_review_cost"],
        "merchant_margin": params["merchant_margin"],
        "step_up_abandon_rate": params["step_up_abandon_rate"],
        "live_segments": False,
    }
