from pathlib import Path

import joblib
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "data" / "processed" / "models" / "calibrated_model.joblib"


# These are the deployed model features from the final feature contract.
FEATURE_COLUMNS = [
    "log_amount",
    "amount_vs_merchant_avg_ratio",
    "retry_count",
    "checkout_latency_ms",
    "is_foreign_bin",
    "is_first_txn_for_device",
    "phone_verified",
    "txns_last_24h",
    "txns_last_7d",
    "distinct_devices_30d",
    "has_prior_history",
    "prior_disputes_before_this_txn",
    "merchant_dispute_rate_trailing_90d",
]


@staticmethod
def load_model():
    """
    Load the frozen calibrated model.

    The app never retrains the model.
    """

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found at {MODEL_PATH}"
        )

    return joblib.load(MODEL_PATH)


def build_features(transaction):
    """
    Build the model input from a transaction dictionary.

    This function should remain aligned with Notebook 3's
    final feature engineering contract.
    """

    amount = float(
        transaction["amount"]
    )

    # Prevent log(0).
    log_amount = np.log1p(
        max(amount, 0)
    )

    merchant_avg = float(
        transaction.get(
            "merchant_avg_amount",
            amount,
        )
    )

    if merchant_avg <= 0:
        amount_ratio = 1.0
    else:
        amount_ratio = (
            amount / merchant_avg
        )

    features = {
        "log_amount": log_amount,
        "amount_vs_merchant_avg_ratio":
            amount_ratio,

        "retry_count":
            transaction.get("retry_count", 0),

        "checkout_latency_ms":
            transaction.get(
                "checkout_latency_ms",
                0,
            ),

        "is_foreign_bin":
            transaction.get(
                "is_foreign_bin",
                0,
            ),

        "is_first_txn_for_device":
            transaction.get(
                "is_first_txn_for_device",
                0,
            ),

        "phone_verified":
            transaction.get(
                "phone_verified",
                0,
            ),

        "txns_last_24h":
            transaction.get(
                "txns_last_24h",
                0,
            ),

        "txns_last_7d":
            transaction.get(
                "txns_last_7d",
                0,
            ),

        "distinct_devices_30d":
            transaction.get(
                "distinct_devices_30d",
                0,
            ),

        "has_prior_history":
            transaction.get(
                "has_prior_history",
                0,
            ),

        "prior_disputes_before_this_txn":
            transaction.get(
                "prior_disputes_before_this_txn",
                0,
            ),

        "merchant_dispute_rate_trailing_90d":
            transaction.get(
                "merchant_dispute_rate_trailing_90d",
                0,
            ),
    }

    return pd.DataFrame(
        [[features[col] for col in FEATURE_COLUMNS]],
        columns=FEATURE_COLUMNS,
    )


def score_transaction(
    transaction,
    model,
):
    """
    Return calibrated dispute probability.
    """

    X = build_features(transaction)

    if hasattr(model, "predict_proba"):

        probability = model.predict_proba(X)[
            0, 1
        ]

    else:

        probability = model.predict(
            X
        )[0]

    return float(
        np.clip(
            probability,
            0.0,
            1.0,
        )
    )


def get_risk_band(
    probability,
    params,
):
    """
    Convert probability into the frozen policy band.
    """

    allow_stepup = float(
        params["threshold_allow_stepup"]
    )

    stepup_review = float(
        params["threshold_stepup_review"]
    )

    if probability < allow_stepup:
        return "allow"

    if probability < stepup_review:
        return "step_up"

    return "manual_review"


def get_action(
    probability,
    params,
):
    """
    Operational action corresponding to the
    frozen policy bands.
    """

    return get_risk_band(
        probability,
        params,
    )


def get_risk_drivers(
    transaction,
    probability,
):
    """
    Deterministic reviewer-facing risk drivers.

    These are intentionally simple and interpretable.
    They do not modify the model probability.
    """

    drivers = []

    if transaction.get(
        "amount",
        0,
    ) > 25000:
        drivers.append(
            "Transaction amount is relatively high."
        )

    if transaction.get(
        "amount_vs_merchant_avg_ratio",
        1,
    ) > 3:
        drivers.append(
            "Transaction amount is materially above the merchant's typical amount."
        )

    if transaction.get(
        "retry_count",
        0,
    ) >= 2:
        drivers.append(
            "Multiple payment attempts were observed."
        )

    if transaction.get(
        "checkout_latency_ms",
        0,
    ) > 10000:
        drivers.append(
            "Checkout latency is unusually high."
        )

    if transaction.get(
        "is_first_txn_for_device",
        0,
    ):
        drivers.append(
            "This is the first transaction observed for the device."
        )

    if not transaction.get(
        "phone_verified",
        1,
    ):
        drivers.append(
            "Phone verification is not present."
        )

    if transaction.get(
        "email_domain_type",
        "",
    ) == "disposable":
        drivers.append(
            "Disposable email domain detected."
        )

    if transaction.get(
        "prior_disputes_before_this_txn",
        0,
    ) > 0:
        drivers.append(
            "Customer has prior dispute history."
        )

    if transaction.get(
        "merchant_dispute_rate_trailing_90d",
        0,
    ) > 0.02:
        drivers.append(
            "Merchant trailing dispute rate is elevated."
        )

    if not drivers:
        drivers.append(
            "No single dominant risk driver was identified."
        )

    return drivers[:5]