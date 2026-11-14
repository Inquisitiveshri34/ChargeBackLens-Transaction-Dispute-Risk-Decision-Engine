"""GET /api/meta — everything the front end would otherwise have to hard-code."""

import pandas as pd

import scoring as sc

from fmt import pct, rupees


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_model_card_and_contract(meta):
    assert meta["model_card"]["selected_model"] == "LR_plain"
    assert meta["model_card"]["calibration_method"] == "sigmoid"
    assert meta["contract"] == {"n_columns": 26, "n_features_in": 26, "feature_names_checked": True}


def test_feature_columns_are_in_fitted_order(meta):
    on_disk = pd.read_csv(sc.PROCESSED_DIR / "04_feature_columns.csv").sort_values("order")
    assert [c["name"] for c in meta["feature_columns"]] == on_disk["feature_name"].tolist()
    assert [c["role"] for c in meta["feature_columns"]] == on_disk["model_role"].tolist()


def test_headline_figures(meta):
    headline = meta["headline"]
    assert rupees(headline["net_savings_inr"]) == "₹11,99,620"
    assert pct(headline["share_of_exposure"], 1) == "39.1%"
    assert f"{headline['lift_at_1pct']:.1f}" == "16.2"
    assert pct(headline["precision_at_1pct"], 1) == "14.6%"
    assert headline["review_band_n"] == 308
    assert f"{headline['review_band_lift']:.1f}" == "18.8"
    assert pct(headline["base_rate"], 3) == "0.900%"
    assert (headline["test_positives"], headline["test_n"]) == (407, 45246)


def test_policy_bands_and_thresholds(meta):
    assert [b["band"] for b in meta["policy_bands"]] == ["allow", "step_up", "manual_review"]
    params = meta["economics_params"]
    assert f"{params['threshold_allow_stepup']:.4f}" == "0.0244"
    assert f"{params['threshold_stepup_review']:.4f}" == "0.0824"
    assert (params["dispute_fee"], params["ops_review_cost"]) == (1500, 300)
    assert (params["merchant_margin"], params["step_up_abandon_rate"]) == (0.18, 0.25)


def test_censoring_audit(meta):
    audit = meta["censoring_audit"]
    assert (audit["raised_after_snapshot"], audit["test_positives"]) == (294, 407)
    assert pct(audit["share_after_snapshot"], 1) == "72.2%"
    assert audit["max_raised_at"].startswith("2027-01-26")


def test_form_options_and_merchant_defaults(meta):
    assert meta["categorical_levels"] == sc.CATEGORICAL_LEVELS
    assert meta["merchant_defaults"] == sc.MERCHANT_DEFAULTS
    assert meta["action_labels"]["step_up"] == "Step-up (3DS)"


def test_note_source_is_template_without_a_key(meta):
    assert meta["reviewer_note_source"] == "template"
