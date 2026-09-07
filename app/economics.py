"""
app/economics.py — the cost model, the sweeps, and the two-threshold optimiser.

Ported from notebook 5, not re-implemented (dev plan §7.3). Every function here
is verified to reproduce its exported CSV on 04_test_predictions.csv:

    do-nothing cost      3,069,546.78   == 05_economics_params.csv
    binary sweep optimum 1,080,993.40 @ 0.024054  == 05_threshold_sweep.csv row 93
    joint band optimum   1,199,620.186 @ (0.0244250300855189, 0.0823954944078569)
                                        == 05_economics_params.csv + 05_policy_bands.csv
    all 15 segments      net + review-band decomposition == 05_segment_economics.csv

Two conventions that are load-bearing:

1. THE GRID IS QUANTILE-BASED, NEVER np.linspace. The deployed model's maximum
   test probability is 0.3344, so 67 of the 100 points in the dev plan's
   linspace grid flag zero rows and the "optimum" would be wherever that plateau
   began (model_evaluation.md §4.5). linspace is not offered as an option here.

2. BAND MEMBERSHIP IS `>=` ON BOTH CUTS, matching 05_policy_bands.csv.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from scoring import (ACTION_ALLOW, ACTION_REVIEW, ACTION_STEP_UP,
                     load_policy_bands, load_scored_sample, load_test_predictions)

COST_PARAM_KEYS = ("dispute_fee", "ops_review_cost", "merchant_margin", "step_up_abandon_rate")

# Sensitivity rows for these two are NOT comparable to each other on
# net_savings, because both sit inside fn_cost and therefore raise the
# do-nothing baseline the saving is measured against (model_evaluation.md §4.8).
# The app must say so wherever these sliders move.
BASELINE_SHIFTING_PARAMS = ("dispute_fee", "ops_review_cost")


# --------------------------------------------------------------------------
# The cost model (LLD §4.7, extended to three bands in model_evaluation.md §5.2)
# --------------------------------------------------------------------------

def expected_cost_matrix(amount: float, params: dict) -> dict[str, float]:
    """
    Per-transaction cost under each outcome. Scalar form, kept for parity with
    LLD §4.7's signature and for display in the app's methodology expander.

        fn_cost = amount + dispute_fee + ops_review_cost   (allowed, then disputed)
        fp_cost = amount * margin * abandon_rate           (stepped up, wasn't going to dispute)
        tp_cost = ops_review_cost                          (reviewed, correctly)
        tn_cost = 0
    """
    return {
        "fn_cost": float(amount) + params["dispute_fee"] + params["ops_review_cost"],
        "fp_cost": float(amount) * params["merchant_margin"] * params["step_up_abandon_rate"],
        "tp_cost": params["ops_review_cost"],
        "tn_cost": 0.0,
    }


def do_nothing_cost(y: np.ndarray, amounts: np.ndarray, params: dict) -> float:
    """
    Cost of allowing every transaction: every dispute lands and is paid for.
    This is the baseline net savings is measured against, and the reason the
    two baseline-shifting parameters above need their caveat.
    """
    y = np.asarray(y, dtype=float)
    amounts = np.asarray(amounts, dtype=float)
    return float((y * (amounts + params["dispute_fee"] + params["ops_review_cost"])).sum())


def quantile_grid(proba: np.ndarray, n_steps: int = 101) -> np.ndarray:
    """101 points drawn from quantiles of the score, so every point flags >= 1 row."""
    return np.quantile(np.asarray(proba, dtype=float), np.linspace(0.0, 1.0, n_steps))


# --------------------------------------------------------------------------
# Binary sweep (LLD §4.7 threshold_sweep, on realised cost)
# --------------------------------------------------------------------------

def threshold_sweep(y, proba, amounts, params: dict, n_steps: int = 101,
                    weights=None) -> pd.DataFrame:
    """
    Each row is charged the cost of the outcome it actually had, given the
    action the threshold would have taken. Reproduces 05_threshold_sweep.csv.

    `weights` supports the reweighted-sample fallback below; None means every
    row counts once, which is the notebook's case.
    """
    y = np.asarray(y, dtype=float)
    proba = np.asarray(proba, dtype=float)
    amounts = np.asarray(amounts, dtype=float)
    w = np.ones_like(y) if weights is None else np.asarray(weights, dtype=float)

    fee, ops = params["dispute_fee"], params["ops_review_cost"]
    friction = params["merchant_margin"] * params["step_up_abandon_rate"]
    baseline = float((w * y * (amounts + fee + ops)).sum())

    rows = []
    for t in quantile_grid(proba, n_steps):
        flagged = proba >= t
        tp = flagged & (y == 1)
        fp = flagged & (y == 0)
        fn = ~flagged & (y == 1)
        cost = float((w[tp] * ops).sum()
                     + (w[fp] * amounts[fp] * friction).sum()
                     + (w[fn] * (amounts[fn] + fee + ops)).sum())
        n_flag = float(w[flagged].sum())
        n_tp, n_fp, n_fn = float(w[tp].sum()), float(w[fp].sum()), float(w[fn].sum())
        rows.append({
            "threshold": float(t),
            "n_flagged": n_flag,
            "flag_rate": n_flag / w.sum(),
            "tp": n_tp, "fp": n_fp, "fn": n_fn,
            "precision": n_tp / n_flag if n_flag else 0.0,
            "recall": n_tp / (n_tp + n_fn) if (n_tp + n_fn) else 0.0,
            "total_cost_inr": cost,
            "net_savings_inr": baseline - cost,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Joint two-threshold optimisation (model_evaluation.md §4.7)
# --------------------------------------------------------------------------

def optimise_bands(y, proba, amounts, params: dict, weights=None) -> dict:
    """
    Optimise both cuts jointly under the three-band cost model.

    Sort descending by probability and any policy is two cut indices i <= j:
    rows [0, i) are reviewed, [i, j) stepped up, [j, n) allowed. Total cost
    decomposes as

        f(i) + cumS(j) + A - cumA(j),     f(i) = R*i - cumS(i)

    where S is the step-up cost of each row and A its allow cost. f depends only
    on i, so the best i for every j is a prefix-argmin: one pass over 45,246
    rows instead of 45,246^2 pairs.

    Returns the two thresholds, the band counts, total cost, and net savings.
    Reproduces the exported policy exactly at default parameters.
    """
    y = np.asarray(y, dtype=float)
    proba = np.asarray(proba, dtype=float)
    amounts = np.asarray(amounts, dtype=float)
    w = np.ones_like(y) if weights is None else np.asarray(weights, dtype=float)

    fee, ops = params["dispute_fee"], params["ops_review_cost"]
    friction = params["merchant_margin"] * params["step_up_abandon_rate"]

    order = np.argsort(-proba, kind="mergesort")   # stable: ties keep input order
    ys, ps, amt_s, ws = y[order], proba[order], amounts[order], w[order]

    review = ws * ops                              # charged whatever the label
    step_up = ws * (1 - ys) * amt_s * friction     # step-up deters the disputer
    allow = ws * ys * (amt_s + fee + ops)

    n = len(ys)
    cum_review = np.concatenate([[0.0], np.cumsum(review)])
    cum_step = np.concatenate([[0.0], np.cumsum(step_up)])
    cum_allow = np.concatenate([[0.0], np.cumsum(allow)])
    allow_total = float(cum_allow[-1])

    f = cum_review - cum_step                      # cost of reviewing the first i rows
    running_min = np.minimum.accumulate(f)
    # Index at which each running minimum was first achieved, vectorised: mark
    # every strict new minimum, then carry the latest such index forward.
    is_new_min = np.concatenate([[True], f[1:] < running_min[:-1]])
    arg_i = np.maximum.accumulate(np.where(is_new_min, np.arange(n + 1), 0))

    total = running_min + cum_step + allow_total - cum_allow
    j = int(np.argmin(total))
    i = int(arg_i[j])

    # A cut index maps back to a threshold as the probability of the last row
    # inside the band, since membership is `>=`.
    t_review = float(ps[i - 1]) if i > 0 else float(ps[0]) + 1.0
    t_allow = float(ps[j - 1]) if j > 0 else t_review

    baseline = float((w * y * (amounts + fee + ops)).sum())

    return {
        "threshold_allow_stepup": t_allow,
        "threshold_stepup_review": t_review,
        "n_review": float(ws[:i].sum()),
        "n_stepup": float(ws[i:j].sum()),
        "n_allow": float(ws[j:].sum()),
        "total_cost_inr": float(total[j]),
        "do_nothing_cost_inr": baseline,
        "net_savings_inr": baseline - float(total[j]),
        "cut_index_review": i,
        "cut_index_allow": j,
    }


def policy_cost(y, proba, amounts, params: dict, t_allow: float, t_review: float,
                weights=None) -> dict:
    """
    Cost and savings of an ARBITRARY pair of thresholds, decomposed by band.

    Separate from optimise_bands() on purpose: the segment table needs each
    segment evaluated at the single GLOBAL policy that would actually ship. A
    threshold optimised inside a segment is non-negative by construction and so
    can never identify a segment worth skipping (model_evaluation.md §4.9).
    """
    y = np.asarray(y, dtype=float)
    proba = np.asarray(proba, dtype=float)
    amounts = np.asarray(amounts, dtype=float)
    w = np.ones_like(y) if weights is None else np.asarray(weights, dtype=float)

    fee, ops = params["dispute_fee"], params["ops_review_cost"]
    friction = params["merchant_margin"] * params["step_up_abandon_rate"]

    review = proba >= t_review
    step_up = (proba >= t_allow) & ~review
    allow = ~review & ~step_up

    cost_review = float((w[review] * ops).sum())
    cost_step = float((w[step_up] * (1 - y[step_up]) * amounts[step_up] * friction).sum())
    cost_allow = float((w[allow] * y[allow] * (amounts[allow] + fee + ops)).sum())

    # Each band's contribution to savings = what those rows would have cost if
    # allowed, minus what the policy actually spends on them.
    would_cost_review = float((w[review] * y[review] * (amounts[review] + fee + ops)).sum())
    would_cost_step = float((w[step_up] * y[step_up] * (amounts[step_up] + fee + ops)).sum())

    baseline = float((w * y * (amounts + fee + ops)).sum())
    total = cost_review + cost_step + cost_allow
    return {
        "do_nothing_cost_inr": baseline,
        "total_cost_inr": total,
        "net_savings_inr": baseline - total,
        "review_band_net_inr": would_cost_review - cost_review,
        "stepup_band_net_inr": would_cost_step - cost_step,
        "n_review": float(w[review].sum()),
        "n_stepup": float(w[step_up].sum()),
        "n_allow": float(w[allow].sum()),
        "catches_review": float((w[review] * y[review]).sum()),
        "catches_stepup": float((w[step_up] * y[step_up]).sum()),
    }


def policy_bands_table(y, proba, amounts, t_allow: float, t_review: float,
                       weights=None) -> pd.DataFrame:
    """Volume, disputes and lift per band — the live form of 05_policy_bands.csv."""
    y = np.asarray(y, dtype=float)
    proba = np.asarray(proba, dtype=float)
    w = np.ones_like(y) if weights is None else np.asarray(weights, dtype=float)
    base_rate = float((w * y).sum() / w.sum())

    masks = [
        (ACTION_ALLOW, 0.0, t_allow, proba < t_allow),
        (ACTION_STEP_UP, t_allow, t_review, (proba >= t_allow) & (proba < t_review)),
        (ACTION_REVIEW, t_review, 1.0, proba >= t_review),
    ]
    rows = []
    for band, lo, hi, m in masks:
        n = float(w[m].sum())
        d = float((w[m] * y[m]).sum())
        rate = d / n if n else 0.0
        rows.append({"band": band, "lower": lo, "upper": hi, "n": n, "disputes": d,
                     "share_of_volume": n / w.sum(),
                     "dispute_rate_in_band": rate,
                     "lift_vs_base": rate / base_rate if base_rate else 0.0})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Sensitivity and segments, live
# --------------------------------------------------------------------------

def sensitivity_analysis(y, proba, amounts, base_params: dict, param_name: str,
                         param_range, weights=None) -> pd.DataFrame:
    """
    Re-optimise the band policy at each value of one parameter.

    `total_cost_inr` is exported alongside `net_savings_inr` precisely because
    net savings is NOT comparable across dispute_fee or ops_review_cost rows —
    both raise the baseline the saving is measured against. The open blocker on
    this asks for either the extra column or the caveat; this returns both.
    """
    rows = []
    for value in param_range:
        params = dict(base_params)
        params[param_name] = float(value)
        best = optimise_bands(y, proba, amounts, params, weights=weights)
        rows.append({
            "param_name": param_name,
            "param_value": float(value),
            "optimal_threshold": best["threshold_allow_stepup"],
            "threshold_stepup_review": best["threshold_stepup_review"],
            "n_review": best["n_review"],
            "n_stepup": best["n_stepup"],
            "total_cost_inr": best["total_cost_inr"],
            "do_nothing_cost_inr": best["do_nothing_cost_inr"],
            "net_savings_inr": best["net_savings_inr"],
            "comparable_across_rows": param_name not in BASELINE_SHIFTING_PARAMS,
        })
    return pd.DataFrame(rows)


def segment_economics_live(df: pd.DataFrame, params: dict, t_allow: float, t_review: float,
                           min_n: int = 300, weights=None) -> pd.DataFrame:
    """
    Every segment evaluated at the GLOBAL policy, decomposed into its review and
    step-up halves. The review column is the one that carries the finding: a
    segment can be profitable overall while a human reviewer on it loses money.
    """
    y = df["is_disputed"].to_numpy(float)
    p = df["proba_calibrated"].to_numpy(float)
    a = df["amount"].to_numpy(float)
    w = np.ones_like(y) if weights is None else np.asarray(weights, dtype=float)

    bucket = pd.cut(df["amount"], [-np.inf, 500, 2000, 10000, np.inf],
                    labels=["<500", "500-2000", "2000-10000", ">10000"])
    axes = {"amount_bucket": bucket.astype(str),
            "merchant_category": df["merchant_category"],
            "method": df["method"]}

    rows = []
    for seg_type, series in axes.items():
        for value in sorted(series.dropna().unique()):
            m = (series == value).to_numpy()
            if w[m].sum() < min_n:
                continue
            r = policy_cost(y[m], p[m], a[m], params, t_allow, t_review, weights=w[m])
            interventions = r["n_review"] + r["n_stepup"]
            rows.append({
                "segment_type": seg_type, "segment_value": value,
                "n": float(w[m].sum()), "positives": float((w[m] * y[m]).sum()),
                "dispute_rate": float((w[m] * y[m]).sum() / w[m].sum()),
                "mean_amount": float(np.average(a[m], weights=w[m])),
                "net_savings_at_global_policy": r["net_savings_inr"],
                "savings_per_txn": r["net_savings_inr"] / w[m].sum(),
                "savings_per_intervention": r["net_savings_inr"] / interventions if interventions else np.nan,
                "review_band_net_inr": r["review_band_net_inr"], "n_review": r["n_review"],
                "stepup_band_net_inr": r["stepup_band_net_inr"], "n_stepup": r["n_stepup"],
            })
    return pd.DataFrame(rows).sort_values("savings_per_intervention").reset_index(drop=True)


# --------------------------------------------------------------------------
# Which rows the live economics runs on
# --------------------------------------------------------------------------

def load_economics_basis() -> tuple[pd.DataFrame, np.ndarray, str, bool]:
    """
    Return (df, weights, source_label, is_exact).

    Prefers 04_test_predictions.csv: all 45,246 test rows, weight 1 each, and at
    default parameters the live optimiser reproduces the exported ₹1,199,620.186
    exactly — which makes Tab 3 a live cross-check of notebook 5 rather than a
    separate calculation that happens to look similar.

    Falls back to 05_scored_test_sample.csv with inverse sampling weights. That
    sample is STRATIFIED, not random (model_evaluation.md §4.10): all 308
    manual-review rows kept, 4,692 drawn from the other 44,938. Weighting by
    308/308 and 44938/4692 = 9.578 restores population scale, but it is an
    estimate: measured at ₹1,073,068 against the true ₹1,199,620, about 11% low,
    because the 83 sampled disputes stand in for 407. The app must label the
    curve as an estimate whenever this path is taken.
    """
    full = load_test_predictions()
    if full is not None:
        return full, np.ones(len(full)), "04_test_predictions.csv (45,246 rows, exact)", True

    sample = load_scored_sample()
    bands = load_policy_bands()
    n_pop = float(bands["n"].sum())
    n_pop_review = float(bands.loc[bands.band == ACTION_REVIEW, "n"].iloc[0])

    is_review = (sample["recommended_action"] == ACTION_REVIEW).to_numpy()
    n_s_review, n_s_other = is_review.sum(), (~is_review).sum()
    weights = np.where(is_review,
                       n_pop_review / max(n_s_review, 1),
                       (n_pop - n_pop_review) / max(n_s_other, 1))
    return sample, weights, "05_scored_test_sample.csv (5,000 rows, reweighted estimate)", False