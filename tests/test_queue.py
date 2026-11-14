"""GET /api/queue and /api/queue/{payment_id} — Tab 2."""

from fmt import pct, rupees

TOP_ROW = "pay_86bqtrjlsj9hg0"


def test_queue_at_five_percent(client):
    body = client.get("/api/queue", params={"top_k_pct": 5}).json()
    metrics = body["metrics"]
    assert metrics["transactions"] == 250
    assert metrics["disputes_caught"] == 51
    assert pct(metrics["precision"]) == "20.40%"
    assert rupees(metrics["exposure_inr"]) == "₹5,08,255"
    assert len(body["rows"]) == 250


def test_default_slice_is_five_percent(client):
    assert client.get("/api/queue").json() == client.get("/api/queue", params={"top_k_pct": 5}).json()


def test_rows_are_sorted_by_risk_descending(client):
    rows = client.get("/api/queue", params={"top_k_pct": 25}).json()["rows"]
    risks = [r["proba_calibrated"] for r in rows]
    assert len(rows) == 1250
    assert risks == sorted(risks, reverse=True)


def test_top_queue_row(client):
    top = client.get("/api/queue").json()["rows"][0]
    assert top["payment_id"] == TOP_ROW
    assert pct(top["proba_calibrated"]) == "33.44%"
    assert top["risk_pct"] == 33.44
    assert top["percentile"] == 100.0
    assert top["recommended_action"] == "manual_review"
    assert top["is_disputed"] is True
    assert top["created_at"] == "2026-08-10T19:15:25"
    assert (top["method"], top["merchant_category"]) == ("netbanking", "travel")


def test_selecting_the_top_row_opens_without_error(client):
    """
    Regression for the queue-selection crash: the top row's second driver is
    the categorical `email_domain_type = "disposable"`, which explain._describe
    used to pass to float().
    """
    top = client.get("/api/queue").json()["rows"][0]
    response = client.get(f"/api/queue/{top['payment_id']}")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["payment_id"] == TOP_ROW
    assert pct(detail["probability"]) == "33.44%"
    assert f"{detail['lift_vs_base']:.1f}" == "37.2"
    assert detail["action"] == "manual_review"
    assert detail["action_label"] == "Manual review"
    assert rupees(detail["amount"]) == "₹59,931"
    assert ("driven mainly by transaction amount (Rs 59,931) and email domain type = disposable."
            in detail["reviewer_note"])
    assert detail["reviewer_note_source"] == "template"


def test_every_row_in_the_slice_opens(client):
    for row in client.get("/api/queue", params={"top_k_pct": 2}).json()["rows"]:
        detail = client.get(f"/api/queue/{row['payment_id']}")
        assert detail.status_code == 200, row["payment_id"]
        assert detail.json()["action"] == row["recommended_action"]


def test_unknown_payment_id_is_a_404(client):
    response = client.get("/api/queue/pay_does_not_exist")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_slice_outside_the_slider_range_is_a_422(client):
    for value in (0, 0.4, 25.5, "lots"):
        response = client.get("/api/queue", params={"top_k_pct": value})
        assert response.status_code == 422
        assert response.json()["fields"][0]["field"] == "top_k_pct"
