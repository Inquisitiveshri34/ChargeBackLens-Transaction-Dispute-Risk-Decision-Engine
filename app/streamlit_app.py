"""
app/streamlit_app.py — ChargebackLens.

Reads the frozen artifacts from notebooks 01-05. Never trains, never touches
data/raw/, and does live inference in exactly one place (Tab 1's form). Tab 2 is
a pure read of an already-scored sample; Tab 3 recomputes economics but never
the model.

Run:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import math
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import economics as ec
import explain as ex
import scoring as sc

st.set_page_config(page_title="ChargebackLens", page_icon="₹", layout="wide")

TEST_BASE_RATE = 0.008995          # 05_model_comparison.csv
ACTION_COLOR = {sc.ACTION_ALLOW: "#2e7d32", sc.ACTION_STEP_UP: "#ef6c00", sc.ACTION_REVIEW: "#c62828"}


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------

def rupees(x, decimals: int = 0) -> str:
    """Indian digit grouping: 1199620 -> ₹11,99,620, not ₹1,199,620."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    negative = x < 0
    whole = int(round(abs(float(x)), decimals))
    digits = str(whole)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"{'−' if negative else ''}₹{digits}"


# --------------------------------------------------------------------------
# Cached loaders (LLD §5.1)
#   @st.cache_resource for the model  — one unpickled object per server process
#   @st.cache_data     for the CSVs   — content-hashed, treated as immutable
# Mixing these two up is the most common Streamlit caching bug, so they are
# split here deliberately rather than decorated uniformly.
# --------------------------------------------------------------------------

@st.cache_resource(show_spinner="Loading the calibrated model…")
def get_model():
    return sc.load_model()


@st.cache_data(show_spinner="Loading artifacts…")
def get_artifacts() -> dict:
    cols, numeric, categorical = sc.load_feature_columns()
    return {
        "feature_columns": cols, "numeric_cols": numeric, "categorical_cols": categorical,
        "params": sc.load_economics_params(),
        "card": sc.load_model_card(),
        "sample": sc.load_scored_sample(),
        "bands": sc.load_policy_bands(),
        "sweep": sc.load_threshold_sweep(),
        "segments": sc.load_segment_economics(),
        "sensitivity": sc.load_sensitivity(),
        "censoring": sc.load_censoring_audit(),
        "comparison": sc.load_model_comparison(),
        "calibration": sc.load_calibration_curve(),
        "importances": sc.load_feature_importances(),
        "coefficients": sc.load_model_coefficients(),
    }


@st.cache_data(show_spinner="Loading the economics basis…")
def get_basis():
    df, weights, label, exact = ec.load_economics_basis()
    return df, weights, label, exact


@st.cache_data(show_spinner=False)
def run_policy(params_key: tuple, _df: pd.DataFrame, _weights: np.ndarray) -> dict:
    """
    Live band optimisation, cached on the PARAMETER VALUES.

    Caching here is safe and caching is the point: keyed on params_key, the
    function recomputes the moment a slider moves and reuses the result when it
    does not. (LLD §5.4 warns about the opposite mistake — a cache that makes
    the chart look static because it never sees the new parameters.)
    """
    params = dict(zip(ec.COST_PARAM_KEYS, params_key))
    y = _df["is_disputed"].to_numpy(float)
    p = _df["proba_calibrated"].to_numpy(float)
    a = _df["amount"].to_numpy(float)
    best = ec.optimise_bands(y, p, a, params, weights=_weights)
    sweep = ec.threshold_sweep(y, p, a, params, weights=_weights)
    return {"best": best, "sweep": sweep, "params": params}


# --------------------------------------------------------------------------
# Boot
# --------------------------------------------------------------------------

try:
    ART = get_artifacts()
    MODEL = get_model()
    CONTRACT = sc.assert_model_contract(MODEL, ART["feature_columns"])
except sc.ArtifactError as err:
    st.error("**Artifact contract failed at boot — refusing to score.**")
    st.code(str(err))
    st.stop()

PARAMS = ART["params"]
T_ALLOW = PARAMS["threshold_allow_stepup"]
T_REVIEW = PARAMS["threshold_stepup_review"]

st.title("ChargebackLens")
st.caption(
    f"Calibrated dispute risk → rupee-optimal routing · "
    f"{ART['card'].get('selected_model')} + {ART['card'].get('calibration_method')} calibration · "
    f"{CONTRACT['n_columns']} features · scikit-learn {ART['card'].get('sklearn_version')} · "
    "defense-only scope (SCOPE.md)"
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Net savings at the deployed policy", rupees(PARAMS["net_savings_inr_at_policy"]),
          f"{PARAMS['net_savings_inr_at_policy'] / PARAMS['do_nothing_cost_inr']:.1%} of exposure")
c2.metric("Lift at the top 1% of the queue", "16.2×", "precision 14.6%")
c3.metric("Manual-review band", f"{int(ART['bands'].loc[ART['bands'].band == sc.ACTION_REVIEW, 'n'].iloc[0]):,} txns",
          f"{ART['bands'].loc[ART['bands'].band == sc.ACTION_REVIEW, 'lift_vs_base'].iloc[0]:.1f}× base rate")
c4.metric("Test base rate", f"{TEST_BASE_RATE:.3%}", "407 disputes in 45,246")

# Four caveats, at the top and not in a footnote. A submission that reports the
# savings without these is reporting a larger number and a smaller result
# (model_evaluation.md §8).
with st.expander("⚠️ Four things to read before the rupee figures", expanded=False):
    cen = ART["censoring"]
    st.markdown(f"""
1. **{int(cen['raised_after_snapshot'])} of {int(cen['test_positives'])} test disputes
   ({cen['share_after_snapshot']:.1%}) were raised *after* the declared 2026-11-01 snapshot**,
   the latest on {pd.Timestamp(cen['max_raised_at']).date()}. Ranking is unaffected — every feature is
   time-gated and notebook 3's tripwire passed — but the label counts three months of future
   disputes, so absolute rupee figures are scaled to exposure a real operator could not yet
   have measured.
2. **Every rupee figure is a floor, not an estimate.** The model under-predicts in decile 9 by
   +1.15pp (3.93% predicted against 5.08% observed), so the expected-cost calculation understates
   savings exactly where the policy operates. This errs in the safe direction, but it is a
   property of the number, not a disclaimer.
3. **The conclusion is robust; the operating point is not.** Net savings stay positive from
   ₹10.9L to ₹18.1L across step-up abandon rates 0.10–0.40, but the allow/step-up cut moves 3.1×.
   `step_up_abandon_rate` is the one parameter a merchant must measure rather than assume.
4. **One band of one segment loses money.** Manual review on `method = wallet` nets −₹300 across
   one review and zero catches, while its step-up band earns ₹9,779. The finding is about routing
   the queue by ticket size, not about skipping wallet entirely.
""")

tab_score, tab_queue, tab_econ = st.tabs(
    ["Score a Transaction", "Review Queue", "Economics Explorer"])


# ==========================================================================
# Tab 1 — Score a transaction
# ==========================================================================

with tab_score:
    st.subheader("Score a single transaction")
    st.caption(
        "The eight trailing features below are **manual-override sliders**. In production they are "
        "computed from the customer's and merchant's prior history with `closed='left'` windows; the "
        "app has no history at form-entry time, so they are exposed as inputs. This is a demo path, "
        "not the production path."
    )

    left, mid, right = st.columns(3)

    with left:
        st.markdown("**Transaction**")
        amount = st.number_input("Amount (₹)", min_value=1.0, max_value=500_000.0,
                                 value=8_500.0, step=100.0)
        method = st.selectbox("Method", sc.CATEGORICAL_LEVELS["method"])
        merchant_category = st.selectbox("Merchant category", sc.CATEGORICAL_LEVELS["merchant_category"])
        created_at = pd.Timestamp(st.date_input("Date", value=pd.Timestamp("2026-09-15").date())) \
            + pd.Timedelta(hours=st.slider("Hour of day", 0, 23, 22))
        retry_count = st.number_input("Retry count (failed auths before success)", 0, 10, 0)
        checkout_latency_ms = st.number_input("Checkout latency (ms)", 0, 30_000, 2_600, step=100)

    with mid:
        st.markdown("**Customer & merchant**")
        defaults = sc.MERCHANT_DEFAULTS[merchant_category]
        merchant_avg_ticket = st.number_input(
            "Merchant average ticket size (₹)", min_value=1.0, value=float(defaults["avg_ticket_size"]),
            step=50.0, help="Drives amount_vs_merchant_avg_ratio. Defaults are per-category medians.")
        email_domain_type = st.selectbox("Email domain type", sc.CATEGORICAL_LEVELS["email_domain_type"])
        phone_verified = st.checkbox("Phone verified", value=True)
        account_age_days_at_txn = st.slider("Account age at transaction (days)", 0, 2_500, 450)
        is_first_txn_for_device = st.checkbox("First transaction on this device", value=False)
        is_foreign_bin = st.checkbox("Foreign card BIN", value=False)
        is_physical_goods = st.checkbox("Physical goods", value=bool(defaults["is_physical_goods"]))
        refund_window_days = st.number_input("Refund window (days)", 0, 60, int(defaults["refund_window_days"]))
        delivery_sla_days = st.number_input("Delivery SLA (days)", 0, 30, int(defaults["delivery_sla_days"]),
                                            disabled=not is_physical_goods)

    with right:
        st.markdown("**Trailing history** (manual override)")
        txns_last_24h = st.slider("Transactions in last 24h", 0, 5, 0)
        txns_last_7d = st.slider("Transactions in last 7 days", 0, 10, 0)
        distinct_devices_30d = st.slider("Distinct devices in 30 days", 0, 6, 1)
        prior_disputes = st.slider("Prior disputes before this transaction", 0, 5, 0)
        has_prior_history = st.checkbox("Has any prior transaction", value=True)
        ip_state_changed = st.checkbox("IP state changed since last transaction", value=True)
        amount_vs_own_avg = st.slider("Amount vs own 30-day average", 0.1, 10.0, 1.0, step=0.1,
                                      help="1.0 is also the sentinel for 'no 30-day history to compare against'.")
        merchant_rate = st.slider("Merchant trailing 90-day dispute rate", 0.001, 0.030, 0.007, step=0.001)

    if st.button("Score transaction", type="primary"):
        form = {
            "amount": amount, "created_at": created_at,
            "merchant_avg_ticket_size": merchant_avg_ticket,
            "retry_count": retry_count, "checkout_latency_ms": checkout_latency_ms,
            "is_foreign_bin": is_foreign_bin, "is_first_txn_for_device": is_first_txn_for_device,
            "account_age_days_at_txn": account_age_days_at_txn,
            "refund_window_days": refund_window_days, "delivery_sla_days": delivery_sla_days,
            "is_physical_goods": is_physical_goods, "phone_verified": phone_verified,
            "method": method, "merchant_category": merchant_category,
            "email_domain_type": email_domain_type,
            "txns_last_24h": float(txns_last_24h), "txns_last_7d": float(txns_last_7d),
            "distinct_devices_30d": float(distinct_devices_30d),
            "prior_disputes_before_this_txn": prior_disputes,
            "amount_vs_own_avg": amount_vs_own_avg,
            "has_prior_history": int(has_prior_history),
            "ip_state_changed_from_prev_txn": int(ip_state_changed),
            "merchant_dispute_rate_trailing_90d": merchant_rate,
        }
        row = sc.build_feature_row(form, ART["feature_columns"], ART["categorical_cols"])
        proba = sc.score_transaction(MODEL, row)
        action = sc.recommend_action(proba, PARAMS)
        drivers = ex.top_drivers(MODEL, row, ART["coefficients"], ART["importances"],
                                 ART["categorical_cols"], k=5)

        st.divider()
        m1, m2, m3 = st.columns([1, 1, 2])
        m1.metric("Dispute probability", f"{proba:.2%}", f"{proba / TEST_BASE_RATE:.1f}× base rate")
        m2.metric("Recommended action", sc.ACTION_LABELS[action])
        with m3:
            costs = ec.expected_cost_matrix(amount, PARAMS)
            st.markdown(
                f"**Why this band** · allowing and being wrong costs {rupees(costs['fn_cost'])}; "
                f"a 3DS step-up costs {rupees(costs['fp_cost'])} in expected abandonment; "
                f"a human review costs {rupees(costs['tp_cost'])}. Band cuts: "
                f"{T_ALLOW:.4f} / {T_REVIEW:.4f}."
            )

        d1, d2 = st.columns([3, 2])
        with d1:
            plot = drivers.iloc[::-1]
            fig = go.Figure(go.Bar(
                x=plot["contribution"], y=plot["label"], orientation="h",
                marker_color=["#c62828" if v >= 0 else "#2e7d32" for v in plot["contribution"]],
                hovertemplate="%{y}<br>%{x:+.3f} log-odds<extra></extra>"))
            fig.update_layout(title="Drivers for this transaction (log-odds contribution)",
                              xaxis_title="← lowers risk    ·    raises risk →",
                              height=300, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                f"Method: {drivers.attrs['method']}. Only features passing the 2σ permutation screen "
                "in `04_feature_importances.csv` are eligible — 18 of 26 fail it and 6 score at or "
                "below zero, so an unfiltered list would name shuffled noise as a driver."
            )
        with d2:
            note, source = ex.generate_reviewer_note(
                proba, action, drivers, amount=amount, base_rate=TEST_BASE_RATE)
            st.markdown("**Reviewer note**")
            st.info(note)
            st.caption(
                "Generated by the Anthropic API." if source == "anthropic-api"
                else "Deterministic template — `ANTHROPIC_API_KEY` is not set. This is the default "
                     "path and is exercised on every boot without a key.")

        with st.expander("The exact feature row sent to the model"):
            st.dataframe(row.T.rename(columns={0: "value"}), use_container_width=True)


# ==========================================================================
# Tab 2 — Review queue
# ==========================================================================

with tab_queue:
    st.subheader("Review queue")
    sample = ART["sample"]
    st.caption(
        f"Pre-scored, no live inference. **This 5,000-row sample is stratified, not random**: all "
        f"{int(ART['bands'].loc[ART['bands'].band == sc.ACTION_REVIEW, 'n'].iloc[0])} manual-review rows "
        "were kept and the rest drawn from everything else, so its dispute rate is *not* the "
        "population rate and is never quoted as one. `risk_percentile` is a rank within the full "
        "45,246-row test set."
    )

    top_k_pct = st.slider("Work down the top k% of the queue", 0.5, 25.0, 5.0, step=0.5)
    k = max(1, int(round(len(sample) * top_k_pct / 100)))
    queue = sample.sort_values("proba_calibrated", ascending=False).head(k)

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Transactions in slice", f"{k:,}")
    q2.metric("Disputes caught", f"{int(queue.is_disputed.sum()):,}")
    q3.metric("Precision within slice", f"{queue.is_disputed.mean():.2%}")
    q4.metric("Exposure in slice", rupees(queue.loc[queue.is_disputed == 1, 'amount'].sum()))
    st.caption(
        "Precision is computed within the stratified sample, so it is an ordering diagnostic — the "
        "population figures are precision@1% = 14.6% (16.2× lift) and precision@5% = 7.78% "
        "(recall 43.2%), both from `05_model_comparison.csv`."
    )

    display = queue.assign(
        risk=lambda d: (d.proba_calibrated * 100).round(2),
        percentile=lambda d: (d.risk_percentile * 100).round(2),
    )[["payment_id", "created_at", "amount", "method", "merchant_category",
       "risk", "percentile", "recommended_action", "is_disputed"]]

    selection = st.dataframe(
        display, use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row",
        column_config={
            "amount": st.column_config.NumberColumn("Amount", format="₹%.0f"),
            "risk": st.column_config.NumberColumn("Risk %", format="%.2f%%"),
            "percentile": st.column_config.NumberColumn("Percentile", format="%.2f"),
            "is_disputed": st.column_config.CheckboxColumn("Disputed (label)"),
            "created_at": st.column_config.DatetimeColumn("Created", format="YYYY-MM-DD HH:mm"),
        },
    )

    rows = selection.selection.rows if hasattr(selection, "selection") else []
    if rows:
        picked = queue.iloc[rows[0]]
        st.divider()
        st.markdown(f"### {picked.payment_id}")
        s1, s2, s3 = st.columns(3)
        s1.metric("Dispute probability", f"{picked.proba_calibrated:.2%}",
                  f"{picked.proba_calibrated / TEST_BASE_RATE:.1f}× base rate")
        s2.metric("Recommended action", sc.ACTION_LABELS[sc.recommend_action(picked.proba_calibrated, PARAMS)])
        s3.metric("Amount", rupees(picked.amount))

        # Same code path as Tab 1 — importance-ranked here, because the queue
        # sample carries 18 display columns rather than the 26 fitted ones, so
        # there is no design row to decompose without refitting the transform.
        eligible = ART["importances"].query("informative").copy()
        eligible["present"] = [
            picked.get(f, np.nan) if f in picked.index else np.nan for f in eligible.feature]
        eligible = eligible.dropna(subset=["present"])
        drivers = pd.DataFrame({
            "feature": eligible.feature,
            "label": [ex._describe(f, None, v) for f, v in zip(eligible.feature, eligible.present)],
            "contribution": eligible.importance,
            "value": eligible.present,
            "direction": "raises risk",
        }).head(4)
        note, source = ex.generate_reviewer_note(
            float(picked.proba_calibrated),
            sc.recommend_action(picked.proba_calibrated, PARAMS),
            drivers, amount=float(picked.amount), base_rate=TEST_BASE_RATE)
        st.info(note)
        st.caption("Same note generator as Tab 1 — one code path, not a duplicate. "
                   + ("Anthropic API." if source == "anthropic-api" else "Template fallback."))


# ==========================================================================
# Tab 3 — Economics explorer
# ==========================================================================

with tab_econ:
    st.subheader("Economics explorer")
    basis_df, basis_w, basis_label, basis_exact = get_basis()
    st.caption(f"Recomputed live on **{basis_label}**." + ("" if basis_exact else
               " Reweighted to population scale by inverse sampling weights; measured about 11% "
               "below the exact figure, so read the curve's shape rather than its level."))

    e1, e2, e3, e4 = st.columns(4)
    dispute_fee = e1.slider("Dispute fee (₹)", 500, 3000, int(PARAMS["dispute_fee"]), step=100)
    ops_review_cost = e2.slider("Ops review cost (₹)", 100, 800, int(PARAMS["ops_review_cost"]), step=50)
    merchant_margin = e3.slider("Merchant margin", 0.05, 0.35, float(PARAMS["merchant_margin"]), step=0.01)
    abandon_rate = e4.slider("Step-up abandon rate", 0.05, 0.50, float(PARAMS["step_up_abandon_rate"]), step=0.01,
                             help="The one parameter a merchant must measure rather than assume: "
                                  "the optimal allow/step-up cut moves 3.1× across 0.10–0.40.")

    key = (float(dispute_fee), float(ops_review_cost), float(merchant_margin), float(abandon_rate))
    result = run_policy(key, basis_df, basis_w)
    best, sweep = result["best"], result["sweep"]
    at_default = np.allclose(key, [PARAMS[k] for k in ec.COST_PARAM_KEYS])

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Net savings (three-band)", rupees(best["net_savings_inr"]),
              f"{best['net_savings_inr'] / best['do_nothing_cost_inr']:.1%} of exposure")
    r2.metric("Allow / step-up cut", f"{best['threshold_allow_stepup']:.4f}")
    r3.metric("Step-up / review cut", f"{best['threshold_stepup_review']:.4f}")
    r4.metric("Interventions", f"{int(best['n_review'] + best['n_stepup']):,}",
              f"{int(best['n_review']):,} review · {int(best['n_stepup']):,} step-up")

    if at_default and basis_exact:
        st.success(
            f"At default parameters the live optimiser reproduces the exported policy exactly: "
            f"{rupees(PARAMS['net_savings_inr_at_policy'])} at cuts {T_ALLOW:.4f} / {T_REVIEW:.4f}. "
            "This tab is a live cross-check of notebook 5, not a parallel calculation."
        )
    binary_best = sweep.loc[sweep.net_savings_inr.idxmax()]
    st.caption(
        f"A single-threshold policy on the same parameters earns {rupees(binary_best.net_savings_inr)}. "
        f"The second cut is worth {rupees(best['net_savings_inr'] - binary_best.net_savings_inr)} — "
        "the measured justification for two thresholds instead of one."
    )
    if key[0] != PARAMS["dispute_fee"] or key[1] != PARAMS["ops_review_cost"]:
        st.warning(
            "`dispute_fee` and `ops_review_cost` both sit inside `fn_cost`, so moving either also "
            "raises the do-nothing baseline that net savings is measured against. Net savings is "
            f"**not comparable** to the default run — compare total cost instead "
            f"({rupees(best['total_cost_inr'])} now).",
            icon="⚠️")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sweep.threshold, y=sweep.net_savings_inr, mode="lines",
                             name="Net savings (single threshold)", line=dict(width=2)))
    # Numeric x-axis, so add_vline with an annotation is safe here — the plotly
    # 5.x TypeError in BLK-001 only fires on a *date* axis.
    fig.add_vline(x=best["threshold_allow_stepup"], line_dash="dot", line_color="#ef6c00",
                  annotation_text="allow / step-up", annotation_position="top right")
    fig.add_vline(x=best["threshold_stepup_review"], line_dash="dot", line_color="#c62828",
                  annotation_text="step-up / review", annotation_position="top right")
    fig.add_hline(y=0, line_color="#999", line_width=1)
    fig.update_layout(height=380, xaxis_title="Threshold on calibrated probability",
                      yaxis_title="Net savings (₹)", margin=dict(l=10, r=10, t=30, b=10),
                      xaxis_range=[0, float(np.quantile(basis_df.proba_calibrated, 0.999))])
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "The grid is 101 points drawn from **quantiles of the score**, not `linspace(0.01, 0.99)`: "
        "the model's maximum test probability is 0.334, so two-thirds of a linear grid would flag "
        "zero rows and the apparent optimum would be an artifact of the grid."
    )

    st.markdown("#### Where the policy should and should not be deployed")
    live_segments = st.toggle("Recompute segments at the current sliders", value=False,
                              help="Off shows the frozen 05_segment_economics.csv, which is the "
                                   "table every quoted segment number traces back to.")
    if live_segments:
        seg = ec.segment_economics_live(basis_df, result["params"],
                                        best["threshold_allow_stepup"], best["threshold_stepup_review"],
                                        weights=basis_w)
    else:
        seg = ART["segments"].sort_values("savings_per_intervention")

    st.dataframe(
        seg[["segment_type", "segment_value", "n", "dispute_rate", "mean_amount",
             "net_savings_at_global_policy", "savings_per_intervention",
             "review_band_net_inr", "n_review", "stepup_band_net_inr", "n_stepup"]],
        use_container_width=True, hide_index=True,
        column_config={
            "n": st.column_config.NumberColumn("n", format="%.0f"),
            "dispute_rate": st.column_config.NumberColumn("Dispute rate", format="%.3f%%"),
            "mean_amount": st.column_config.NumberColumn("Mean amount", format="₹%.0f"),
            "net_savings_at_global_policy": st.column_config.NumberColumn("Net @ global policy", format="₹%.0f"),
            "savings_per_intervention": st.column_config.NumberColumn("Per intervention", format="₹%.0f"),
            "review_band_net_inr": st.column_config.NumberColumn("Review band net", format="₹%.0f"),
            "stepup_band_net_inr": st.column_config.NumberColumn("Step-up band net", format="₹%.0f"),
        })
    st.caption(
        "Segments are evaluated at the **global** policy, not optimised within themselves — a "
        "per-segment optimum is non-negative by construction and so can never identify a segment "
        "worth skipping. Read the review-band column: `method = wallet` nets −₹300 across one "
        "review and zero catches while its step-up band earns ₹9,779, and `amount > ₹10,000` "
        "returns ₹1,434 per intervention, 31× wallet's ₹47. The conclusion is to route the review "
        "queue by ticket size, not to skip wallet."
    )

    with st.expander("Frozen sensitivity analysis (05_sensitivity_analysis.csv)"):
        st.dataframe(ART["sensitivity"], use_container_width=True, hide_index=True)
        st.caption(
            "Rows are comparable on `net_savings_inr` within `merchant_margin` and "
            "`step_up_abandon_rate`, and **not** within `dispute_fee` or `ops_review_cost` — both "
            "of those raise the do-nothing baseline as well as the cost, so a larger saving there "
            "can hide a worse policy."
        )