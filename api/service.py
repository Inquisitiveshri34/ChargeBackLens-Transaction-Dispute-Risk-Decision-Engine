"""
api/service.py — what each endpoint returns, as plain functions over Artifacts.

Every number is produced by a function in app/. This file arranges calls and
shapes JSON; it holds no formula of its own. Where it mirrors a block of
app/streamlit_app.py (which cannot be imported without starting Streamlit), the
comment names the block.
"""

from __future__ import annotations

import math
import os
from functools import lru_cache

import numpy as np
import pandas as pd

from .artifacts import Artifacts

import economics as ec
import explain as ex
import scoring as sc

SEGMENT_COLUMNS = [
    "segment_type", "segment_value", "n", "dispute_rate", "mean_amount",
    "net_savings_at_global_policy", "savings_per_intervention",
    "review_band_net_inr", "n_review", "stepup_band_net_inr", "n_stepup",
]
QUEUE_COLUMNS = [
    "payment_id", "created_at", "amount", "method", "merchant_category",
    "proba_calibrated", "risk_percentile", "recommended_action", "is_disputed",
]
SWEEP_COLUMNS = ["threshold", "net_savings_inr", "total_cost_inr", "n_flagged"]


# --------------------------------------------------------------------------
# JSON shaping
# --------------------------------------------------------------------------

def to_python(value):
    """numpy and pandas scalars to JSON-safe Python; NaN and NaT become None."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def records(df: pd.DataFrame) -> list[dict]:
    columns = list(df.columns)
    return [{c: to_python(v) for c, v in zip(columns, row)}
            for row in df.itertuples(index=False, name=None)]


# --------------------------------------------------------------------------
# GET /api/meta
# --------------------------------------------------------------------------

def meta(art: Artifacts) -> dict:
    review = art.bands.loc[art.bands["band"] == sc.ACTION_REVIEW].iloc[0]
    params = art.params
    dep = art.deployed
    return {
        "model_card": dict(art.card),
        "contract": {
            "n_columns": art.contract["n_columns"],
            "n_features_in": art.contract["n_features_in_"],
            "feature_names_checked": art.contract["feature_names_in_"] is not None,
        },
        "feature_columns": [
            {"name": name, "role": "categorical" if name in art.categorical_cols else "numeric",
             "order": i}
            for i, name in enumerate(art.feature_columns)
        ],
        "economics_params": {k: to_python(v) for k, v in params.items()},
        "policy_bands": records(art.bands),
        "censoring_audit": {k: to_python(v) for k, v in art.censoring.items()},
        "headline": {
            "net_savings_inr": params.get("net_savings_inr_at_policy"),
            "do_nothing_cost_inr": params.get("do_nothing_cost_inr"),
            "share_of_exposure": (params["net_savings_inr_at_policy"] / params["do_nothing_cost_inr"]
                                  if params.get("do_nothing_cost_inr") else None),
            "lift_at_1pct": to_python(dep["lift_at_1pct"]),
            "precision_at_1pct": to_python(dep["precision_at_1pct"]),
            "caught_at_1pct": to_python(dep["caught_at_1pct"]),
            "precision_at_5pct": to_python(dep["precision_at_5pct"]),
            "recall_at_5pct": to_python(dep["recall_at_5pct"]),
            "review_band_n": to_python(review["n"]),
            "review_band_lift": to_python(review["lift_vs_base"]),
            "base_rate": art.base_rate,
            "test_positives": to_python(dep["positives"]),
            "test_n": to_python(dep["n"]),
            "max_proba": to_python(dep["max_proba"]),
        },
        "categorical_levels": {k: list(v) for k, v in sc.CATEGORICAL_LEVELS.items()},
        "merchant_defaults": {k: dict(v) for k, v in sc.MERCHANT_DEFAULTS.items()},
        "action_labels": dict(sc.ACTION_LABELS),
        "economics_basis": {"label": art.basis_label, "is_exact": art.basis_exact},
        "queue_sample_size": int(len(art.queue)),
        "reviewer_note_source": "anthropic-api" if os.environ.get("ANTHROPIC_API_KEY") else "template",
    }


# --------------------------------------------------------------------------
# POST /api/score — Tab 1's button handler
# --------------------------------------------------------------------------

def score(art: Artifacts, form: dict) -> dict:
    amount = float(form["amount"])
    row = sc.build_feature_row(form, art.feature_columns, art.categorical_cols)
    probability = sc.score_transaction(art.model, row)
    action = sc.recommend_action(probability, art.params)
    drivers = ex.top_drivers(art.model, row, art.coefficients, art.importances,
                             art.categorical_cols, k=5)
    note, source = ex.generate_reviewer_note(
        probability, action, drivers, amount=amount, base_rate=art.base_rate)

    return {
        "probability": probability,
        "base_rate": art.base_rate,
        "lift_vs_base": probability / art.base_rate,
        "action": action,
        "action_label": sc.ACTION_LABELS[action],
        "thresholds": {
            "allow_stepup": art.params["threshold_allow_stepup"],
            "stepup_review": art.params["threshold_stepup_review"],
        },
        "costs": ec.expected_cost_matrix(amount, art.params),
        "drivers": [
            {
                "feature": r["feature"],
                "term": r["term"],
                "label": r["label"],
                "contribution": to_python(r["contribution"]),
                "direction": r["direction"],
            }
            for _, r in drivers.iterrows()
        ],
        "drivers_method": drivers.attrs.get("method"),
        "reviewer_note": note,
        "reviewer_note_source": source,
        "feature_row": [{"name": c, "value": to_python(row.iloc[0][c])}
                        for c in art.feature_columns],
    }


# --------------------------------------------------------------------------
# GET /api/queue and /api/queue/{payment_id} — Tab 2
# --------------------------------------------------------------------------

def queue_slice(art: Artifacts, top_k_pct: float) -> dict:
    k = max(1, int(round(len(art.queue) * top_k_pct / 100)))
    queue = art.queue.head(k)
    disputed = queue["is_disputed"] == 1

    rows = queue[QUEUE_COLUMNS].assign(
        # Same two display columns Tab 2 derives.
        risk_pct=(queue["proba_calibrated"] * 100).round(2),
        percentile=(queue["risk_percentile"] * 100).round(2),
        is_disputed=disputed,
    )
    return {
        "top_k_pct": top_k_pct,
        "sample_size": int(len(art.queue)),
        "metrics": {
            "transactions": k,
            "disputes_caught": int(queue["is_disputed"].sum()),
            "precision": float(queue["is_disputed"].mean()),
            "exposure_inr": float(queue.loc[disputed, "amount"].sum()),
        },
        "rows": records(rows),
    }


def queue_detail(art: Artifacts, payment_id: str) -> dict | None:
    """Mirrors Tab 2's selection block. Returns None for an unknown payment_id."""
    if payment_id not in art.queue_by_id.index:
        return None
    picked = art.queue_by_id.loc[payment_id]
    probability = float(picked["proba_calibrated"])
    action = sc.recommend_action(probability, art.params)

    # Importance-ranked, as in Tab 2: the sample carries display columns rather
    # than the 26 fitted ones, so there is no design row to decompose.
    eligible = art.importances[art.importances["informative"].astype(bool)].copy()
    eligible["present"] = [picked.get(f, np.nan) if f in picked.index else np.nan
                           for f in eligible["feature"]]
    eligible = eligible.dropna(subset=["present"])
    drivers = pd.DataFrame({
        "feature": eligible["feature"],
        "label": [ex._describe(f, None, v) for f, v in zip(eligible["feature"], eligible["present"])],
        "contribution": eligible["importance"],
        "value": eligible["present"],
        "direction": "raises risk",
    }).head(4)
    note, source = ex.generate_reviewer_note(
        probability, action, drivers, amount=float(picked["amount"]), base_rate=art.base_rate)

    return {
        "payment_id": payment_id,
        "probability": probability,
        "base_rate": art.base_rate,
        "lift_vs_base": probability / art.base_rate,
        "action": action,
        "action_label": sc.ACTION_LABELS[action],
        "amount": float(picked["amount"]),
        "reviewer_note": note,
        "reviewer_note_source": source,
    }


# --------------------------------------------------------------------------
# POST /api/economics — Tab 3
# --------------------------------------------------------------------------

class EconomicsEngine:
    """
    Live band optimisation, cached on the four parameter values plus the
    segments flag. The cache belongs to the instance so it lives and dies with
    the artifacts it was computed from.
    """

    def __init__(self, art: Artifacts, cache_size: int = 512):
        self.art = art
        self.run = lru_cache(maxsize=cache_size)(self._run)

    def _run(self, dispute_fee: float, ops_review_cost: float, merchant_margin: float,
             step_up_abandon_rate: float, live_segments: bool) -> dict:
        art = self.art
        key = (dispute_fee, ops_review_cost, merchant_margin, step_up_abandon_rate)
        params = dict(zip(ec.COST_PARAM_KEYS, key))
        defaults = art.default_cost_params

        df, weights = art.basis_df, art.basis_weights
        y = df["is_disputed"].to_numpy(float)
        p = df["proba_calibrated"].to_numpy(float)
        a = df["amount"].to_numpy(float)

        best = ec.optimise_bands(y, p, a, params, weights=weights)
        sweep = ec.threshold_sweep(y, p, a, params, weights=weights)
        single = sweep.loc[sweep["net_savings_inr"].idxmax()]

        at_default = bool(np.allclose(key, [defaults[k] for k in ec.COST_PARAM_KEYS]))
        baseline_shifted = any(params[k] != defaults[k] for k in ec.BASELINE_SHIFTING_PARAMS)

        if live_segments:
            segments = ec.segment_economics_live(
                df, params, best["threshold_allow_stepup"], best["threshold_stepup_review"],
                weights=weights)
        else:
            segments = art.segments

        return {
            "params": params,
            "basis": {"label": art.basis_label, "is_exact": art.basis_exact},
            "at_default": at_default,
            "reproduces_export": at_default and art.basis_exact,
            "exported_policy": {
                "net_savings_inr": art.params.get("net_savings_inr_at_policy"),
                "threshold_allow_stepup": art.params["threshold_allow_stepup"],
                "threshold_stepup_review": art.params["threshold_stepup_review"],
            },
            "baseline_shifted": baseline_shifted,
            "bands": {
                "threshold_allow_stepup": best["threshold_allow_stepup"],
                "threshold_stepup_review": best["threshold_stepup_review"],
                "n_review": best["n_review"],
                "n_stepup": best["n_stepup"],
                "n_allow": best["n_allow"],
                "interventions": best["n_review"] + best["n_stepup"],
                "total_cost_inr": best["total_cost_inr"],
                "do_nothing_cost_inr": best["do_nothing_cost_inr"],
                "net_savings_inr": best["net_savings_inr"],
                "share_of_exposure": (best["net_savings_inr"] / best["do_nothing_cost_inr"]
                                      if best["do_nothing_cost_inr"] else None),
            },
            "single_threshold": {
                "threshold": float(single["threshold"]),
                "net_savings_inr": float(single["net_savings_inr"]),
                "second_cut_value_inr": best["net_savings_inr"] - float(single["net_savings_inr"]),
            },
            "sweep": records(sweep[SWEEP_COLUMNS]),
            "x_max": art.score_x_max,
            "segments": {
                "source": "live" if live_segments else "frozen",
                "rows": records(segments[SEGMENT_COLUMNS]),
            },
        }


# --------------------------------------------------------------------------
# GET /api/sensitivity, GET /api/lane-examples
# --------------------------------------------------------------------------

def sensitivity(art: Artifacts) -> dict:
    return {"columns": list(art.sensitivity.columns), "rows": records(art.sensitivity)}


def lane_examples(art: Artifacts, per_band: int) -> dict:
    """
    Real rows from the scored sample for the landing page's lane chips. The draw
    is seeded, so the same rows come back on every call and every restart.
    """
    bands = sc.recommend_action_vec(
        art.queue["proba_calibrated"].to_numpy(float),
        art.params["threshold_allow_stepup"], art.params["threshold_stepup_review"])
    out = {}
    for band in (sc.ACTION_ALLOW, sc.ACTION_STEP_UP, sc.ACTION_REVIEW):
        rows = art.queue.loc[bands == band, ["amount", "method", "merchant_category"]]
        picked = rows.sample(n=min(per_band, len(rows)), random_state=sc.RANDOM_SEED)
        out[band] = records(picked)
    return out
