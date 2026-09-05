# ChargebackLens — Low-Level Design

**Track:** Razorpay AI Buildathon — Track 02, AI Risk Manager
**Workflow:** Jupyter (NumPy, Pandas, Plotly, scikit-learn) → exported artifacts → Streamlit app
**Data:** Five pre-generated CSV files, loaded read-only. No data generation happens inside this project.

---

## 1. Scope and assumptions

- The CSVs already exist on disk under `data/raw/`. This LLD treats their schema as a fixed contract — every downstream module validates against it but never mutates the source files.
- All modelling and EDA happens in one notebook, organized into clearly separated sections that mirror the module boundaries below. Even though it's one `.ipynb`, each section is written as if it were an importable module — a function with a docstring, typed inputs, typed outputs — so it can be lifted into a `src/` file later without rewriting logic.
- The notebook's final section **exports artifacts** (model file, feature list, thresholds, a scored sample of the test set). The Streamlit app reads only those exported artifacts — it never re-runs training and never touches the raw CSVs directly. This is the seam between the two halves of the project.
- Reproducibility is enforced with a single `RANDOM_SEED = 42` constant set once at the top of the notebook and threaded through every stochastic call (`train_test_split` is not used — see §5.4 — but `HistGradientBoostingClassifier(random_state=...)` and `CalibratedClassifierCV` both take it).

---

## 2. Data layer — CSV schemas

These are the five source files. Every column listed here is what a loader function is allowed to assume exists; anything not listed is treated as unknown and must not be relied upon.

### 2.1 `transactions.csv` (~120,000 rows) — grain: one row per payment attempt

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `payment_id` | string (PK) | No | Unique per row |
| `merchant_id` | string (FK → merchants) | No | |
| `customer_id` | string (FK → customers) | No | |
| `amount` | float64 | No | INR, > 0 |
| `method` | category | No | `upi`, `card`, `netbanking`, `wallet`, `emi` |
| `issuer_bank` | string | Yes | Null for UPI/wallet |
| `card_bin_country` | string | Yes | Null for non-card methods |
| `created_at` | datetime64 | No | Transaction timestamp |
| `ip_state` | string | No | Indian state code |
| `device_id` | string | No | |
| `is_first_txn_for_device` | bool | No | |
| `checkout_latency_ms` | int64 | No | Time from checkout start to auth |
| `retry_count` | int64 | No | Failed auth attempts before success, ≥ 0 |
| `auth_status` | category | No | `success` (only successful txns are in scope for dispute risk) |

### 2.2 `customers.csv` (~35,000 rows) — grain: one row per customer

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `customer_id` | string (PK) | No | |
| `account_age_days` | int64 | No | As of dataset snapshot date |
| `lifetime_orders` | int64 | No | |
| `prior_disputes` | int64 | No | Total disputes ever, snapshot value — **must be time-gated before use, see §5.3.2** |
| `avg_order_value` | float64 | No | |
| `email_domain_type` | category | No | `personal`, `disposable`, `corporate` |
| `phone_verified` | bool | No | |

### 2.3 `merchants.csv` (~60 rows) — grain: one row per merchant

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `merchant_id` | string (PK) | No | |
| `category` | category | No | `travel`, `gaming`, `edtech`, `d2c`, `ticketing`, `subscription` |
| `avg_ticket_size` | float64 | No | |
| `refund_window_days` | int64 | No | |
| `delivery_sla_days` | int64 | Yes | Null for non-physical merchants (gaming, edtech, subscription) |

### 2.4 `fulfilment.csv` (~variable rows, one per physical-goods transaction) — grain: one row per payment_id that required shipping

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `payment_id` | string (FK → transactions) | No | Not all payment_ids appear here — digital goods have no row |
| `shipped_at` | datetime64 | Yes | Null if not yet shipped at snapshot time |
| `delivered_at` | datetime64 | Yes | Null if not yet delivered |
| `delivery_status` | category | No | `delivered`, `in_transit`, `returned`, `lost` |
| `tracking_available` | bool | No | |
| `address_completeness_score` | float64 | No | 0–1 |

⚠️ **Leakage flag on this table:** `delivered_at` and `delivery_status` are frequently known only *after* the dispute window would already be closing. Any feature built from this table must pass the knowability check in §5.3.1.

### 2.5 `disputes.csv` (~900–1,200 rows, the positive class) — grain: one row per dispute raised

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `dispute_id` | string (PK) | No | |
| `payment_id` | string (FK → transactions) | No | A payment_id appears here **at most once** — treat as the binary label source |
| `reason_code` | category | No | `fraud`, `not_received`, `not_as_described`, `duplicate`, `subscription_cancelled` |
| `raised_at` | datetime64 | No | 30–90 days after `created_at`, per the generator's design |
| `disputed_amount` | float64 | No | Usually equals `transactions.amount`, occasionally partial |

**Label definition:** `label = 1` if `payment_id` appears in `disputes.csv`, else `0`. This is computed once, early, in the loader module (§5.1) and carried as a single `int8` column called `is_disputed` — never recomputed downstream.

---

## 3. Directory and file structure

```
chargebacklens/
├── data/
│   ├── raw/
│   │   ├── transactions.csv
│   │   ├── customers.csv
│   │   ├── merchants.csv
│   │   ├── fulfilment.csv
│   │   └── disputes.csv
│   └── processed/                    # written by the notebook, read by the app
│       ├── model.joblib
│       ├── calibrated_model.joblib
│       ├── feature_columns.json
│       ├── economics_params.json
│       ├── threshold_sweep.csv
│       ├── scored_test_set.csv
│       └── feature_importances.csv
├── notebooks/
│   └── 01_chargebacklens.ipynb
├── app/
│   ├── streamlit_app.py
│   ├── scoring.py                    # shared logic imported by the app
│   └── explain.py                    # LLM reviewer-note generator + fallback
├── SCOPE.md
├── METRICS.md
├── FAILURES.md
├── requirements.txt
└── README.md
```

The notebook is the **only** place training happens. `app/scoring.py` contains pure functions with no training logic — it loads `data/processed/*` and applies them. This separation is deliberate: it means the Streamlit app boots in under a second and never depends on scikit-learn's training code path, only its inference path.

---

## 4. Notebook design

The notebook is organized into nine numbered sections, each a markdown header followed by one or more code cells. Each section below is specified as if it were a module: purpose, inputs, outputs, and the functions inside it.

### 4.1 Section 1 — Load and validate

**Purpose:** read the five CSVs, enforce dtypes, build the label, fail loudly on schema drift.

```python
def load_raw_tables(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """
    Reads all five CSVs with an explicit dtype map (no dtype inference —
    inference is where silent schema drift hides). Parses all *_at / created_at
    columns as datetime64[ns] via parse_dates=[...].
    Returns {"transactions": df, "customers": df, "merchants": df,
             "fulfilment": df, "disputes": df}
    """

def validate_schema(tables: dict[str, pd.DataFrame]) -> None:
    """
    For each table, asserts the column set matches §2 exactly (extra columns
    are logged as a warning, not an error — allows future dataset extension;
    missing columns raise AssertionError with the missing column names).
    Also asserts referential integrity: every merchant_id / customer_id /
    payment_id in transactions exists in the parent table.
    """

def build_label(transactions: pd.DataFrame, disputes: pd.DataFrame) -> pd.DataFrame:
    """
    Left-joins transactions to disputes on payment_id, adds:
      - is_disputed: int8, 1 if payment_id in disputes else 0
      - dispute_raised_at: datetime64, NaT if not disputed
      - dispute_reason_code: category, NaN if not disputed
    Returns transactions with these 3 columns appended. Asserts no
    payment_id appears twice after the join (guards against a many-to-one
    disputes table, which would silently duplicate rows).
    """
```

Output of this section: one wide DataFrame `txns` (transactions + label columns), plus `customers`, `merchants`, `fulfilment` held separately (joined later, in §4.3, at feature-build time — not here, to keep the label-building step free of any feature logic).

### 4.2 Section 2 — EDA (Plotly)

**Purpose:** understand class imbalance, temporal distribution, and per-segment risk before any modelling decision is made. Every chart here should directly inform a modelling choice made later — this section is not decorative.

Planned charts, each as a small function returning a `plotly.graph_objects.Figure`:

```python
def plot_dispute_rate_over_time(txns: pd.DataFrame) -> go.Figure:
    """Weekly is_disputed rate, line chart. Confirms the ~0.8-1.0% base
    rate and whether it drifts across the 10-month window — this directly
    justifies the temporal split in §4.4 over a random split."""

def plot_dispute_rate_by_segment(txns: pd.DataFrame, merchants: pd.DataFrame,
                                   segment_col: str) -> go.Figure:
    """Bar chart of dispute rate by merchant category / method / bin_country.
    Called once per segment_col of interest. Confirms which raw fields carry
    signal before they're engineered into features."""

def plot_amount_distribution(txns: pd.DataFrame) -> go.Figure:
    """Overlaid histogram, disputed vs non-disputed, on log1p(amount).
    Decides whether amount needs a log transform in §4.3 (it will)."""

def plot_class_imbalance_summary(txns: pd.DataFrame) -> go.Figure:
    """Single annotated bar showing positive vs negative counts and the
    resulting ratio — pinned near the top of the notebook as the number
    that justifies class_weight='balanced' and PR-AUC-over-ROC-AUC later."""
```

Output: no data artifacts — this section produces only inline figures and the written observations that steer §4.3–4.6.

### 4.3 Section 3 — Feature engineering

**Purpose:** build a single model-ready DataFrame, with every feature tagged by *when it becomes knowable relative to `created_at`*. This is the leakage-discipline section and the one to be most careful and most explicit about.

```python
FEATURE_KNOWABILITY = {
    # feature_name: "instant" | "trailing" | "FORBIDDEN"
    "log_amount": "instant",
    "amount_vs_merchant_avg_ratio": "instant",
    "hour_of_day": "instant",
    "day_of_week": "instant",
    "is_night_txn": "instant",
    "retry_count": "instant",
    "checkout_latency_ms": "instant",
    "method": "instant",
    "is_foreign_bin": "instant",
    "ip_billing_state_mismatch": "instant",
    "txns_last_24h": "trailing",
    "txns_last_7d": "trailing",
    "distinct_devices_30d": "trailing",
    "prior_disputes_before_this_txn": "trailing",
    "account_age_days": "instant",          # static snapshot, safe
    "amount_vs_own_avg": "trailing",
    "merchant_dispute_rate_trailing_90d": "trailing",
    "delivery_status": "FORBIDDEN",         # known only after fulfilment — excluded
    "delivered_at": "FORBIDDEN",
}
```

This dict is printed as a table into `METRICS.md` directly — it is the artifact that proves leakage discipline to a reader, not just a code comment.

```python
def build_instant_features(txns: pd.DataFrame, merchants: pd.DataFrame) -> pd.DataFrame:
    """
    All features computable from the transaction row itself plus static
    merchant/customer attributes. No time-ordering required. Returns a
    DataFrame indexed by payment_id.
    """

def build_trailing_features(txns: pd.DataFrame, customers: pd.DataFrame,
                              window_days: list[int] = [1, 7, 30]) -> pd.DataFrame:
    """
    THE CORE LEAKAGE-SAFE FUNCTION. For each transaction, computes rolling
    counts/aggregates using ONLY rows from the same customer/merchant with
    created_at strictly earlier than the current row's created_at.

    Implementation: sort by (customer_id, created_at), then for each window
    use a groupby + pd.Series.rolling on a time-indexed window ('7D', '30D')
    with closed='left' (excludes the current row and anything at the same
    timestamp) rather than a manual loop, for both correctness and speed
    at 120K rows.

    Returns a DataFrame indexed by payment_id with columns:
    txns_last_24h, txns_last_7d, distinct_devices_30d,
    prior_disputes_before_this_txn, amount_vs_own_avg,
    merchant_dispute_rate_trailing_90d.
    """

def assemble_feature_matrix(txns: pd.DataFrame, instant: pd.DataFrame,
                              trailing: pd.DataFrame) -> pd.DataFrame:
    """
    Joins instant + trailing features + is_disputed + created_at (kept only
    for the split, dropped before fitting) into one matrix X_full.
    Asserts: no column in X_full is in the FORBIDDEN list above.
    Asserts: no NaNs remain except in columns explicitly allowed to have
    them (e.g. a customer's first-ever transaction has txns_last_7d = 0,
    not NaN — verified here).
    """
```

Output: `X_full` (feature matrix, one row per payment_id, `created_at` retained for the split) and `y_full` (the `is_disputed` Series, same index).

### 4.4 Section 4 — Temporal split

**Purpose:** avoid the single most common mistake in this problem class — a random split leaks future merchant-risk drift into training.

```python
def temporal_split(X_full: pd.DataFrame, y_full: pd.Series,
                    split_date: str = "2026-08-01"
                    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """
    Rows with created_at < split_date -> train.
    Rows with created_at >= split_date -> test.
    Drops created_at from both X_train and X_test after splitting (it is
    a split key, never a model feature).
    Logs and returns the row counts and positive rates of both splits —
    a large rate gap between train and test is itself worth reporting,
    not hiding.
    """
```

Output: `X_train, X_test, y_train, y_test`.

### 4.5 Section 5 — Modelling

**Purpose:** baseline, then main model, then calibration — in that fixed order, each one evaluated before moving to the next, so the notebook tells an honest story of incremental justification rather than presenting one model as a given.

```python
def build_preprocessing_pipeline(categorical_cols: list[str],
                                   numeric_cols: list[str]) -> ColumnTransformer:
    """
    ColumnTransformer:
      - numeric_cols -> SimpleImputer(strategy='median') -> passthrough
        (HistGradientBoostingClassifier handles NaN natively, so no scaling
        is applied for the main model; the baseline pipeline below wraps
        this same transformer with an added StandardScaler step for the
        numeric branch, since LogisticRegression needs it)
      - categorical_cols -> OrdinalEncoder(handle_unknown='use_encoded_value',
        unknown_value=-1) for the HGB pipeline
        OR OneHotEncoder(handle_unknown='ignore') for the baseline pipeline
    """

def fit_baseline(X_train, y_train, categorical_cols, numeric_cols) -> Pipeline:
    """
    Pipeline([('prep', ColumnTransformer[...OneHot + Scale...]),
              ('clf', LogisticRegression(class_weight='balanced',
                                          max_iter=1000,
                                          random_state=RANDOM_SEED))])
    """

def fit_main_model(X_train, y_train, categorical_cols, numeric_cols) -> Pipeline:
    """
    Pipeline([('prep', ColumnTransformer[...Ordinal, median-impute...]),
              ('clf', HistGradientBoostingClassifier(
                          class_weight='balanced',
                          max_iter=300,
                          learning_rate=0.05,
                          max_depth=6,
                          categorical_features=categorical_col_indices,
                          random_state=RANDOM_SEED))])
    """

def calibrate_model(fitted_pipeline: Pipeline, X_train, y_train) -> CalibratedClassifierCV:
    """
    CalibratedClassifierCV(estimator=fitted_pipeline, method='isotonic', cv=3)
    fit on X_train/y_train (isotonic chosen over Platt/sigmoid because the
    dataset is large enough — >500 positives — for isotonic's non-parametric
    fit to be stable, and it makes no assumption about the score distribution's
    shape, which HGB's raw scores don't reliably have).
    """
```

Output: `baseline_pipeline`, `main_pipeline`, `calibrated_model` — all three retained (not just the final one), because §4.6 reports all three side by side.

### 4.6 Section 6 — Evaluation

**Purpose:** produce every number that goes into `METRICS.md`, and produce them for all three models so the calibration step's value is visible, not asserted.

```python
def evaluate_model(model, X_test, y_test, name: str) -> dict:
    """
    Computes and returns a dict:
      pr_auc (average_precision_score),
      precision_at_1pct, precision_at_5pct (rank the test set by predicted
        probability, take top 1%/5% by volume, report precision within it),
      confusion_matrix (absolute counts, at a threshold chosen in §4.7 —
        called AFTER §4.7 for the final report, or at threshold=0.5 for an
        interim baseline-only sanity check),
      brier_score (calibration quality, only meaningful for calibrated_model)
    Explicitly does NOT compute roc_auc as a headline metric; if computed
    at all, it's logged to a side cell with a one-line comment explaining
    why it's excluded from METRICS.md (base rate ~1% inflates it).
    """

def plot_calibration_curve(model, X_test, y_test, name: str) -> go.Figure:
    """
    Plotly line: predicted probability (binned) vs observed frequency,
    plus the y=x reference line. Run once for main_pipeline (uncalibrated)
    and once for calibrated_model, on the same axes, to show the effect
    of §4.5's calibration step directly.
    """

def plot_precision_recall_curve(models: dict[str, Pipeline], X_test, y_test) -> go.Figure:
    """All three models overlaid on one PR curve."""

def feature_importance_table(main_pipeline, feature_names: list[str]) -> pd.DataFrame:
    """
    Pulls .feature_importances_ from the fitted HistGradientBoostingClassifier
    step, pairs with feature_names in the correct post-ColumnTransformer
    order, sorts descending. Exported as feature_importances.csv (used by
    the Streamlit app's reviewer-note generator in place of SHAP if SHAP
    is dropped under time pressure).
    """
```

### 4.7 Section 7 — Economics layer

**Purpose:** convert the calibrated probability into a rupee-optimal decision. This is the section that separates the project from a plain classifier.

```python
ECONOMICS_PARAMS = {
    "dispute_fee": 1500.0,       # INR, fixed cost per raised dispute regardless of outcome
    "ops_review_cost": 300.0,    # INR, cost of a human reviewing a flagged txn
    "merchant_margin": 0.18,     # fraction of amount that is margin, not COGS
    "step_up_abandon_rate": 0.25 # P(customer abandons | forced into 3DS step-up)
}

def expected_cost_matrix(amount: float, params: dict) -> dict:
    """
    Returns per-transaction cost under each of the 4 confusion-matrix outcomes:
      fn_cost = amount + params['dispute_fee'] + params['ops_review_cost']
      fp_cost = amount * params['merchant_margin'] * params['step_up_abandon_rate']
      tp_cost = params['ops_review_cost']
      tn_cost = 0.0
    """

def threshold_sweep(y_test: pd.Series, y_proba: np.ndarray, amounts: pd.Series,
                     params: dict, n_steps: int = 100) -> pd.DataFrame:
    """
    For threshold in np.linspace(0.01, 0.99, n_steps):
      predictions = (y_proba >= threshold)
      for each row, look up its actual outcome (TP/FP/TN/FN given
      predictions vs y_test) and its expected_cost_matrix cost
      net_savings = sum(cost of doing nothing i.e. all-FN baseline)
                    - sum(actual cost at this threshold)
    Returns a DataFrame: threshold, precision, recall, net_savings_inr,
    n_flagged. This is exported wholesale as threshold_sweep.csv — the
    Streamlit economics tab reads this file directly rather than
    recomputing the sweep at runtime.
    """

def sensitivity_analysis(y_test, y_proba, amounts, base_params: dict,
                           param_name: str, param_range: list[float]) -> pd.DataFrame:
    """
    Re-runs threshold_sweep for each value in param_range (varying only
    param_name, e.g. step_up_abandon_rate from 0.10 to 0.40), records the
    optimal threshold and its net_savings for each. Returns a DataFrame
    used to answer: does the optimal operating point survive a wrong
    assumption about abandon rate?
    """

def segment_economics(y_test, y_proba, amounts, merchant_categories: pd.Series,
                       params: dict) -> pd.DataFrame:
    """
    Runs threshold_sweep separately per amount bucket (<2000, 2000-10000,
    >10000) and per merchant category. Returns the best net_savings per
    segment — used to identify segments (expected: low-ticket transactions)
    where the model should NOT be deployed because review friction costs
    more than the dispute exposure it prevents.
    """
```

Output artifacts: `economics_params.json` (the params dict), `threshold_sweep.csv`, plus the segment table saved into `METRICS.md` as a markdown table (not a separate CSV — it's small and narrative).

### 4.8 Section 8 — Explanation generation (design only, code lives in `app/explain.py`)

The notebook does not call the LLM. It only prepares the SHAP-or-importances input the app will need — see §4.6's `feature_importance_table`. The generation function itself is specified in §5.5, since it runs inside the Streamlit app at request time, not in the notebook.

### 4.9 Section 9 — Export

```python
def export_artifacts(calibrated_model, feature_columns: list[str],
                      economics_params: dict, threshold_sweep_df: pd.DataFrame,
                      X_test: pd.DataFrame, y_test: pd.Series, y_proba: np.ndarray,
                      out_dir: Path) -> None:
    """
    Writes, in order:
      out_dir/calibrated_model.joblib   — via joblib.dump
      out_dir/feature_columns.json      — ordered list, so the app can
                                           validate/reorder a scoring-form
                                           input dict before calling .predict
      out_dir/economics_params.json
      out_dir/threshold_sweep.csv
      out_dir/scored_test_set.csv       — X_test + y_test + y_proba + amount
                                           + merchant category, capped/sampled
                                           to ~5,000 rows for the review-queue
                                           tab (full 24K-row test set is not
                                           needed for a demo queue and bloats
                                           app load time)
      out_dir/feature_importances.csv
    Every write is followed by an immediate re-read + shape/columns assert,
    so a corrupted export fails in the notebook, not silently in the app.
    """
```

---

## 5. Streamlit app design

### 5.1 App shell

```python
# app/streamlit_app.py
st.set_page_config(page_title="ChargebackLens", layout="wide")

@st.cache_resource
def load_model() -> CalibratedClassifierCV:
    """Loads calibrated_model.joblib once per server process, not per rerun."""

@st.cache_data
def load_static_artifacts() -> dict:
    """Loads feature_columns.json, economics_params.json, threshold_sweep.csv,
    scored_test_set.csv, feature_importances.csv into a single dict, cached
    by Streamlit's data cache (safe here since these are read-only DataFrames
    treated as immutable for the session)."""
```

Three tabs via `st.tabs(["Score a Transaction", "Review Queue", "Economics Explorer"])`. No sidebar navigation — three tabs is simple enough that a sidebar would be redundant chrome.

### 5.2 Tab 1 — Score a transaction

**Inputs (widgets):** `st.number_input` for amount, `st.selectbox` for method/merchant category/card_bin_country, `st.number_input` for retry_count and checkout_latency_ms, `st.checkbox` for is_first_txn_for_device, `st.slider` for account_age_days. Trailing features (`txns_last_7d` etc.) are exposed as sliders too, with a caption clarifying they're normally computed automatically from history — this is a manual-override demo mode, stated explicitly so a judge doesn't mistake it for the production path.

```python
def build_feature_row(form_inputs: dict, feature_columns: list[str]) -> pd.DataFrame:
    """
    Maps the Streamlit form dict onto a single-row DataFrame with columns
    in EXACTLY the order of feature_columns.json (the pipeline's
    ColumnTransformer is order-sensitive). Missing engineered fields not
    exposed as widgets (e.g. amount_vs_merchant_avg_ratio) are derived
    here from the raw inputs using the same formulas as §4.3 — kept in
    app/scoring.py as a shared function imported by both, so the notebook
    and the app can never silently diverge on feature logic.
    """

def score_transaction(model, feature_row: pd.DataFrame) -> float:
    """model.predict_proba(feature_row)[0, 1]"""

def recommend_action(probability: float, threshold_sweep_df: pd.DataFrame) -> str:
    """
    Looks up the economics-optimal threshold (pre-computed, the row of
    threshold_sweep_df with max net_savings_inr) and returns one of:
    "Allow", "Step-up (3DS)", "Manual review" — using two threshold bands,
    not one, since a hard allow/block split ignores the real workflow
    (very high-confidence flags go to manual review, not just step-up).
    """
```

On submit: display the probability as `st.metric`, a horizontal bar chart (Plotly) of the top-5 feature importances **for this specific row** (importance × the row's own standardized feature value, as a cheap SHAP-free approximation if SHAP was cut per the fallback plan), the recommended action, and the LLM reviewer note (§5.5) in an `st.info` box.

### 5.3 Tab 2 — Review queue

Reads `scored_test_set.csv` (already scored, from §4.9 — no live inference here). Sorted descending by `y_proba`.

```python
def render_review_queue(scored_df: pd.DataFrame, top_k_pct: float) -> pd.DataFrame:
    """
    Slices scored_df to the top top_k_pct% by y_proba (top_k_pct set via
    an st.slider, default 5%). Computes and displays precision-within-slice
    live, as the slider moves — this is the same precision@k metric from
    METRICS.md, made interactive so a judge can feel the volume/precision
    trade-off rather than read it as a static number.
    """
```

Table rendered with `st.dataframe`, row-click (via `st.dataframe`'s selection API) opens the same reviewer-note card used in Tab 1, reusing `recommend_action` and the note generator — one code path, not a duplicate.

### 5.4 Tab 3 — Economics explorer

```python
def recompute_sweep_live(scored_df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    Re-runs §4.7's threshold_sweep logic (imported from a shared module,
    not re-implemented) directly on scored_test_set.csv's y_proba/amount
    columns whenever a slider changes. This is fast (~24K rows in scope,
    100 thresholds) and gives a genuinely live curve rather than a static
    pre-computed one — the whole point of this tab is letting a judge
    change dispute_fee / merchant_margin / step_up_abandon_rate and watch
    the optimal threshold move.
    """
```

Sliders: `dispute_fee` (₹500–3000), `merchant_margin` (0.05–0.35), `step_up_abandon_rate` (0.05–0.50). Plotly line chart of net_savings_inr vs threshold, vertical marker at the current optimum, `st.metric` showing the optimum's rupee figure and the threshold value. A static `st.dataframe` below shows the pre-computed `segment_economics` table from §4.7, with a caption explicitly naming the segment(s) where the model is not worth deploying.

### 5.5 `app/explain.py` — reviewer note generator

```python
def generate_reviewer_note(feature_row: pd.DataFrame, probability: float,
                            top_features: list[tuple[str, float]],
                            merchant_policy_text: str,
                            api_key: str | None) -> str:
    """
    If api_key is provided: calls the Anthropic API with a short, fixed
    system prompt instructing a 2-3 sentence factual reviewer note citing
    only the top_features and merchant_policy_text supplied — no free
    invention of transaction details not present in the input.

    If api_key is None or the API call raises: falls back to
    template_note(feature_row, probability, top_features), a deterministic
    f-string template covering the same fields, so the app runs fully
    offline for a judge with no key. This fallback path is exercised by
    default in the deployed demo unless ANTHROPIC_API_KEY is set.
    """

def template_note(feature_row, probability, top_features) -> str:
    """Deterministic fallback, e.g.:
    'Flagged at {probability:.2f}. Top signals: {feature_1_readable},
    {feature_2_readable}. Recommended: {action}.'"""
```

---

## 6. Data contract summary (the seam between notebook and app)

| Artifact | Producer | Consumer | Format |
|---|---|---|---|
| `calibrated_model.joblib` | §4.9 | §5.1 `load_model` | joblib-pickled sklearn object |
| `feature_columns.json` | §4.9 | §5.2 `build_feature_row` | ordered list[str] |
| `economics_params.json` | §4.9 | §5.4 defaults | flat dict, JSON |
| `threshold_sweep.csv` | §4.9 | §5.2, §5.4 | columns: threshold, precision, recall, net_savings_inr, n_flagged |
| `scored_test_set.csv` | §4.9 | §5.3, §5.4 | X_test columns + y_test + y_proba + amount + merchant_category |
| `feature_importances.csv` | §4.6 | §5.2, §5.5 | columns: feature, importance |

Any change to `feature_columns.json`'s order or contents requires re-running §4.9's export — the app has no independent knowledge of feature order and will misalign a raw dict onto the pipeline if the two drift. Worth a one-line `assert` at app startup comparing `feature_columns.json` against `model.feature_names_in_` if that attribute is available on the fitted pipeline, to catch drift immediately rather than as a silent misprediction.

---

## 7. Non-functional notes

- **Reproducibility:** single `RANDOM_SEED` constant, threaded through every `random_state=` argument; `np.random.seed(RANDOM_SEED)` set once at notebook top for any remaining unseeded NumPy calls.
- **Performance:** `build_trailing_features` is the one place with real cost (rolling window ops over 120K rows). Budget for it to run in seconds, not minutes — if it's slow, the fix is sorting once and using vectorized `groupby.rolling`, not writing a Python loop.
- **App startup:** `@st.cache_resource` for the model (loaded once per process) vs `@st.cache_data` for the CSV-based artifacts (Streamlit's data cache, which correctly treats DataFrames as hashable-by-content) — mixing these up is the most common Streamlit caching bug and worth getting right the first time.
