# ChargebackLens — Project Development Plan

**Companion documents:** `chargebacklens_hld.md` (architecture), `chargebacklens_lld.md` (module/function design), `chargebacklens_data_spec.md` (CSV schema, FK, and data-quality contract)
**Purpose of this document:** the literal build order. Five notebooks, run in sequence, each reading CSVs the previous one wrote and writing new CSVs for the next. Once the notebooks produce a clean, validated artifact chain, the reusable logic is lifted into `.py` modules and wired into the Streamlit app. Every intermediate and final data artifact is a CSV — the only binary files in the whole project are the three fitted model objects, because a gradient-boosted ensemble genuinely cannot be represented as a CSV without losing the object itself. Everything else — cleaned tables, the feature matrix, predictions, thresholds, economics parameters, even the feature-knowability tags — is CSV, specifically so every artifact can be opened, diffed, and sanity-checked by eye at any point without deserializing anything.

---

## 1. Before writing any notebook code

### 1.1 Folder structure (create this first, exactly)

```
chargebacklens/
├── data/
│   ├── raw/                              # the 5 pre-generated CSVs — never written to
│   │   ├── transactions.csv
│   │   ├── customers.csv
│   │   ├── merchants.csv
│   │   ├── fulfilment.csv
│   │   └── disputes.csv
│   └── processed/                        # every notebook writes here, nothing else does
│       ├── 01_cleaned_transactions.csv
│       ├── 01_cleaned_customers.csv
│       ├── 01_cleaned_merchants.csv
│       ├── 01_cleaned_fulfilment.csv
│       ├── 01_cleaned_disputes.csv
│       ├── 01_master_labelled.csv
│       ├── 01_data_quality_log.csv
│       ├── 02_eda_segment_summary.csv
│       ├── 03_feature_matrix.csv
│       ├── 03_feature_knowability.csv
│       ├── 03_train.csv
│       ├── 03_test.csv
│       ├── 04_train_predictions.csv
│       ├── 04_test_predictions.csv
│       ├── 04_feature_importances.csv
│       ├── 05_model_comparison.csv
│       ├── 05_calibration_curve.csv
│       ├── 05_threshold_sweep.csv
│       ├── 05_sensitivity_analysis.csv
│       ├── 05_segment_economics.csv
│       ├── 05_economics_params.csv
│       ├── 05_scored_test_sample.csv
│       └── models/
│           ├── baseline_model.joblib
│           ├── main_model.joblib
│           └── calibrated_model.joblib
├── notebooks/
│   ├── 01_data_cleaning_merging.ipynb
│   ├── 02_eda.ipynb
│   ├── 03_feature_engineering.ipynb
│   ├── 04_model_building.ipynb
│   └── 05_model_evaluation.ipynb
├── app/
│   ├── streamlit_app.py
│   ├── scoring.py
│   ├── economics.py
│   └── explain.py
├── SCOPE.md
├── METRICS.md
├── FAILURES.md
├── requirements.txt
└── README.md
```

The `01_`, `02_`, `03_`… prefixes on every processed file are deliberate: sorted alphabetically, `data/processed/` reads as the exact build order, and it's immediately obvious which notebook is the producer of any given file.

### 1.2 `requirements.txt`

```
pandas
numpy
plotly
scikit-learn
joblib
streamlit
anthropic
jupyter
```

Pin versions once your environment is working (`pip freeze | grep -E "pandas|numpy|scikit-learn|plotly|streamlit"` → paste into `requirements.txt`) so the Streamlit Cloud deployment in §10 doesn't silently resolve a different `scikit-learn` version than the one that pickled your model — a version mismatch on `HistGradientBoostingClassifier` is a real, common deployment failure, not a hypothetical one.

### 1.3 Constants every notebook imports at the top

```python
RANDOM_SEED = 42
RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
SPLIT_DATE = "2026-08-01"        # train < this date, test >= this date
np.random.seed(RANDOM_SEED)
```

Copy this cell verbatim into all five notebooks. Do not let any notebook define its own seed or path — a mismatched constant between notebooks is the single easiest way to silently corrupt the artifact chain (e.g. notebook 4 accidentally reading a `03_train.csv` built with a different split date than notebook 5 expects).

### 1.4 The one rule that governs every notebook below

**Every notebook ends with an export cell, and every export cell immediately re-reads what it just wrote and asserts its shape and columns match expectation before the notebook is considered "done."** This is not optional polish — it's what turns a silent corrupted handoff into a loud failure at build time instead of a confusing bug three notebooks later.

```python
df.to_csv(PROCESSED_DIR / "0X_something.csv", index=False)
check = pd.read_csv(PROCESSED_DIR / "0X_something.csv")
assert check.shape[0] == df.shape[0], f"row count mismatch: wrote {df.shape[0]}, read {check.shape[0]}"
assert set(check.columns) == set(df.columns), "column mismatch after CSV round-trip"
print(f"✅ 0X_something.csv — {check.shape[0]} rows, {check.shape[1]} cols")
```

---

## 2. Notebook 1 — `01_data_cleaning_merging.ipynb`

**Reads:** the 5 raw CSVs. **Writes:** 5 cleaned individual tables, 1 merged master table, 1 data-quality log. **Never:** engineers a rolling/trailing feature — that belongs to notebook 3. This notebook's job is strictly "make the raw data trustworthy and give me one labelled table," nothing more.

### 2.1 Cell-by-cell plan

**Cell 1 — imports and constants** (§1.3 block).

**Cell 2 — load raw tables with explicit dtypes**
```python
def load_raw_tables(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """Explicit dtype map per chargebacklens_data_spec.md §3 — no dtype
    inference. parse_dates=[...] for every *_at / created_at column."""
```
Print `.shape` for all 5 immediately after loading — the first sanity check is that you got 120,000 / 35,000 / 60 / 66,140 / 1,091 rows respectively (data spec §1). If any count is off, stop here; don't proceed into cleaning against the wrong input.

**Cell 3 — schema validation**
Assert the column set of each table matches `chargebacklens_data_spec.md` §3 exactly. Missing columns → `AssertionError` with the missing names. Extra columns → logged warning, not an error.

**Cell 4 — foreign key integrity**
Per data spec §2:
- `transactions.merchant_id → merchants.merchant_id` and `transactions.customer_id → customers.customer_id`: assert **zero** violations. Raise if any exist — these are first-party fields and a violation here means something is actually broken, not a designed inconsistency.
- `fulfilment.payment_id → transactions.payment_id`: log orphan count, drop those rows, **assert the logged count equals 140** (data spec §3.4.3).
- `disputes.payment_id → transactions.payment_id`: log orphan count, drop those rows, **assert the logged count equals 35** (data spec §3.5.3).

**Cell 5 — duplicate-key resolution**
Handle each of the three duplicate-key conditions from the data spec, and **document the rule you chose** for each — this is exactly the kind of decision a reader will want to see stated, not silently made:
- `transactions`: 12 `payment_id`s appear twice (data spec §3.1.1). Rule: keep the row with the earlier `created_at`, drop the later duplicate, log the 12 dropped rows to the quality log.
- `customers`: 10 `customer_id`s appear twice (data spec §3.2.4). Rule: keep the row with the higher `lifetime_orders` (the more "complete" record), drop the other, log 10 dropped rows.
- `disputes`: 6 `payment_id`s appear twice among the valid 1,050 (data spec §3.5.2). Rule: keep the row with the earlier `raised_at`, drop the later duplicate — this is also re-verified inside `build_label` in Cell 7 as a second, independent check.

**Cell 6 — value-level cleaning**
One sub-cell per issue, each ending with a `print(f"cleaned N rows: <issue name>")` line that becomes a row in the quality log:
- `ip_state`: uppercase, then map full state names → codes (data spec §3.1.2, 360 rows).
- `device_id`: replace `""` with `pd.NA` (§3.1.3, 60 rows) — critical: do **not** drop these rows, just null the field, since `build_trailing_features` in notebook 3 needs to treat this customer's device history as "one fewer known device," not delete the transaction.
- `amount`: log and exclude the 8 non-positive rows from modelling entirely (§3.1.4) — flag them in the quality log with their `payment_id`s, don't silently drop without a trace.
- `created_at`: log and exclude the 3 out-of-window rows (§3.1.5).
- `checkout_latency_ms`: clip negative values to `0` and log the 12 affected rows (§3.1.6) — clip rather than drop, since the row's other fields are still usable.
- `retry_count`: cap at a sane ceiling (e.g. 10) and log the 5 outlier rows (§3.1.7) rather than dropping — the fact that they happened is itself informative and should stay visible in EDA.
- `customers.account_age_days`: clip negative values to `0`, log 6 rows (§3.2.3).
- `customers.email_domain_type`: replace `""` with `"unknown"` as an explicit fourth category, log 15 rows (§3.2.2) — don't silently fold into one of the three real categories.
- `disputes.reason_code`: replace null with `"unclassified"`, log 5 rows (§3.5.4).
- `disputes.raised_at < created_at`: null out `raised_at` for the 12 affected rows and log them (§3.5.5) — the dispute is still real (it still counts for the label), only the timing field is untrustworthy.
- `fulfilment.delivered_at < shipped_at`: null out both timestamps for the 790 affected rows and log them (§3.4.1) — same logic, the delivery event happened, the timestamps didn't.
- `fulfilment.address_completeness_score`: clip to `[0, 1]`, log 25 rows (§3.4.4).

**Cell 7 — build the label**
```python
def build_label(transactions: pd.DataFrame, disputes: pd.DataFrame) -> pd.DataFrame:
    """Left-join on payment_id. Adds is_disputed (int8), dispute_raised_at,
    dispute_reason_code. Asserts no payment_id appears twice post-join —
    this is the exact check that Cell 5's dispute-dedup logic must have
    already satisfied; this assertion is the safety net, not the primary fix."""
```
Print the resulting base rate. **Expected: 1,050 / 119,988 ≈ 0.875%** (119,988 = 120,000 raw rows − 12 duplicates removed in Cell 5). If this number is meaningfully off from the data spec's expected 0.8–1.0% range, stop and debug before moving to EDA — every downstream number depends on this being right.

**Cell 8 — merge in static merchant attributes**
Join `merchant category`, `avg_ticket_size`, `refund_window_days`, `delivery_sla_days` onto the labelled transaction table. **Do not** join anything from `customers` or `fulfilment` beyond this point — those require time-gated, per-transaction computation and belong entirely to notebook 3. This produces `01_master_labelled.csv`: one row per (cleaned, deduplicated) transaction, with the label and static merchant context attached, and nothing else.

**Cell 9 — data quality log**
Assemble every count printed across Cells 4–7 into one table and export it:

| Column | Description |
|---|---|
| `table` | which raw table the issue was found in |
| `issue` | short name, matching the data spec §3.x numbering |
| `rows_found` | count actually found in this run |
| `rows_expected` | count from `chargebacklens_data_spec.md` |
| `match` | `TRUE`/`FALSE` — `rows_found == rows_expected` |
| `handling_rule` | one line: dropped / clipped / nulled / flagged-only |

This file (`01_data_quality_log.csv`) is the single most reusable artifact in the whole project — it's the direct source for the data-quality section of `METRICS.md`, and any `FALSE` in the `match` column is worth investigating before continuing to notebook 2.

**Cell 10 — export** (5 cleaned tables + master + quality log), each followed by the round-trip assert from §1.4.

### 2.2 Definition of done for notebook 1
- All 7 output CSVs exist in `data/processed/`.
- `01_data_quality_log.csv` has zero `FALSE` rows in its `match` column.
- Base dispute rate printed in Cell 7 is between 0.8% and 1.0%.
- `01_master_labelled.csv` row count is `119,988` (raw 120,000 minus the 12 duplicate rows dropped in Cell 5), and contains **zero** columns from `fulfilment.csv` — a quick `assert not any(c in df.columns for c in ['delivered_at','delivery_status'])` is worth leaving in the notebook permanently as a leakage tripwire.

---

## 3. Notebook 2 — `02_eda.ipynb`

**Reads:** `01_master_labelled.csv`, `01_cleaned_customers.csv`, `01_cleaned_fulfilment.csv`. **Writes:** one summary CSV, plus inline Plotly figures. **Purpose:** every chart here should directly justify a decision made in notebooks 3–5 — this notebook is not decorative, and each chart's markdown cell should end with a one-line "this tells us…" note.

### 3.1 Cell-by-cell plan

1. **Load** the three input CSVs.
2. **Class imbalance summary** — bar chart of positive vs. negative counts, annotated with the exact ratio. This is the number that justifies `class_weight='balanced'` and PR-AUC-over-ROC-AUC in notebooks 4–5.
3. **Dispute rate over time** — weekly `is_disputed` rate, line chart, full Jan–Oct window. Look specifically at whether the rate drifts across the window. This chart is the direct justification for the temporal split in notebook 3 — if there's no drift at all, say so honestly in the markdown cell rather than overstating the case for a temporal split.
4. **Dispute rate by segment** — one bar chart each for `merchant_category`, `method`, `card_bin_country` (card transactions only), and cleaned `ip_state`. These confirm which raw fields carry signal before they're engineered into features in notebook 3.
5. **Amount distribution** — overlaid histogram of `log1p(amount)`, disputed vs. non-disputed. Decides whether the log transform is worth it (it will be — state that conclusion explicitly).
6. **Export `02_eda_segment_summary.csv`** — one row per (segment_type, segment_value): `dispute_rate`, `transaction_count`, `avg_amount`. This is the CSV a reader can open without re-running any Plotly cell, and it's a fast reference for notebook 3 when deciding which categorical fields are worth encoding vs. dropping.

### 3.2 Definition of done for notebook 2
- Every chart has a markdown cell underneath it stating the decision it informs.
- `02_eda_segment_summary.csv` exists and is non-empty.
- The base rate confirmed in Chart 2 matches the number printed in notebook 1, Cell 7 (a mismatch here means notebook 1's export or notebook 2's load has a bug).

---

## 4. Notebook 3 — `03_feature_engineering.ipynb`

**Reads:** the 5 cleaned tables from notebook 1. **Writes:** the feature matrix, the knowability tag table, and the temporal train/test split. **This is the highest-risk notebook in the project** — leakage introduced here silently invalidates notebooks 4 and 5 even though they'll run without error.

### 4.1 Cell-by-cell plan

1. **Load** `01_cleaned_transactions.csv`, `01_cleaned_customers.csv`, `01_cleaned_merchants.csv`, `01_master_labelled.csv` (for the label and `created_at`).
2. **Define and print `FEATURE_KNOWABILITY`** (per `chargebacklens_lld.md` §4.3) as a Python dict, then immediately export it:
   `03_feature_knowability.csv` — columns `feature_name`, `knowability` (`instant` / `trailing` / `forbidden`). Keep this as the first thing the notebook writes, before any feature is actually built, so the tag is a commitment made up front, not a label applied retroactively to justify whatever got built.
3. **`build_instant_features()`** — every feature computable from the transaction row plus static merchant attributes: `log_amount`, `amount_vs_merchant_avg_ratio`, `hour_of_day`, `day_of_week`, `is_night_txn`, `retry_count`, `checkout_latency_ms`, `method`, `is_foreign_bin`, `ip_billing_state_mismatch`, `account_age_days`.
4. **`build_trailing_features()`** — the core leakage-safe function (LLD §4.3). Sort by `(customer_id, created_at)`, use `groupby + rolling` with a time-indexed window and `closed='left'` — never a manual loop. Produces `txns_last_24h`, `txns_last_7d`, `distinct_devices_30d` (treating nulled `device_id` as "not a distinct device," per notebook 1 Cell 6), `prior_disputes_before_this_txn` (recomputed from `disputes.csv` directly — **never** read `customers.prior_disputes`, per data spec §3.2.1), `amount_vs_own_avg`, `merchant_dispute_rate_trailing_90d`.
5. **Sanity-check the leakage-sensitive feature by hand.** Pick the 40 customers flagged in `chargebacklens_data_spec.md` §3.2.1 (stale `prior_disputes`) and print, side by side, `customers.prior_disputes` vs. the freshly computed `prior_disputes_before_this_txn` for their transactions. They should differ. If they match, the trailing computation is accidentally reading the stale snapshot column somewhere — this is the single most valuable manual check in the whole notebook.
6. **`assemble_feature_matrix()`** — join instant + trailing + `is_disputed` + `created_at`. Two hard asserts, left permanently in the notebook:
   - `assert not any(FEATURE_KNOWABILITY.get(c) == 'forbidden' for c in X_full.columns)`
   - `assert X_full.isna().sum().sum() == 0` (after explicitly confirming which NaNs are legitimately zero-filled, e.g. a customer's first-ever transaction has `txns_last_7d = 0`, not NaN).
7. **Export `03_feature_matrix.csv`** — one row per transaction, `payment_id` as an explicit column (not the index — CSVs don't preserve a named index cleanly), all features, `is_disputed`, `created_at`.
8. **`temporal_split()`** — rows with `created_at < SPLIT_DATE` → train, else → test. Log and print row counts and positive rates for both splits; a large rate gap is worth reporting, not hiding.
9. **Export `03_train.csv` and `03_test.csv`** — `created_at` is retained in both files (useful for later traceability and for notebook 5's date-range reporting) but must be **dropped before fitting** in notebook 4 — it is a split key, never a model input. Say so in a markdown cell directly above the export.

### 4.2 Definition of done for notebook 3
- `03_feature_knowability.csv` contains no feature tagged `forbidden` anywhere in `03_feature_matrix.csv`'s columns.
- The manual 40-customer check in step 5 shows a real difference between stale and recomputed `prior_disputes`.
- `03_train.csv` + `03_test.csv` row counts sum to `03_feature_matrix.csv`'s row count exactly (no silent row loss across the split).
- Test-set positive rate is printed and is in a plausible range (not wildly different from train — if it is, that's worth a note, not a silent pass).

---

## 5. Notebook 4 — `04_model_building.ipynb`

**Reads:** `03_train.csv`, `03_test.csv`. **Writes:** three model files, train and test predictions, feature importances. **Purpose:** fit baseline → main → calibrated, in that order, and score both splits with all three so notebook 5 can compare them side by side.

### 5.1 Cell-by-cell plan

1. **Load** train/test, **drop `created_at` and `payment_id`** into a separate `meta_train`/`meta_test` DataFrame (keep `payment_id` for later re-joining, drop everything else that isn't a feature) before fitting.
2. **Identify `categorical_cols` and `numeric_cols`** from `03_feature_knowability.csv` — don't hand-type the list a second time; derive it from the artifact so the two can never drift apart.
3. **`build_preprocessing_pipeline()`** — `ColumnTransformer`: numeric → `SimpleImputer(median)`; categorical → `OrdinalEncoder` (HGB branch) or `OneHotEncoder` (baseline branch), per LLD §4.5.
4. **`fit_baseline()`** — `LogisticRegression(class_weight='balanced', max_iter=1000, random_state=RANDOM_SEED)` inside the OneHot + Scale pipeline.
5. **`fit_main_model()`** — `HistGradientBoostingClassifier(class_weight='balanced', max_iter=300, learning_rate=0.05, max_depth=6, random_state=RANDOM_SEED)` inside the Ordinal-encoded pipeline.
6. **`calibrate_model()`** — `CalibratedClassifierCV(estimator=main_pipeline, method='isotonic', cv=3)`, fit on train.
7. **Score all three models on both train and test**, building two wide DataFrames:
   `04_train_predictions.csv` / `04_test_predictions.csv` — columns: `payment_id`, `is_disputed`, `amount`, `merchant_category`, `proba_baseline`, `proba_main`, `proba_calibrated`.
8. **`feature_importance_table()`** — pull `.feature_importances_` from the fitted `HistGradientBoostingClassifier` step, pair with the post-`ColumnTransformer` feature names in the correct order, sort descending. Export `04_feature_importances.csv` (`feature`, `importance`).
9. **Save the three model objects** — `models/baseline_model.joblib`, `models/main_model.joblib`, `models/calibrated_model.joblib` via `joblib.dump`. This is the one place in the project where the output is intentionally not a CSV, because a fitted sklearn `Pipeline`/`CalibratedClassifierCV` object is not tabular data — serializing its coefficients or split points to CSV would either lose information or require reimplementing scikit-learn's own inference logic by hand. Every other artifact in this notebook, and every artifact in the rest of the project, is CSV.

### 5.2 Definition of done for notebook 4
- All three `.joblib` files load back successfully in a fresh cell (`joblib.load(...)`, then a single `.predict_proba()` call on one test row) before the notebook is considered finished.
- `04_test_predictions.csv` has exactly as many rows as `03_test.csv`.
- `proba_calibrated` values are all in `[0, 1]` and are **not** identical to `proba_main` (if they are, calibration silently didn't run).

---

## 6. Notebook 5 — `05_model_evaluation.ipynb`

**Reads:** `04_test_predictions.csv` (and `04_train_predictions.csv` where a train/test comparison is useful). **Writes:** every metric and economics artifact, plus `METRICS.md`'s data. **Purpose:** this is where the project earns the "risk manager, not classifier" framing — don't skip straight to the economics cells without first establishing the model's honest baseline performance.

### 6.1 Cell-by-cell plan — evaluation half

1. **Load** `04_test_predictions.csv`.
2. **`evaluate_model()`** for each of the three probability columns: PR-AUC (`average_precision_score`), precision@1%, precision@5%, confusion matrix at threshold 0.5 (interim sanity check only — the real threshold comes from §6.2), Brier score (calibrated model only). Assemble into `05_model_comparison.csv` — one row per model.
3. **Explicitly print, and note in a markdown cell, why ROC-AUC is not in this table**: at a ~0.9% base rate it's dominated by the true-negative mass and stays misleadingly high. If you compute it anyway out of curiosity, put it in a side cell with that same one-line caveat — never in the exported CSV or `METRICS.md`.
4. **Calibration curve** — bin `proba_main` and `proba_calibrated` into deciles, compute observed frequency per bin for each, export `05_calibration_curve.csv` (`model`, `bin_midpoint`, `predicted_mean`, `observed_frequency`), then plot both against the y=x reference line. This is the chart that makes calibration's value visible rather than asserted.
5. **PR curve** — all three models overlaid, one Plotly figure, no CSV export needed (it's fully derivable from `04_test_predictions.csv` + `is_disputed`).

### 6.2 Cell-by-cell plan — economics half

6. **Define `ECONOMICS_PARAMS`** (per LLD §4.7: `dispute_fee=1500`, `ops_review_cost=300`, `merchant_margin=0.18`, `step_up_abandon_rate=0.25`) and export immediately as `05_economics_params.csv` (`param`, `value`) — two columns, one row per parameter, so a reader (or the Streamlit economics tab) can read the exact assumptions without opening the notebook.
7. **`expected_cost_matrix()`** — per-transaction cost under each of the four outcomes, as defined in LLD §4.7.
8. **`threshold_sweep()`** — sweep `np.linspace(0.01, 0.99, 100)`, using `proba_calibrated` only (never the uncalibrated score). Export `05_threshold_sweep.csv` (`threshold`, `precision`, `recall`, `net_savings_inr`, `n_flagged`).
9. **Identify the two operating thresholds** (allow/step-up boundary and step-up/manual-review boundary) from the sweep — the LLD's three-band decision needs two cut points, not one. Append both to `05_economics_params.csv` as two more rows (`threshold_allow_stepup`, `threshold_stepup_review`).
10. **`sensitivity_analysis()`** — re-sweep varying `step_up_abandon_rate` from 0.10 to 0.40. Export `05_sensitivity_analysis.csv` (`param_value`, `optimal_threshold`, `net_savings_inr`). State plainly in a markdown cell whether the optimal threshold survives a wrong assumption.
11. **`segment_economics()`** — re-sweep separately per amount bucket (`<2000`, `2000-10000`, `>10000`) and per `merchant_category`. Export `05_segment_economics.csv` (`segment_type`, `segment_value`, `best_net_savings_inr`, `optimal_threshold`). Write the "don't deploy here" finding directly into a markdown cell — this is the single most differentiating sentence in the whole submission, so it shouldn't only live in a CSV.

### 6.3 Cell-by-cell plan — final export for the app

12. **Build `05_scored_test_sample.csv`** — sample (or take, if under 5,000 rows) up to 5,000 rows from `04_test_predictions.csv`, joined back to the human-readable feature columns from `03_test.csv` that Tab 2 of the app needs to display (`method`, `merchant_category`, `is_first_txn_for_device`, `retry_count`, etc.), plus `proba_calibrated`, `is_disputed`, `amount`. This is the file `app/streamlit_app.py`'s review-queue tab reads directly — no live inference in the app for this tab.
13. **Write `METRICS.md`** by hand, pulling numbers directly from `05_model_comparison.csv`, `05_threshold_sweep.csv`, `05_segment_economics.csv`, and `01_data_quality_log.csv`. Every number in `METRICS.md` should be traceable to a specific CSV cell — resist the temptation to write a round or flattering number that isn't actually in one of the exported files.

### 6.4 Definition of done for notebook 5
- `05_model_comparison.csv` shows PR-AUC improving baseline → main, and Brier score improving main → calibrated (if Brier gets *worse* after calibration, something in Cell 6 of notebook 4 is wrong — go back before writing `METRICS.md`).
- `05_segment_economics.csv` contains at least one segment with negative or near-zero `best_net_savings_inr` — if every segment looks profitable, the economics parameters in Cell 6 are probably too favorable and worth revisiting for credibility.
- `05_scored_test_sample.csv` exists, is under 5,000 rows, and contains every column the Streamlit app's Tab 1 and Tab 2 will need — cross-check this against §7.2 below before moving on, since a missing column here becomes a `KeyError` in the app, not in the notebook.

---

## 7. From notebooks to `.py` — what changes and why

### 7.1 The risk this step introduces

Every function above was written once, in a notebook, against `03_feature_matrix.csv`'s exact formulas. The Streamlit app needs some of that same logic — specifically the instant-feature formulas from notebook 3 (`log_amount`, `amount_vs_merchant_avg_ratio`, etc.) and the threshold-lookup logic from notebook 5 — to score a **brand-new, manually-entered transaction** that never went through notebook 1–3's batch pipeline. If you retype those formulas from scratch inside `app/scoring.py`, the notebook and the app will silently diverge the first time either one is edited later. This is the exact failure mode `chargebacklens_hld.md` §5.7 and §11 both call out.

**The fix:** copy the instant-feature formulas out of notebook 3, Cell 3, verbatim, into `app/scoring.py`, as the single source of truth going forward. Do not leave a second copy in the notebook — either re-import from `app/scoring.py` back into the notebook (cleanest, if your notebook environment can import from `app/`), or leave a comment in notebook 3 pointing at `app/scoring.py` as the canonical version once it exists.

### 7.2 `app/scoring.py` — what it needs, sourced from which notebook

| Function | Ported from | Notes |
|---|---|---|
| `build_feature_row(form_inputs, feature_columns)` | Notebook 3, `build_instant_features` formulas | `feature_columns` loaded from `03_feature_knowability.csv`'s `feature_name` column, in the same order the model was fit on — read that order from `04_feature_importances.csv` or re-derive it from the fitted pipeline's `feature_names_in_` if available |
| `score_transaction(model, feature_row)` | Notebook 4 | Just `model.predict_proba(feature_row)[0, 1]` — no porting risk here |
| `recommend_action(probability, economics_params_df)` | Notebook 5, step 9 | Reads the two threshold rows out of `05_economics_params.csv` |
| `load_model()` | — | `joblib.load("data/processed/models/calibrated_model.joblib")` |

### 7.3 `app/economics.py`

| Function | Ported from |
|---|---|
| `recompute_sweep_live(scored_df, params)` | Notebook 5, step 8 (`threshold_sweep`) — same function body, just re-run at request time on `05_scored_test_sample.csv`'s columns instead of the full test set |

### 7.4 `app/explain.py`

Not ported from any notebook — this is new code, per `chargebacklens_lld.md` §5.5: an Anthropic API call for the reviewer note, with a deterministic template fallback for when `ANTHROPIC_API_KEY` isn't set.

### 7.5 Checklist before touching Streamlit at all

- [ ] `app/scoring.py`'s `build_feature_row()` produces the **identical** feature row for a hand-picked transaction as notebook 3's pipeline did — run a one-off check: take one `payment_id` from `03_test.csv`, feed its raw inputs through `app/scoring.py`, and diff the resulting row against the corresponding row in `03_feature_matrix.csv`. Any mismatch here is a bug you want to catch now, not after deployment.
- [ ] `app/scoring.py` imports `feature_columns` order from a file, never hardcodes it as a Python list — if `03_feature_knowability.csv` changes, the app should break loudly on the next run, not silently misalign.

---

## 8. Streamlit app — build order

Build and manually test one tab at a time, in this order, per `chargebacklens_lld.md` §5:

1. **App shell** — `st.set_page_config`, the two `@st.cache_resource`/`@st.cache_data` loaders (LLD §5.1), and the three empty tabs. Run it. Confirm it boots in under a second and confirm the cached loaders aren't silently re-reading the CSVs on every widget interaction (add a temporary `st.write("loaded at", datetime.now())` inside each cached function during development, remove before submission).
2. **Tab 2 (Review Queue) first, not Tab 1** — it's pure read-and-display against `05_scored_test_sample.csv`, no scoring logic, no LLM call. It's the fastest way to confirm the artifact chain actually reads correctly inside Streamlit before adding any interactive complexity.
3. **Tab 3 (Economics Explorer)** — wires `app/economics.py`'s `recompute_sweep_live()` to the three sliders. Confirm the optimal-threshold marker actually moves when a slider moves; a static-looking chart here usually means the recompute function isn't being called on slider change (a `st.cache_data` decorator wrongly applied to a function that should recompute every time is the usual cause).
4. **Tab 1 (Score a Transaction)** last — it's the most complex tab (form inputs → `build_feature_row` → `score_transaction` → `recommend_action` → `generate_reviewer_note`), and by this point Tabs 2 and 3 have already proven the model and artifacts load correctly, so any remaining bug is isolated to the form-to-feature-row mapping in `app/scoring.py`.
5. **Wire `app/explain.py`** into Tab 1's output and Tab 2's row-click card. Test both **with** and **without** `ANTHROPIC_API_KEY` set — the fallback path is not optional to test, it's the default state a judge will see.

---

## 9. Pre-submission validation checklist

Run through this in order, on a clean checkout if possible (delete `data/processed/`, re-run all 5 notebooks top to bottom, then start the app) — the single most common demo-day failure is a stale artifact from an earlier, since-changed version of a notebook.

- [ ] All 5 notebooks run top-to-bottom without error, in numeric order, with no manual cell re-ordering required.
- [ ] `01_data_quality_log.csv` — zero `FALSE` rows in `match`.
- [ ] `03_feature_matrix.csv` — zero forbidden-tagged columns present.
- [ ] `04_test_predictions.csv` — `proba_calibrated` differs from `proba_main` (calibration actually ran).
- [ ] `05_segment_economics.csv` — at least one segment shows the model isn't worth deploying, and that finding is written into `METRICS.md` in plain language.
- [ ] `streamlit run app/streamlit_app.py` boots with no `ANTHROPIC_API_KEY` set — Tab 1's note falls back to the template, no exception.
- [ ] `streamlit run app/streamlit_app.py` boots **with** `ANTHROPIC_API_KEY` set — Tab 1's note comes from the API and reads as a genuine 2–3 sentence note, not a malformed response.
- [ ] Every number quoted in the README or the pitch video traces back to a specific cell in `data/processed/*.csv` — no number typed from memory.
- [ ] `SCOPE.md` exists and states the defense-only boundary explicitly (per `chargebacklens_hld.md` §9).
- [ ] `FAILURES.md` documents the real thing that broke during this build, with before/after numbers.

---

## 10. Deployment (Streamlit Community Cloud)

1. Push the repo, with `data/raw/` and the large `data/processed/` files (`03_feature_matrix.csv`, `03_train.csv`, `03_test.csv`, `04_train_predictions.csv`) added to `.gitignore` — the app doesn't need them at runtime, only the small final artifacts do (`05_scored_test_sample.csv`, `05_threshold_sweep.csv`, `05_economics_params.csv`, `04_feature_importances.csv`, the three `.joblib` files).
2. Commit a small **sample** of the gitignored files (e.g. `data/raw/*_sample.csv`, first 500 rows) so a judge cloning the repo can still re-run the notebooks end-to-end without the full dataset, per `chargebacklens_hld.md` §10.
3. On Streamlit Community Cloud: point it at `app/streamlit_app.py`, set `ANTHROPIC_API_KEY` in the app's **Secrets** panel (never commit it to the repo), and confirm `requirements.txt` versions match what actually pickled the model — this is the most common cause of a deployed app crashing on `joblib.load()` when it worked fine locally.
4. After deploying, immediately repeat the two `st.cache` boot checks from §9 (with and without the API key) against the **deployed** URL, not just localhost — secrets and dependency versions are the two things that differ between the two environments.
