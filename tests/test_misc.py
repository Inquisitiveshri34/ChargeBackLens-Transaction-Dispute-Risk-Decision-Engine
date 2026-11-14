"""Sensitivity, lane examples, and the server refusing to start on a bad artifact."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.main as api_main
import scoring as sc


def test_sensitivity_returns_the_csv_rows(client):
    body = client.get("/api/sensitivity").json()
    on_disk = pd.read_csv(sc.PROCESSED_DIR / "05_sensitivity_analysis.csv")
    assert body["columns"] == on_disk.columns.tolist()
    assert len(body["rows"]) == len(on_disk) == 22
    assert body["rows"][0] == {
        "param_name": "step_up_abandon_rate", "param_value": 0.1,
        "optimal_threshold": 0.0142912864464524, "threshold_stepup_review": 0.146008042569217,
        "n_review": 41, "n_stepup": 6255, "net_savings_inr": 1811638.8244800016,
    }


def test_lane_examples_are_real_rows_from_the_right_band(client, meta):
    body = client.get("/api/lane-examples").json()
    assert list(body) == ["allow", "step_up", "manual_review"]

    sample = pd.read_csv(sc.PROCESSED_DIR / "05_scored_test_sample.csv")
    for band, chips in body.items():
        assert len(chips) == 5
        in_band = sample[sample["recommended_action"] == band]
        real = set(zip(in_band["amount"], in_band["method"], in_band["merchant_category"]))
        for chip in chips:
            assert set(chip) == {"amount", "method", "merchant_category"}
            assert (chip["amount"], chip["method"], chip["merchant_category"]) in real


def test_lane_examples_are_stable_and_sized_by_query(client):
    assert client.get("/api/lane-examples").json() == client.get("/api/lane-examples").json()
    assert all(len(v) == 2 for v in client.get("/api/lane-examples", params={"per_band": 2}).json().values())
    assert client.get("/api/lane-examples", params={"per_band": 0}).status_code == 422


def test_unknown_route_uses_the_same_error_shape(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert set(response.json()) == {"error", "message", "fields"}


def test_server_refuses_to_start_when_column_order_drifts(monkeypatch):
    columns, numeric, categorical = sc.load_feature_columns()
    drifted = [columns[1], columns[0], *columns[2:]]
    monkeypatch.setattr(sc, "load_feature_columns", lambda: (drifted, numeric, categorical))
    with pytest.raises(sc.ArtifactError, match="column order drift"):
        with TestClient(api_main.create_app()):
            pass


def test_server_refuses_to_start_when_the_model_card_is_stale(monkeypatch):
    card = sc.load_model_card()
    monkeypatch.setattr(sc, "load_model_card", lambda: {**card, "n_features": "25"})
    with pytest.raises(sc.ArtifactError, match="n_features=25"):
        with TestClient(api_main.create_app()):
            pass


def test_only_frozen_reads_may_be_cached(client, default_form, default_economics):
    """A CDN in front of the API may hold the three artifact reads and nothing else."""
    for path in ("/api/meta", "/api/sensitivity", "/api/lane-examples"):
        assert "s-maxage=300" in client.get(path).headers["cache-control"], path

    never = [
        client.get("/api/health"),
        client.get("/api/queue"),
        client.get("/api/queue/pay_86bqtrjlsj9hg0"),
        client.post("/api/score", json=default_form),
        client.post("/api/economics", json=default_economics),
        client.get("/api/queue/pay_does_not_exist"),          # errors are never stored
        client.get("/api/queue", params={"top_k_pct": 99}),
    ]
    for response in never:
        assert response.headers["cache-control"] == "no-store", response.url


def test_large_responses_are_compressed(client):
    response = client.get("/api/queue", params={"top_k_pct": 25})
    assert response.headers["content-encoding"] == "gzip"
    assert len(response.json()["rows"]) == 1250
    assert "content-encoding" not in client.get("/api/health").headers   # too small to bother
