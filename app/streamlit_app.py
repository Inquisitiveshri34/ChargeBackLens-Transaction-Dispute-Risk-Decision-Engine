from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from economics import format_inr


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="ChargebackLens",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"


# ============================================================
# CUSTOM STYLING
# ============================================================

st.markdown(
    """
    <style>

        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1450px;
        }

        .brand-title {
            font-size: 1.45rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            margin-bottom: 0.15rem;
        }

        .brand-subtitle {
            font-size: 0.78rem;
            opacity: 0.65;
            margin-bottom: 1.5rem;
        }

        .hero {
            padding: 2.5rem 2.75rem;
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 16px;
            margin-bottom: 2.5rem;
        }

        .hero-title {
            font-size: 2.7rem;
            font-weight: 750;
            letter-spacing: -0.045em;
            margin-bottom: 0.6rem;
        }

        .hero-subtitle {
            font-size: 1.1rem;
            line-height: 1.65;
            opacity: 0.72;
            max-width: 900px;
        }

        .section-card {
            padding: 1.5rem;
            border: 1px solid rgba(128, 128, 128, 0.22);
            border-radius: 12px;
            min-height: 185px;
            height: auto;
        }

        .section-number {
            font-size: 0.75rem;
            font-weight: 700;
            opacity: 0.55;
            letter-spacing: 0.08em;
            margin-bottom: 0.6rem;
        }

        .section-card h3 {
            margin: 0 0 0.7rem 0;
            font-size: 1.15rem;
        }

        .section-card p {
            margin: 0;
            line-height: 1.6;
            opacity: 0.72;
            font-size: 0.92rem;
        }

        .workflow-step {
            padding: 1.05rem 1.25rem;
            border-left: 3px solid rgba(128, 128, 128, 0.45);
            margin-bottom: 0.85rem;
        }

        .workflow-title {
            font-weight: 650;
            margin-bottom: 0.25rem;
        }

        .workflow-description {
            opacity: 0.7;
            line-height: 1.5;
        }

        .policy-card {
            padding: 0.4rem 0;
        }

        .policy-title {
            font-weight: 700;
            font-size: 0.95rem;
            margin-bottom: 1rem;
        }

        .policy-number {
            font-size: 1.7rem;
            font-weight: 650;
            margin-top: 0.2rem;
        }

        .policy-subtext {
            font-size: 0.82rem;
            opacity: 0.65;
            margin-top: 0.35rem;
        }

        .metric-label {
            font-size: 0.82rem;
            opacity: 0.7;
            margin-bottom: 0.15rem;
        }

        .metric-value {
            font-size: 1.65rem;
            font-weight: 700;
        }

        .action-box {
            padding: 1rem 1.2rem;
            border-radius: 10px;
            border: 1px solid rgba(128,128,128,0.25);
        }

        .dev-box {
            padding: 3rem 2rem;
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 16px;
            text-align: center;
            margin-top: 2rem;
        }

        .dev-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
            opacity: 0.65;
        }

        .dev-title {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.7rem;
        }

        .dev-text {
            opacity: 0.7;
            max-width: 650px;
            margin: 0 auto;
            line-height: 1.6;
        }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# DATA LOADING
# ============================================================

@st.cache_data
def load_scored_sample():

    path = PROCESSED / "05_scored_test_sample.csv"

    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)

    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(
            df["created_at"],
            errors="coerce",
        )

    return df


@st.cache_data
def load_policy_bands():

    path = PROCESSED / "05_policy_bands.csv"

    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


@st.cache_data
def load_economics_params():

    path = PROCESSED / "05_economics_params.csv"

    if not path.exists():
        return {}

    df = pd.read_csv(path)

    if "param" not in df.columns or "value" not in df.columns:
        return {}

    return dict(
        zip(
            df["param"],
            df["value"],
        )
    )


@st.cache_data
def load_threshold_sweep():

    path = PROCESSED / "05_threshold_sweep.csv"

    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


@st.cache_data
def load_sensitivity():

    path = PROCESSED / "05_sensitivity_analysis.csv"

    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


@st.cache_data
def load_segment_economics():

    path = PROCESSED / "05_segment_economics.csv"

    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


# ============================================================
# HELPERS
# ============================================================

def pct(value, digits=1):

    if pd.isna(value):
        return "—"

    return f"{float(value) * 100:.{digits}f}%"


def render_metric(
    label,
    value,
    help_text=None,
):

    st.markdown(
        f"""
        <div>
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if help_text:
        st.caption(help_text)


def band_label(action):

    return {
        "allow": "ALLOW",
        "step_up": "STEP-UP",
        "manual_review": "MANUAL REVIEW",
    }.get(
        str(action).lower(),
        str(action).upper(),
    )


# ============================================================
# LOAD ARTIFACTS
# ============================================================

sample = load_scored_sample()
policy_bands = load_policy_bands()
economics_params = load_economics_params()
threshold_sweep = load_threshold_sweep()
sensitivity = load_sensitivity()
segment_economics = load_segment_economics()


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.markdown(
    """
    <div class="brand-title">◈ ChargebackLens</div>
    <div class="brand-subtitle">
        Dispute Risk Decision Engine
    </div>
    """,
    unsafe_allow_html=True,
)

page = st.sidebar.radio(
    "Navigation",
    [
        "Home",
        "Risk Queue",
        "Economics",
        "Score Transaction",
    ],
)

st.sidebar.divider()

st.sidebar.caption(
    "Calibrated probability → policy → economics"
)

st.sidebar.caption(
    "Decision support prototype"
)


# ============================================================
# HOME
# ============================================================

if page == "Home":

    # --------------------------------------------------------
    # HERO
    # --------------------------------------------------------

    st.markdown(
        """
<div class="hero">
    <div class="hero-title">ChargebackLens</div>
    <div class="hero-subtitle">
        A calibrated chargeback-risk decision engine that turns
        transaction-level dispute probability into an operational
        action and a rupee-denominated economic decision.
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # WHAT IS CHARGEBACKLENS?
    # --------------------------------------------------------

    st.header("What is ChargebackLens?")

    st.write(
        "ChargebackLens is designed to help payment and risk teams "
        "identify transactions that are more likely to result in a "
        "dispute and determine what intervention, if any, is "
        "economically justified."
    )

    st.write(
        "Rather than treating chargeback prediction as only a "
        "classification problem, the system connects three layers: "
        "**risk probability, operational policy, and economics.**"
    )

    st.divider()

    # --------------------------------------------------------
    # OBJECTIVE
    # --------------------------------------------------------

    st.header("Objective")

    st.write(
        "The objective of ChargebackLens is to build a decision layer "
        "around a calibrated dispute-risk model. The system "
        "distinguishes transactions that can be allowed normally "
        "from those where additional intervention or human review "
        "is justified."
    )

    st.write(
        "The final decision is not based solely on whether a "
        "transaction is predicted to be risky. It also considers "
        "the economic consequence of intervening."
    )

    st.divider()

    # --------------------------------------------------------
    # HOW IT WORKS
    # --------------------------------------------------------

    st.header("How it works")

    workflow = [
        (
            "01",
            "Transaction",
            "Transaction-level signals available at the point of decision."
        ),
        (
            "02",
            "Risk",
            "The calibrated model produces a probability representing "
            "the estimated likelihood of a dispute."
        ),
        (
            "03",
            "Decision",
            "The probability is translated into an operational policy: "
            "allow, step-up, or manual review."
        ),
        (
            "04",
            "Economics",
            "The policy is evaluated in rupee terms by comparing "
            "expected dispute losses with intervention costs."
        ),
        (
            "05",
            "Explanation",
            "The resulting decision can be presented to a reviewer "
            "using the relevant risk signals."
        ),
    ]

    for number, title, description in workflow:

        st.markdown(
            f"""
<div class="workflow-step">
    <div class="workflow-title">{number} · {title}</div>
    <div class="workflow-description">{description}</div>
</div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    # --------------------------------------------------------
    # APPLICATION SURFACES
    # --------------------------------------------------------

    st.header("Application surfaces")

    col1, col2, col3 = st.columns(
        3,
        gap="medium",
    )

    with col1:

        st.markdown(
            """
<div class="section-card">
    <div class="section-number">01</div>
    <h3>Risk Queue</h3>
    <p>
        A reviewer-oriented queue of transactions ranked by
        calibrated dispute probability, with policy actions
        and transaction-level details.
    </p>
</div>
            """,
            unsafe_allow_html=True,
        )

    with col2:

        st.markdown(
            """
<div class="section-card">
    <div class="section-number">02</div>
    <h3>Economics</h3>
    <p>
        Explore the financial impact of policy thresholds,
        intervention assumptions, sensitivity, and
        transaction segments.
    </p>
</div>
            """,
            unsafe_allow_html=True,
        )

    with col3:

        st.markdown(
            """
<div class="section-card">
    <div class="section-number">03</div>
    <h3>Transaction Scoring</h3>
    <p>
        Live transaction scoring is planned as the next
        development stage of the application.
    </p>
</div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    # --------------------------------------------------------
    # CURRENT POLICY SNAPSHOT
    # --------------------------------------------------------

    st.header("Current policy snapshot")

    if not policy_bands.empty:

        cols = st.columns(
            min(3, len(policy_bands)),
            gap="large",
        )

        for i, (_, row) in enumerate(
            policy_bands.iterrows()
        ):

            with cols[i]:

                st.markdown(
                    f"""
<div class="policy-card">
    <div class="policy-title">
        {band_label(row["band"])}
    </div>
</div>
                    """,
                    unsafe_allow_html=True,
                )

                st.metric(
                    "Volume",
                    f"{int(row['n']):,}",
                    delta=pct(
                        row["share_of_volume"],
                        2,
                    ),
                )

                st.caption(
                    f"Dispute rate: "
                    f"{pct(row['dispute_rate_in_band'], 2)}"
                )

                st.caption(
                    f"{row['lift_vs_base']:.2f}× base-rate lift"
                )

    else:

        st.info(
            "Policy artifacts are not available."
        )

    st.divider()

    # --------------------------------------------------------
    # FOOTNOTE
    # --------------------------------------------------------

    st.caption(
        "ChargebackLens is a decision-support prototype. "
        "Model outputs should be evaluated against appropriate "
        "operational and business controls before production use."
    )

# ============================================================
# RISK QUEUE
# ============================================================

elif page == "Risk Queue":

    st.title("Risk Queue")

    st.markdown(
        """
        A reviewer-oriented queue ranked by calibrated dispute
        probability.
        """
    )

    if sample.empty:

        st.error(
            "05_scored_test_sample.csv was not found."
        )

        st.stop()

    # --------------------------------------------------------
    # FILTERS
    # --------------------------------------------------------

    with st.expander(
        "Filters",
        expanded=True,
    ):

        f1, f2, f3, f4 = st.columns(4)

        with f1:

            action_options = sorted(
                sample[
                    "recommended_action"
                ]
                .dropna()
                .unique()
            )

            action_filter = st.multiselect(
                "Action",
                action_options,
                default=[],
            )

        with f2:

            category_options = sorted(
                sample[
                    "merchant_category"
                ]
                .dropna()
                .unique()
            )

            category_filter = st.multiselect(
                "Merchant category",
                category_options,
                default=[],
            )

        with f3:

            method_options = sorted(
                sample[
                    "method"
                ]
                .dropna()
                .unique()
            )

            method_filter = st.multiselect(
                "Payment method",
                method_options,
                default=[],
            )

        with f4:

            max_risk = float(
                sample[
                    "proba_calibrated"
                ].max()
            )

            min_probability = st.slider(
                "Minimum risk",
                min_value=0.0,
                max_value=max_risk,
                value=0.0,
                format="%.2f",
            )

    filtered = sample.copy()

    if action_filter:

        filtered = filtered[
            filtered[
                "recommended_action"
            ].isin(action_filter)
        ]

    if category_filter:

        filtered = filtered[
            filtered[
                "merchant_category"
            ].isin(category_filter)
        ]

    if method_filter:

        filtered = filtered[
            filtered[
                "method"
            ].isin(method_filter)
        ]

    filtered = filtered[
        filtered[
            "proba_calibrated"
        ] >= min_probability
    ]

    filtered = filtered.sort_values(
        "proba_calibrated",
        ascending=False,
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    c1, c2, c3, c4 = st.columns(4)

    with c1:

        render_metric(
            "Transactions",
            f"{len(filtered):,}",
        )

    with c2:

        manual_count = (
            filtered[
                "recommended_action"
            ]
            == "manual_review"
        ).sum()

        render_metric(
            "Manual review",
            f"{manual_count:,}",
        )

    with c3:

        stepup_count = (
            filtered[
                "recommended_action"
            ]
            == "step_up"
        ).sum()

        render_metric(
            "Step-up",
            f"{stepup_count:,}",
        )

    with c4:

        average_risk = (
            filtered[
                "proba_calibrated"
            ].mean()
            if len(filtered)
            else 0
        )

        render_metric(
            "Average risk",
            pct(
                average_risk,
                2,
            ),
        )

    st.divider()

    # --------------------------------------------------------
    # QUEUE TABLE
    # --------------------------------------------------------

    queue_columns = [
        "payment_id",
        "created_at",
        "amount",
        "merchant_category",
        "method",
        "proba_calibrated",
        "recommended_action",
    ]

    available_columns = [
        col
        for col in queue_columns
        if col in filtered.columns
    ]

    display = filtered[
        available_columns
    ].copy()

    if "amount" in display.columns:

        display["amount"] = display[
            "amount"
        ].map(
            lambda x: f"₹{x:,.0f}"
        )

    if "proba_calibrated" in display.columns:

        display[
            "proba_calibrated"
        ] = display[
            "proba_calibrated"
        ].map(
            lambda x: f"{x:.2%}"
        )

    display = display.rename(
        columns={
            "payment_id": "Payment ID",
            "created_at": "Created",
            "amount": "Amount",
            "merchant_category": "Category",
            "method": "Method",
            "proba_calibrated": "Risk",
            "recommended_action": "Action",
        }
    )

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=430,
    )

    # --------------------------------------------------------
    # TRANSACTION DETAIL
    # --------------------------------------------------------

    st.divider()

    st.subheader("Transaction detail")

    ids = (
        filtered["payment_id"].tolist()
        if len(filtered)
        else []
    )

    if not ids:

        st.info(
            "No transactions match the selected filters."
        )

    else:

        selected_id = st.selectbox(
            "Select a transaction",
            ids,
        )

        row = sample[
            sample["payment_id"]
            == selected_id
        ].iloc[0]

        d1, d2 = st.columns(2)

        with d1:

            st.markdown(
                f"### {row['payment_id']}"
            )

            detail_columns = [
                "amount",
                "merchant_category",
                "method",
                "retry_count",
                "checkout_latency_ms",
                "is_foreign_bin",
                "is_first_txn_for_device",
                "phone_verified",
                "email_domain_type",
                "txns_last_24h",
                "txns_last_7d",
                "distinct_devices_30d",
                "has_prior_history",
                "prior_disputes_before_this_txn",
                "merchant_dispute_rate_trailing_90d",
            ]

            detail_columns = [
                col
                for col in detail_columns
                if col in row.index
            ]

            details = pd.DataFrame(
                {
                    "Field": detail_columns,
                    "Value": [
                        row[col]
                        for col in detail_columns
                    ],
                }
            )

            st.dataframe(
                details,
                use_container_width=True,
                hide_index=True,
            )

        with d2:

            probability = float(
                row["proba_calibrated"]
            )

            action = row[
                "recommended_action"
            ]

            st.metric(
                "Dispute probability",
                pct(
                    probability,
                    2,
                ),
            )

            if action == "manual_review":

                st.error(
                    "MANUAL REVIEW"
                )

            elif action == "step_up":

                st.warning(
                    "STEP-UP"
                )

            else:

                st.success(
                    "ALLOW"
                )

            if "risk_percentile" in row.index:

                st.metric(
                    "Risk percentile",
                    pct(
                        row["risk_percentile"],
                        1,
                    ),
                )

            if "is_disputed" in row.index:

                outcome = (
                    "Disputed"
                    if row["is_disputed"] == 1
                    else "Not disputed"
                )

                st.caption(
                    f"Evaluation outcome: {outcome}"
                )


# ============================================================
# ECONOMICS
# ============================================================

elif page == "Economics":

    st.title("Economics")

    st.markdown(
        """
        Understand how the risk policy translates into
        rupee-denominated value and how sensitive the decision is
        to operating assumptions.
        """
    )

    if not economics_params:

        st.error(
            "05_economics_params.csv was not found."
        )

        st.stop()

    # --------------------------------------------------------
    # POLICY
    # --------------------------------------------------------

    st.subheader("Current policy")

    p1, p2, p3 = st.columns(3)

    with p1:

        if "threshold_allow_stepup" in economics_params:

            render_metric(
                "Allow → Step-up",
                pct(
                    economics_params[
                        "threshold_allow_stepup"
                    ],
                    2,
                ),
            )

    with p2:

        if "threshold_stepup_review" in economics_params:

            render_metric(
                "Step-up → Review",
                pct(
                    economics_params[
                        "threshold_stepup_review"
                    ],
                    2,
                ),
            )

    with p3:

        if "net_savings_inr_at_policy" in economics_params:

            render_metric(
                "Net savings",
                format_inr(
                    economics_params[
                        "net_savings_inr_at_policy"
                    ]
                ),
            )

    st.divider()

    # --------------------------------------------------------
    # POLICY BANDS
    # --------------------------------------------------------

    if not policy_bands.empty:

        st.subheader("Policy bands")

        band_columns = st.columns(
            min(3, len(policy_bands))
        )

        for i, (_, row) in enumerate(
            policy_bands.iterrows()
        ):

            with band_columns[i]:

                st.markdown(
                    f"### {band_label(row['band'])}"
                )

                render_metric(
                    "Volume",
                    f"{int(row['n']):,}",
                    pct(
                        row[
                            "share_of_volume"
                        ],
                        2,
                    ),
                )

                render_metric(
                    "Dispute rate",
                    pct(
                        row[
                            "dispute_rate_in_band"
                        ],
                        2,
                    ),
                    f"{row['lift_vs_base']:.2f}× base rate",
                )

    # --------------------------------------------------------
    # THRESHOLD SWEEP
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "Threshold → net savings"
    )

    if not threshold_sweep.empty:

        fig = px.line(
            threshold_sweep,
            x="threshold",
            y="net_savings_inr",
            markers=True,
            labels={
                "threshold": "Risk threshold",
                "net_savings_inr":
                    "Net savings (₹)",
            },
        )

        fig.add_hline(
            y=0,
            line_dash="dash",
        )

        fig.update_layout(
            height=420,
            margin=dict(
                l=20,
                r=20,
                t=30,
                b=20,
            ),
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )

        best_row = threshold_sweep.loc[
            threshold_sweep[
                "net_savings_inr"
            ].idxmax()
        ]

        st.info(
            f"Best observed threshold in the sweep: "
            f"{best_row['threshold']:.2%}, "
            f"with estimated net savings of "
            f"{format_inr(best_row['net_savings_inr'])}."
        )

    # --------------------------------------------------------
    # SENSITIVITY
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "Sensitivity to operating assumptions"
    )

    if not sensitivity.empty:

        parameter = st.selectbox(
            "Assumption",
            sensitivity[
                "param_name"
            ].unique(),
        )

        sens = sensitivity[
            sensitivity[
                "param_name"
            ] == parameter
        ].sort_values(
            "param_value"
        )

        fig = px.line(
            sens,
            x="param_value",
            y="net_savings_inr",
            markers=True,
            labels={
                "param_value":
                    "Assumption value",
                "net_savings_inr":
                    "Net savings (₹)",
            },
        )

        fig.update_layout(
            height=380,
            margin=dict(
                l=20,
                r=20,
                t=30,
                b=20,
            ),
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )

        table_columns = [
            "param_value",
            "optimal_threshold",
            "threshold_stepup_review",
            "n_review",
            "n_stepup",
            "net_savings_inr",
        ]

        table_columns = [
            col
            for col in table_columns
            if col in sens.columns
        ]

        st.dataframe(
            sens[
                table_columns
            ],
            use_container_width=True,
            hide_index=True,
        )

    # --------------------------------------------------------
    # SEGMENT ECONOMICS
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "Segment economics"
    )

    if not segment_economics.empty:

        segment_type = st.selectbox(
            "Segment",
            segment_economics[
                "segment_type"
            ].unique(),
        )

        seg = segment_economics[
            segment_economics[
                "segment_type"
            ] == segment_type
        ].copy()

        seg[
            "segment_value"
        ] = seg[
            "segment_value"
        ].astype(str)

        fig = px.bar(
            seg.sort_values(
                "net_savings_at_global_policy",
                ascending=False,
            ),
            x="segment_value",
            y="net_savings_at_global_policy",
            labels={
                "segment_value": "Segment",
                "net_savings_at_global_policy":
                    "Net savings (₹)",
            },
        )

        fig.update_layout(
            height=400,
            margin=dict(
                l=20,
                r=20,
                t=30,
                b=20,
            ),
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )

        segment_columns = [
            "segment_value",
            "n",
            "positives",
            "dispute_rate",
            "mean_amount",
            "optimal_threshold",
            "net_savings_at_global_policy",
            "savings_per_txn",
        ]

        segment_columns = [
            col
            for col in segment_columns
            if col in seg.columns
        ]

        st.dataframe(
            seg[
                segment_columns
            ],
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# SCORE TRANSACTION — UNDER DEVELOPMENT
# ============================================================

elif page == "Score Transaction":

    st.title("Score Transaction")

    st.markdown(
        "Transaction-level live scoring is planned as the next "
        "development stage of ChargebackLens."
    )

    st.write("")

    with st.container(border=True):

        st.write("")

        st.subheader("Under Development")

        st.write(
            "The live transaction scoring interface is currently "
            "being developed. The final version will accept "
            "transaction-level inputs, generate a calibrated "
            "dispute probability, map it to the operational policy, "
            "and display the associated economics."
        )

        st.write("")

    st.write("")

    st.subheader("Planned workflow")

    c1, c2, c3 = st.columns(
        3,
        gap="large",
    )

    with c1:
        st.markdown("**01 · Input**")
        st.write(
            "Enter transaction attributes available at the "
            "point of decision."
        )

    with c2:
        st.markdown("**02 · Score**")
        st.write(
            "Generate a calibrated probability of dispute."
        )

    with c3:
        st.markdown("**03 · Decide**")
        st.write(
            "Translate risk into an action and expected "
            "economic outcome."
        )

    st.divider()

    st.caption(
        "This page intentionally does not perform live scoring yet. "
        "The model and feature pipeline will be connected here once "
        "the production scoring contract is finalized."
    )