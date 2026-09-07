"""
app/explain.py — per-row drivers and the reviewer note.

New code (dev plan §7.4), not ported from a notebook. Two jobs:

1. `top_drivers()` — why THIS row scored what it did. Because the deployed model
   is a logistic regression, this is not an approximation: the contribution of a
   term is exactly `coefficient x transformed value`, in log-odds. LLD §5.2
   hedged toward "importance x standardised value" as a SHAP-free stand-in;
   shipping a linear model means the real decomposition is available and the
   stand-in is not needed (model_building.md §8.6).

2. `generate_reviewer_note()` — an Anthropic API call when ANTHROPIC_API_KEY is
   set, and a deterministic template when it is not. The fallback is the path a
   judge sees by default (dev plan §9), so it is written to be genuinely
   readable rather than to be a placeholder.

The `informative` filter is not optional. Eighteen of 26 features fail the 2-sigma
permutation screen and six score at or below zero, so an unfiltered "top driver"
list will confidently tell a reviewer that a shuffled-noise column drove the
score (blockers.md, open item "the reviewer note quoting a meaningless feature").
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from scoring import ACTION_LABELS, ACTION_REVIEW, ACTION_STEP_UP, find_fitted_pipeline

# Default is a small model: the note is three sentences from a fixed prompt, so
# a larger one buys nothing. Override with CHARGEBACKLENS_LLM_MODEL.
DEFAULT_LLM_MODEL = os.environ.get("CHARGEBACKLENS_LLM_MODEL", "claude-haiku-4-5-20251001")

READABLE = {
    "log_amount": "transaction amount",
    "amount_vs_merchant_avg_ratio": "amount vs this merchant's typical ticket",
    "hour_of_day": "hour of day",
    "day_of_week": "day of week",
    "is_night_txn": "night-time transaction",
    "retry_count": "failed auth attempts before success",
    "checkout_latency_ms": "checkout latency",
    "is_foreign_bin": "foreign card BIN",
    "is_first_txn_for_device": "first transaction on this device",
    "account_age_days_at_txn": "account age at transaction",
    "account_age_implausible": "implausible account age",
    "refund_window_days": "merchant refund window",
    "delivery_sla_days_filled": "merchant delivery SLA",
    "is_physical_goods": "physical goods",
    "phone_verified": "phone verified",
    "txns_last_24h": "transactions in the last 24h",
    "txns_last_7d": "transactions in the last 7 days",
    "distinct_devices_30d": "distinct devices in 30 days",
    "prior_disputes_before_this_txn": "prior disputes before this transaction",
    "amount_vs_own_avg": "amount vs the customer's own average",
    "has_prior_history": "has prior transaction history",
    "ip_state_changed_from_prev_txn": "IP state changed since last transaction",
    "merchant_dispute_rate_trailing_90d": "merchant's trailing 90-day dispute rate",
    "method": "payment method",
    "merchant_category": "merchant category",
    "email_domain_type": "email domain type",
}


def readable(feature: str) -> str:
    return READABLE.get(feature, feature.replace("_", " "))


def _split_term(term: str, categorical_cols: list[str]) -> tuple[str, str | None]:
    """
    Map a post-ColumnTransformer term back to (contract feature, level).

    `num__log_amount` -> ("log_amount", None)
    `cat__method_upi` -> ("method", "upi")
    """
    if term.startswith("num__"):
        return term[len("num__"):], None
    if term.startswith("cat__"):
        rest = term[len("cat__"):]
        for base in sorted(categorical_cols, key=len, reverse=True):
            if rest.startswith(base + "_"):
                return base, rest[len(base) + 1:]
        return rest, None
    return term, None


def _describe(feature: str, level: str | None, raw_value) -> str:
    """
    A driver label a reviewer can read without decoding an encoding.

    Without this, a negative coefficient on an absent flag reads as "phone
    verified: raises risk", which is exactly backwards — the risk comes from the
    phone NOT being verified. Naming the row's own value fixes that.
    """
    label = readable(feature)
    # `level` arrives from a pandas column, so a "no level" numeric term can come
    # back as NaN rather than None depending on the inferred dtype. Test for a
    # real string instead of `is not None`, or every numeric driver reads "= nan".
    if isinstance(level, str) and level:
        return f"{label} = {level}"
    if raw_value is None or (isinstance(raw_value, float) and np.isnan(raw_value)):
        return label
    if feature.startswith(("is_", "has_")) or feature in ("phone_verified", "account_age_implausible"):
        return f"{label}: {'yes' if float(raw_value) >= 0.5 else 'no'}"
    if feature == "log_amount":
        return f"{label} (Rs {np.expm1(float(raw_value)):,.0f})"
    if float(raw_value) == int(float(raw_value)):
        return f"{label} = {int(float(raw_value))}"
    return f"{label} = {float(raw_value):,.3g}"


def top_drivers(model, feature_row: pd.DataFrame, coefficients: pd.DataFrame,
                importances: pd.DataFrame, categorical_cols: list[str],
                k: int = 5, informative_only: bool = True) -> pd.DataFrame:
    """
    Exact per-term log-odds contributions for one row, ranked by absolute size.

    Pushes the row through the fitted ColumnTransformer to get the same design
    vector the classifier saw, then multiplies element-wise by the exported
    coefficients, matched on term name. `get_feature_names_out()` returns exactly
    the 38 terms in 04_model_coefficients.csv (verified), so the join is total,
    not best-effort.

    Degrades to an importance-ranked list if the preprocessor cannot be reached
    inside the pickle — the caller can tell which happened from the `method`
    attribute on the returned frame.
    """
    pipe = find_fitted_pipeline(model)
    prep = None
    if pipe is not None:
        prep = pipe.named_steps.get("prep") or next(iter(pipe.named_steps.values()), None)

    informative = set(importances.loc[importances["informative"].astype(bool), "feature"])

    design = None
    if prep is not None:
        try:
            values = np.asarray(prep.transform(feature_row)).ravel()
            names = list(prep.get_feature_names_out())
            design = pd.DataFrame({"term": names, "value": values})
        except Exception:
            design = None

    if design is not None:
        df = design.merge(coefficients[["term", "coefficient"]], on="term", how="inner")
        df["contribution"] = df["coefficient"] * df["value"]
        split = [_split_term(t, categorical_cols) for t in df["term"]]
        df["feature"] = [s[0] for s in split]
        df["level"] = [s[1] for s in split]
        df.attrs["method"] = "coefficient x transformed value (exact log-odds)"
    else:
        df = importances.rename(columns={"importance": "contribution"}).copy()
        df["term"] = df["feature"]
        df["level"] = None
        df["value"] = np.nan
        df["coefficient"] = np.nan
        df.attrs["method"] = "permutation importance (preprocessor unreachable — ranking only)"

    if informative_only:
        df = df[df["feature"].isin(informative)]

    # A one-hot term for a level the row does NOT have contributes exactly zero,
    # so it can never rank — but drop it explicitly rather than relying on that.
    df = df[~((df["level"].notna()) & (df["value"].fillna(1) == 0))]

    raw = {c: feature_row.iloc[0][c] for c in feature_row.columns}
    df["label"] = [_describe(f, lv, raw.get(f)) for f, lv in zip(df["feature"], df["level"])]
    df["direction"] = np.where(df["contribution"] >= 0, "raises risk", "lowers risk")
    out = (df.reindex(df["contribution"].abs().sort_values(ascending=False).index)
             .head(k)
             .reset_index(drop=True))
    out.attrs["method"] = df.attrs["method"]
    return out


# --------------------------------------------------------------------------
# The note
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """You write one short note for a payments risk reviewer at an Indian PSP.

Rules, all of them hard:
- 2 to 3 sentences. No preamble, no bullet points, no headings, no sign-off.
- Use ONLY the facts in the input block. Invent nothing: no customer names, no
  card details, no history, no claim about intent or fraud.
- Never assert the transaction IS fraudulent or WILL be disputed. The score is a
  calibrated probability, not a verdict.
- Name the specific drivers you were given, in plain language a reviewer can act on.
- End with the recommended action, stated as the recommendation it is.
- This is a defensive triage tool. Do not suggest how a bad actor could evade
  detection, and do not speculate about attack techniques."""


def _driver_lines(drivers: pd.DataFrame) -> str:
    lines = []
    for _, r in drivers.iterrows():
        piece = f"- {r['label']}: {r['direction']}"
        if pd.notna(r.get("value")):
            piece += f" (contribution {r['contribution']:+.3f} log-odds)"
        lines.append(piece)
    return "\n".join(lines) if lines else "- no driver cleared the informativeness screen"


def template_note(probability: float, action: str, drivers: pd.DataFrame,
                  amount: float | None = None, base_rate: float = 0.008995) -> str:
    """
    Deterministic fallback. Runs with no API key, no network, and no variance,
    which is what makes it the right default for a demo.
    """
    lift = probability / base_rate if base_rate else float("nan")
    named = [d["label"] for _, d in drivers.iterrows() if d["direction"] == "raises risk"][:2]
    lowering = [d["label"] for _, d in drivers.iterrows() if d["direction"] == "lowers risk"][:1]

    first = (f"Scored {probability:.2%} against a {base_rate:.2%} portfolio base rate "
             f"({lift:.1f}x).")
    if amount is not None:
        first = first[:-1] + f" on a transaction of Rs {amount:,.0f}."

    if named:
        second = "Risk is driven mainly by " + " and ".join(named) + "."
    else:
        second = "No individual driver cleared the informativeness screen; the score comes from small combined effects."
    if lowering:
        second += f" Working against that: {lowering[0]}."

    if action == ACTION_REVIEW:
        third = "Recommended: manual review before capture."
    elif action == ACTION_STEP_UP:
        third = "Recommended: 3DS step-up rather than a hold — the friction cost is below the expected dispute exposure at this score."
    else:
        third = "Recommended: allow — the expected dispute cost here is below the cost of intervening."
    return f"{first} {second} {third}"


def generate_reviewer_note(probability: float, action: str, drivers: pd.DataFrame,
                           merchant_policy_text: str = "",
                           amount: float | None = None,
                           base_rate: float = 0.008995,
                           api_key: str | None = None,
                           model: str = DEFAULT_LLM_MODEL) -> tuple[str, str]:
    """
    Returns (note, source) where source is "anthropic-api" or "template".

    Any failure — no key, no package, network error, empty response — falls
    through to template_note(). The app never shows an error where a note
    should be, because the fallback is the specified behaviour and not an
    error condition (LLD §5.5).
    """
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return template_note(probability, action, drivers, amount, base_rate), "template"

    payload = (
        f"Calibrated dispute probability: {probability:.4f} "
        f"({probability / base_rate:.1f}x the {base_rate:.4%} portfolio base rate)\n"
        + (f"Transaction amount: Rs {amount:,.0f}\n" if amount is not None else "")
        + f"Policy recommendation: {ACTION_LABELS.get(action, action)}\n"
        + f"Top drivers for this transaction (exact log-odds contributions):\n{_driver_lines(drivers)}\n"
        + (f"Merchant policy context: {merchant_policy_text}\n" if merchant_policy_text else "")
    )

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": payload}],
        )
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise ValueError("empty response")
        return text, "anthropic-api"
    except Exception:
        return template_note(probability, action, drivers, amount, base_rate), "template"