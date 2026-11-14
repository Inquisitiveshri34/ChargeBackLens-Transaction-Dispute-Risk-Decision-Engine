"""POST /api/score — the default form, and what a bad form gets back."""

import pytest

from fmt import cut, pct, rupees, signed3


@pytest.fixture
def scored(client, default_form):
    response = client.post("/api/score", json=default_form)
    assert response.status_code == 200, response.text
    return response.json()


def test_default_form_scores_allow(scored):
    assert pct(scored["probability"]) == "0.46%"
    assert scored["action"] == "allow"
    assert scored["action_label"] == "Allow"
    assert f"{scored['lift_vs_base']:.1f}" == "0.5"


def test_default_drivers_in_order(scored):
    got = [(d["label"], signed3(d["contribution"]), d["direction"]) for d in scored["drivers"]]
    assert got == [
        # The build prompt lists +1.870 for the first driver. The Python modules
        # give 1.8724, and where the two disagree the Python modules win.
        ("transaction amount (Rs 8,500)", "+1.872", "raises risk"),
        ("email domain type = personal", "−1.410", "lowers risk"),
        ("merchant category = travel", "−1.236", "lowers risk"),
        ("payment method = upi", "−1.006", "lowers risk"),
        ("phone verified: yes", "−0.300", "lowers risk"),
    ]
    assert scored["drivers_method"] == "coefficient x transformed value (exact log-odds)"


def test_default_why_this_band_costs(scored):
    costs = scored["costs"]
    assert [rupees(costs[k]) for k in ("fn_cost", "fp_cost", "tp_cost")] == ["₹10,300", "₹382", "₹300"]
    assert cut(scored["thresholds"]["allow_stepup"]) == "0.0244"
    assert cut(scored["thresholds"]["stepup_review"]) == "0.0824"


def test_feature_row_is_26_values_in_fitted_order(scored, meta):
    row = scored["feature_row"]
    assert [f["name"] for f in row] == [c["name"] for c in meta["feature_columns"]]
    assert len(row) == 26
    values = {f["name"]: f["value"] for f in row}
    assert values["hour_of_day"] == 22
    assert values["is_night_txn"] == 0
    assert values["delivery_sla_days_filled"] == 2
    assert values["method"] == "upi"


def test_reviewer_note_uses_the_template_and_says_so(scored):
    assert scored["reviewer_note_source"] == "template"
    assert scored["reviewer_note"].startswith("Scored 0.46% against a 0.90% portfolio base rate (0.5x)")
    assert scored["reviewer_note"].endswith(
        "Recommended: allow — the expected dispute cost here is below the cost of intervening.")


def test_risky_form_reaches_manual_review(client, default_form):
    form = {**default_form, "amount": 60000, "method": "netbanking",
            "email_domain_type": "disposable", "phone_verified": False,
            "is_first_txn_for_device": True, "has_prior_history": False}
    body = client.post("/api/score", json=form).json()
    assert body["action"] == "manual_review"
    assert body["probability"] >= body["thresholds"]["stepup_review"]


def test_delivery_sla_is_ignored_for_digital_goods(client, default_form):
    form = {**default_form, "is_physical_goods": False, "delivery_sla_days": 9}
    values = {f["name"]: f["value"] for f in client.post("/api/score", json=form).json()["feature_row"]}
    assert values["delivery_sla_days_filled"] == 0


@pytest.mark.parametrize("field, value, expected", [
    ("amount", 0, "greater than or equal to 1"),
    ("amount", 500001, "less than or equal to 500000"),
    ("retry_count", 11, "less than or equal to 10"),
    ("checkout_latency_ms", -1, "greater than or equal to 0"),
    ("account_age_days_at_txn", 2501, "less than or equal to 2500"),
    ("merchant_dispute_rate_trailing_90d", 0.5, "less than or equal to 0.03"),
    ("method", "cheque", "must be one of: upi, card, netbanking, wallet, emi"),
    ("created_at", "2026-09-15T22:00:00+05:30", "should not have timezone info"),
])
def test_out_of_range_input_is_a_422_naming_the_field(client, default_form, field, value, expected):
    response = client.post("/api/score", json={**default_form, field: value})
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_error"
    assert [f["field"] for f in body["fields"]] == [field]
    assert expected in body["fields"][0]["message"]
    assert body["message"].startswith(f"{field}: ")


def test_missing_and_unknown_fields_are_rejected(client, default_form):
    form = {k: v for k, v in default_form.items() if k != "amount"}
    form["not_a_field"] = 1
    body = client.post("/api/score", json=form)
    assert body.status_code == 422
    assert {f["field"] for f in body.json()["fields"]} == {"amount", "not_a_field"}
