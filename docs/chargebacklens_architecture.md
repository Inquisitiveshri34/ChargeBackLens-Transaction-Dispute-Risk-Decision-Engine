# ChargebackLens — Architecture (As-Built)

**Track:** Razorpay AI Buildathon — Track 02, AI Risk Manager
**Status of this document:** describes the system **as it actually exists** after notebooks 01–05 and the Streamlit app were built and verified. Every structural claim traces to a file on disk; every number traces to a cell output already recorded in the per-notebook `.md` files.

**Relationship to the other design documents:**

| Document | Answers | Written | Authority |
|---|---|---|---|
| `chargebacklens_hld.md` | *Why does the system look like this?* | Before the build | Intent — still valid at the rationale level |
| `chargebacklens_lld.md` | *How should each function be implemented?* | Before the build | Prescription — superseded in eight places (§11) |
| `chargebacklens_dev_plan.md` | *In what order is it built?* | Before the build | Sequence — complete |
| `chargebacklens_data_spec.md` | *What is in the five raw CSVs?* | Before the build | Input contract — three arithmetic discrepancies flagged, not adopted |
| **This document** | *What is the system, structurally, right now?* | After the build | **As-built authority** |
| `blockers.md` | *Where and why did prescription and reality diverge?* | During the build | Deviation ledger, BLK-001 … BLK-009 |

Where this document and the HLD/LLD disagree, this document is correct and §11 names the delta.

---

## 1. What the system is

ChargebackLens converts a payment transaction into a **calibrated probability of dispute**, and then converts that probability into a **rupee-optimal routing decision** — `allow`, `step_up`, or `manual_review`.

The distinction matters architecturally, not just rhetorically. A classifier's output is a score; this system's output is a *decision with a price attached*. That forces three structural properties that a classifier would not need:

1. Probabilities must be **calibrated**, because they get multiplied by rupee amounts. A ranking-correct but magnitude-wrong score produces a cost estimate with no defensible meaning.
2. The decision layer must be **downstream of and independent from** the model. Economics consumes `(probability, amount, outcome)` tuples only — it has no knowledge of model internals and survives a model swap unchanged.
3. The system must be able to say **"do not deploy here."** A segment-level economics layer exists specifically to surface segments where intervention costs more than it saves.

**Scope boundary (hard, not a preference):** defense-only. The system produces a defensive risk signal and a recommended action. It contains no evasion testing, no adversarial-example generation, and no component that documents how to avoid detection. This is enforced as an architectural rule — no module in the dependency graph takes a "how would this be evaded" input.

---

## 2. Context diagram (as-built)

```
        ┌──────────────────────────────────────────────┐
        │  Five pre-generated raw CSVs                 │
        │  transactions · customers · merchants ·      │
        │  fulfilment · disputes                       │
        │  EXTERNAL TO THIS SYSTEM — read-only,        │
        │  never written by any component here         │
        └────────────────────┬─────────────────────────┘
                             │ read once, notebook 01 only
                             ▼
 ╔═══════════════════════════════════════════════════════════════╗
 ║  OFFLINE PHASE — five Jupyter notebooks, run once, in order   ║
 ║                                                               ║
 ║   01 clean+merge → 02 EDA → 03 features → 04 model →  05 eval ║
 ║        119,988×24    diagnostics  119,977×30   3 fits  economics║
 ╚════════════════════════════╤══════════════════════════════════╝
                              │ writes 25 CSVs + 3 .joblib
                              ▼
              ┌────────────────────────────────────┐
              │      THE SEAM — data/processed/    │
              │  frozen artifacts, content-hashed, │
              │  contract-checked at app boot      │
              └────────────────┬───────────────────┘
                               │ read-only, once per process
                               ▼
 ╔═══════════════════════════════════════════════════════════════╗
 ║  ONLINE PHASE — Streamlit, 1 app + 3 shared modules           ║
 ║   streamlit_app.py  ·  scoring.py  ·  economics.py            ║
 ║                                       ·  explain.py           ║
 ║   Tab 1 Score  ·  Tab 2 Review Queue  ·  Tab 3 Economics      ║
 ╚════════════════════════════╤══════════════════════════════════╝
                              │ optional, one bounded call
                              ▼
              ┌────────────────────────────────────┐
              │  Anthropic API — reviewer-note     │
              │  text only. Deterministic template │
              │  fallback; core app never depends  │
              │  on it.                            │
              └────────────────────────────────────┘
```

**Two actors, deliberately non-overlapping.** The notebook operator produces artifacts and owns modelling decisions. The reviewer consumes artifacts and makes a decision on a transaction. The app cannot train; the notebooks do not serve. Neither role can accidentally do the other's job.

---

## 3. Layered view

| # | Layer | Implemented in | Consumes | Produces | Core invariant it enforces |
|---|---|---|---|---|---|
| L1 | Data | `01_data_cleaning_merging.ipynb` | 5 raw CSVs | `01_master_labelled.csv` (119,988 × 24) | The label is derived **once** and carried forward as one column; nothing downstream re-derives it |
| L2 | Diagnostics | `02_eda.ipynb` | L1 | `02_eda_segment_summary.csv` | `FORBIDDEN` columns are charted **with explicit labels**, so exclusions are documented rather than silent |
| L3 | Features | `03_feature_engineering.ipynb` | L1 | `03_feature_matrix.csv`, `03_train.csv`, `03_test.csv`, `03_feature_knowability.csv` | Knowability contract written **before** any feature is built; leakage tripwire asserted after |
| L4 | Modelling | `04_model_building.ipynb` | L3 | 3 `.joblib` + 10 CSVs | Three models fit and exported, not one — a comparison is evidence, a single model is a claim |
| L5 | Evaluation | `05_model_evaluation.ipynb` | L4 (+ 3 cols of L1 for the censoring audit) | 9 CSVs | Ranking metrics and magnitude metrics are reported separately and never conflated |
| L6 | Economics | `05` notebook + `economics.py` | calibrated probability + amount + outcome | policy bands, thresholds, sensitivity, segment table | Depends on **no** model internals — pure `(y, p, amount, params)` |
| L7 | Explanation | `explain.py` | scored row + coefficients | reviewer note | Bounded to text generation; never touches scoring, thresholds, or features |
| L8 | Application | `streamlit_app.py` | the frozen artifact set | UI | Never trains, never reads `data/raw/`, refuses to boot on a contract failure |

L6 is the layer that makes this a risk manager rather than a classifier. L7 is the only layer with an external dependency, and it is optional by construction.

---

## 4. Component catalogue

### 4.1 Offline components

**Notebook 01 — cleaning and merging.** Reads the five raw CSVs, applies 14 documented cleaning rules, joins to a single labelled transaction table at payment grain. Output: 119,988 × 24, base dispute rate **0.8751%** (inside the spec band). Runs the leakage tripwire for the first time. Where the data spec's arithmetic was internally inconsistent (`issuer_bank` nulls, `delivery_sla_days` nulls, fulfilment per-issue totals), the structural rule was honoured, the measured count recorded, and the spec line flagged — never silently overwritten with the spec's wrong number.

**Notebook 02 — EDA.** Produces the diagnostics that shape every later decision: class imbalance at **113:1**, segment dispute rates, the temporal split marker. Identifies `email_domain_type` and `phone_verified` as the strongest single signals. Its architectural contribution is the decision, made here and once, that ROC-AUC is a diagnostic and not a headline.

**Notebook 03 — feature engineering.** The highest-risk component in the system, because a dispute dataset has an unusually sharp leakage hazard: delivery status and delivery timestamps are only knowable *after* the moment a decision would need to be made. Mitigation is mechanical, not editorial:

- A **feature knowability contract** (`03_feature_knowability.csv`, 46 rows × 5 cols) is written before any feature is built. Every candidate is tagged `INSTANT` / `TRAILING` / `FORBIDDEN` with a rationale.
- Customer-grain and merchant-grain features are built as **trailing windows** computed strictly from rows before the transaction under consideration.
- A tripwire asserts no `FORBIDDEN` column reached the matrix.

Output: `03_feature_matrix.csv` at 119,977 × 30 — eleven rows short of the master table, which is the documented drop, not attrition. Split **temporally** at `2026-08-01`: train 74,731, test 45,246.

**Notebook 04 — model building.** Fits three models and exports all three, including the two that lost. Selection rule was written down before it was applied.

- The LLD-prescribed `HistGradientBoostingClassifier` was fit, measured, and **rejected** — it lost to its own baseline on test PR-AUC (BLK-006).
- `class_weight='balanced'` inflated probabilities roughly **50×**, which is harmless for ranking and fatal for an economics layer that multiplies probabilities by rupees (BLK-007).
- The prescribed **isotonic** calibration destroyed ranking; sigmoid did not (BLK-008).

Deployed scorer: unweighted `LogisticRegression` wrapped in `CalibratedClassifierCV` with a **prefit sigmoid** calibrator over a `FrozenEstimator`, calibration cut at `2026-06-24 09:16:28`, seed 42, scikit-learn 1.7.2, **26 features** (23 numeric, 3 categorical).

**Notebook 05 — evaluation and economics.** Reads `04_test_predictions.csv` once and refits nothing. Produces the threshold sweep, the joint two-threshold optimisation, the sensitivity analysis across four parameters, the segment economics table, the censoring audit, and the stratified scored sample the app's queue reads. Ten of ten definition-of-done checks passed; all nine exports round-tripped.

### 4.2 Online components

**`scoring.py` — the canonical feature and artifact module.** This is the anti-divergence device in the architecture. The instant-feature formulas are **ported from notebook 03 and this is the canonical copy** — the app does not re-implement them. Responsibilities:

- Typed loaders for every artifact the app touches (`load_model`, `load_feature_columns`, `load_economics_params`, `load_scored_sample`, `load_policy_bands`, `load_threshold_sweep`, `load_segment_economics`, `load_sensitivity`, `load_censoring_audit`, `load_model_comparison`, `load_calibration_curve`, `load_feature_importances`, `load_model_coefficients`, `load_test_predictions`).
- `build_instant_features` / `build_feature_row` — construct a model-ready row in the model's exact column order.
- `recommend_action` / `recommend_action_vec` — the single definition of what "high risk" means, shared by notebook and app.
- `assert_model_contract` — the boot gate (§7).
- `verify_instant_features_against_matrix` — round-trips app-computed features against the notebook's matrix on a sample, so drift is detectable rather than theoretical.

**`economics.py` — the decision calculus.** Pure functions over `(y, proba, amounts, params)`. `expected_cost_matrix`, `do_nothing_cost`, `quantile_grid`, `threshold_sweep`, `optimise_bands`, `policy_cost`, `policy_bands_table`, `sensitivity_analysis`, `segment_economics_live`, `load_economics_basis`. No sklearn import in the decision path; no model object ever passed in.

**`explain.py` — the bounded LLM surface.** `top_drivers` derives contributing terms from the exported model coefficients (deterministic). `template_note` produces a note with zero external dependency. `generate_reviewer_note` optionally calls the Anthropic API with a fixed system prompt and falls back to the template on any failure or missing key. The LLM has no path to scoring, thresholding, or feature computation.

**`streamlit_app.py` — the shell.** Three tabs over one frozen artifact set, plus a header strip carrying the four caveats **above the fold rather than in a footnote** (censoring, floor-not-estimate, robust conclusion / fragile operating point, one loss-making segment band).

---

## 5. Data architecture

### 5.1 Artifact format rule

**All data artifacts are CSV.** The only exception is the three fitted `.joblib` model objects. The reason is inspectability: a judge, a reviewer, or a future maintainer can open any number this system reports in a text editor without deserializing a pickle. This is a stated constraint, not an accident of tooling.

### 5.2 Producer / consumer ledger

| Artifact | Producer | Consumers | Shape |
|---|---|---|---|
| `01_master_labelled.csv` | NB01 | NB02, NB03, NB05 (3 cols only) | 119,988 × 24 |
| `02_eda_segment_summary.csv` | NB02 | documentation | 64 × 6 |
| `03_feature_knowability.csv` | NB03 | NB04 (load-time assert) | 46 × 5 |
| `03_feature_matrix.csv` | NB03 | NB03 split, `scoring.py` verification | 119,977 × 30 |
| `03_train.csv` / `03_test.csv` | NB03 | NB04; NB05 (18 display cols) | 74,731 / 45,246 × 30 |
| `models/baseline_model.joblib` | NB04 | comparator only | — |
| `models/main_model.joblib` | NB04 | comparator only | — |
| `models/calibrated_model.joblib` | NB04 | **app, live scoring** | — |
| `04_model_card.csv` | NB04 | NB05, app header, boot contract | 7 × 2 |
| `04_feature_columns.csv` | NB04 | **app, column order of record** | 26 × 3 |
| `04_model_coefficients.csv` | NB04 | `explain.py` | 38 × 3 |
| `04_feature_importances.csv` | NB04 | app | 26 × 5 |
| `04_test_predictions.csv` | NB04 | NB05, app Tab 3 (exact basis) | 45,246 × 10 |
| `04_train_predictions.csv` | NB04 | NB05 boundary assert only | 74,731 × 10 |
| `04_validation_leaderboard.csv`, `04_test_metrics.csv`, `04_reliability_bins.csv`, `04_hgb_search_results.csv` | NB04 | NB05 cross-checks, documentation | small |
| `05_economics_params.csv` | NB05 | **app, the deployed policy** | 8 × 2 |
| `05_policy_bands.csv` | NB05 | app header, economics basis weights | 3 × 8 |
| `05_threshold_sweep.csv` | NB05 | app Tab 3 | 101 × 10 |
| `05_sensitivity_analysis.csv` | NB05 | app Tab 3 | 22 × 7 |
| `05_segment_economics.csv` | NB05 | app Tab 3 | 15 × 15 |
| `05_model_comparison.csv` | NB05 | app header | 4 × 17 |
| `05_calibration_curve.csv` | NB05 | app | 20 × 7 |
| `05_censoring_audit.csv` | NB05 | app caveat strip | 1 × 5 |
| `05_scored_test_sample.csv` | NB05 | **app Tab 2**, Tab 3 fallback basis | 5,000 × 23 |

### 5.3 Verification discipline

Every CSV export is **immediately read back and shape-asserted** by its producing notebook. Cross-checks run against upstream artifacts rather than recomputing on faith — notebook 05 validates its recomputed metrics against `04_test_metrics.csv` and its deciles against `04_reliability_bins.csv` rather than trusting either in isolation. Notebook 04 reloads all three `.joblib` files from disk and re-scores a test row before declaring itself done.

---

## 6. Model architecture

```
raw form input / test row
        │
        ▼
 build_feature_row()  ── column order from 04_feature_columns.csv ──┐
        │                                                           │
        ▼                                                           │
 ColumnTransformer                                                  │
   ├── 23 numeric      → passthrough / scaling                      │
   └──  3 categorical  → one-hot (method, merchant_category,        │
                          email_domain_type)                        │
        │                                                           │
        ▼                                                           │
 LogisticRegression (unweighted)  ← FrozenEstimator                 │
        │                                                           │
        ▼                                                           │
 CalibratedClassifierCV(method="sigmoid", cv="prefit")              │
        │                                                           │
        ▼                                                     assert_model_contract()
   proba_calibrated ∈ [0, 1]  ──────────────────────────────────────┘
```

**Why unweighted + prefit sigmoid, not the prescribed HGB + balanced + isotonic:** measured, in that order.

| Column | PR-AUC | Lift@1% | P@5% | Brier | Brier skill | max p |
|---|---:|---:|---:|---:|---:|---:|
| `proba_baseline` (LR balanced) | 0.0842 | 17.2× | 7.69% | 0.1404 | **−14.75** | 0.991 |
| `proba_main` (tuned HGB) | 0.0812 | 15.5× | 7.21% | 0.0086 | +0.037 | 0.399 |
| `proba_selected` (LR plain) | 0.0872 | 16.2× | 7.78% | 0.0085 | +0.043 | 0.474 |
| **`proba_calibrated`** (deployed) | **0.0872** | **16.2×** | **7.78%** | 0.0086 | **+0.039** | 0.334 |

The baseline's higher lift@1% alongside a Brier skill score of **−14.75** is the entire argument for separating ranking metrics from magnitude metrics. It ranks acceptably and its probabilities are unusable. Deploying it would have produced a beautiful-looking economics layer built on numbers that mean nothing.

**Metric selection, stated once:** PR-AUC and precision@k are headline; ROC-AUC is retained in the CSVs under the column name `roc_auc_DIAGNOSTIC_ONLY` so the naming itself prevents its promotion. At a 0.8995% test base rate, ROC-AUC is dominated by the true-negative mass.

---

## 7. The seam: offline → online contract

Nothing crosses the seam except named files in `data/processed/`. The app enforces this at boot, before any UI renders:

```
get_artifacts()  → all CSV loaders, @st.cache_data (content-hashed, immutable)
get_model()      → calibrated_model.joblib, @st.cache_resource (one object per process)
assert_model_contract(MODEL, feature_columns)
   ├── 04_model_card.csv n_features == len(04_feature_columns.csv)      → else ArtifactError
   ├── fitted pipeline feature_names_in_ == feature_columns (order too) → else ArtifactError
   └── fitted pipeline n_features_in_    == len(feature_columns)        → else ArtifactError
on ArtifactError: st.error(...) ; st.code(...) ; st.stop()
```

**The app refuses to score rather than scoring on a mismatched contract.** This is the single most important online invariant: a column-order drift between the exported feature list and the fitted pipeline is silent, produces plausible-looking probabilities, and would corrupt every rupee figure downstream. The contract check returns a report of *what was actually checkable*, so the app displays a verified fact rather than claiming a check it could not run.

The `@st.cache_resource` / `@st.cache_data` split is deliberate and not cosmetic — mixing them is the most common Streamlit caching bug, and the third cache (`run_policy`) is keyed on the **parameter tuple** so a slider move invalidates it, which is precisely the failure the LLD warned about in the opposite direction.

---

## 8. Decision architecture

### 8.1 Cost model

Four parameters, all merchant-supplied, all exposed as sliders:

| Parameter | Deployed value | Role |
|---|---:|---|
| `dispute_fee` | ₹1,500 | fixed per-dispute cost, incurred regardless of outcome |
| `ops_review_cost` | ₹300 | cost of one manual review |
| `merchant_margin` | 0.18 | margin lost when a step-up drives abandonment |
| `step_up_abandon_rate` | 0.25 | probability a stepped-up legitimate customer abandons |

### 8.2 Three bands, two thresholds

| Band | Range | n | Disputes | Share of volume | Dispute rate | Lift vs base |
|---|---|---:|---:|---:|---:|---:|
| `allow` | 0 – 0.02443 | 42,152 | 204 | 93.16% | 0.484% | 0.54× |
| `step_up` | 0.02443 – 0.08240 | 2,786 | 151 | 6.16% | 5.420% | **6.03×** |
| `manual_review` | 0.08240 – 1.0 | 308 | 52 | 0.68% | 16.883% | **18.77×** |

Thresholds are found by **joint optimisation over a quantile grid**, not a `linspace` grid — a uniform grid over a distribution whose mass sits below 0.05 spends 95% of its evaluations on empty space. Net savings at this policy: **₹11,99,620** against a do-nothing exposure of **₹30,69,547** — 39.1%.

**The second threshold is justified by measurement, not by taste.** The app computes the best single-threshold policy on the same parameters live and displays the delta, so the two-band-vs-three-band choice is defended with a number every time the tab renders.

### 8.3 Where not to deploy

`05_segment_economics.csv` reports 15 segments across three segment types (`method`, `merchant_category`, `amount_bucket`) with per-band net rupees. The finding it exists to surface: **`method = wallet` loses money in the manual-review band** — −₹300 across one review and zero catches — while earning ₹9,779 in its step-up band. The architectural point is that a single global optimum would have hidden this, and the honest conclusion is about routing the queue by ticket size rather than excluding wallet.

### 8.4 Sensitivity

Four parameters swept, 22 rows. Net savings stay positive from ₹10.9L to ₹18.1L across step-up abandon rates 0.10–0.40, but **the allow/step-up cut moves 3.1×**. The conclusion is robust; the operating point is not. `step_up_abandon_rate` is the one parameter a merchant must measure rather than assume, and the app's slider carries that as help text.

---

## 9. Cross-cutting concerns

| Concern | Mechanism | Where enforced |
|---|---|---|
| **Leakage** | Knowability contract written before features; tripwire asserted after; temporal split; `FORBIDDEN` columns charted with labels in EDA | NB02, NB03, NB04 load-assert |
| **Calibration before economics** | Economics layer only ever reads `proba_calibrated`; magnitude metrics (Brier skill, ECE) tracked separately from ranking metrics | NB04 → NB05 boundary |
| **Reproducibility** | Seed 42 threaded through every stochastic call; sklearn version pinned in the model card and surfaced in the app header | NB04, app header |
| **Round-trip verification** | Every export re-read and shape-asserted; models reloaded and re-scored; cross-checks against upstream artifacts | all notebooks |
| **Binning convention** | Pinned after BLK-009 — NB04's `pd.qcut` and NB05's rank-and-floor disagreed on four decile rows and failed a calibration assert | NB04/NB05 |
| **Contract drift** | `assert_model_contract` at boot; `verify_instant_features_against_matrix` for formula drift | `scoring.py` |
| **Sample reweighting** | Tab 2's stratified 5,000-row sample carries `risk_percentile` ranked within the full 45,246; Tab 3 prefers the exact 45,246-row basis and only falls back to inverse-weighted sampling, labelled as an estimate | app Tabs 2 and 3 |
| **Graceful degradation** | `explain.py` template fallback; economics basis fallback; both labelled in the UI when taken | `explain.py`, `economics.py` |
| **Defense-only** | No module accepts an evasion-shaped input; no artifact documents detector avoidance | architectural, whole system |
| **Currency presentation** | `rupees()` — Indian digit grouping (₹11,99,620, not ₹1,199,620) | `streamlit_app.py` |

---

## 10. Runtime paths

**Path A — score a new transaction (Tab 1).** Form input → `build_instant_features` → `build_feature_row` (model column order) → `predict_proba` → `recommend_action` against the two deployed thresholds → `top_drivers` from exported coefficients → `generate_reviewer_note` (API if keyed, template otherwise). This is the **only** live inference in the app.

**Path B — work the queue (Tab 2).** Pure read of `05_scored_test_sample.csv`. No inference. The tab states in its own caption that the sample is stratified rather than random and that its in-slice precision is an **ordering diagnostic**, quoting the population figures (precision@1% = 14.6%, precision@5% = 7.78%) from `05_model_comparison.csv` instead.

**Path C — explore economics (Tab 3).** Sliders → `run_policy` (cached on the parameter tuple) → `optimise_bands` + `threshold_sweep` on the loaded basis. At default parameters on the exact basis the live optimiser **reproduces the exported ₹11,99,620 exactly**, which makes this tab a live cross-check of notebook 05 rather than a parallel calculation that happens to look similar.

Path C also carries the one reading trap the system knows about and warns on inline: `dispute_fee` and `ops_review_cost` both sit inside `fn_cost`, so raising either also raises the do-nothing baseline that net savings is measured against. Net savings across different values of those two parameters is **not comparable**, and the app says so and shows total cost instead.

---

## 11. As-built deltas from the HLD/LLD

| # | Prescribed | Built | Reason | Trace |
|---|---|---|---|---|
| 1 | One notebook with nine sections | Five notebooks, 01–05 | A single notebook cannot be re-run partially; five give per-stage definition-of-done gates | dev plan |
| 2 | `HistGradientBoostingClassifier` deployed | `LogisticRegression`, unweighted | HGB lost to its own baseline on test PR-AUC | BLK-006 |
| 3 | `class_weight='balanced'` | unweighted | Inflated probabilities ~50×, unusable by the economics layer | BLK-007 |
| 4 | Isotonic calibration | Prefit sigmoid | Isotonic destroyed ranking | BLK-008 |
| 5 | No hyperparameter search | 16-point search, exported | Fixed hyperparameters were chosen before the split's positive count was known | `04_hgb_search_results.csv` |
| 6 | `linspace` threshold grid | Quantile grid, 101 steps | Uniform grid wastes 95% of evaluations above the score mass | NB05 §5 |
| 7 | Confusion matrix at 0.5 | Band table at the optimised cuts | Nothing is near 0.5; max calibrated p is 0.334 | NB05 §5 |
| 8 | Bare Brier score | Brier **skill score** vs constant base-rate predictor | Bare Brier at a 0.9% base rate is uninterpretable | `05_model_comparison.csv` |
| 9 | Self-optimised segment table | Segments evaluated at the **global** policy as well | A per-segment optimum is not the policy that would ship | NB05 §5 |
| 10 | Six artifacts cross the seam | 25 CSVs + 3 `.joblib` | Evidence artifacts (policy bands, censoring audit) needed a row on disk, not a cell print | §5.2 |
| 11 | Sensitivity on one parameter | Four parameters, 22 rows | One parameter cannot show which one is fragile | `05_sensitivity_analysis.csv` |
| 12 | SHAP explanations preferred | Coefficient-derived drivers | Deployed model is linear; coefficients *are* the exact attribution | `explain.py` |

Every one of these was measured before it was adopted. None was a silent substitution.

---

## 12. Known limitations and architectural debt

1. **Label censoring.** 294 of 407 test positives (**72.2%**) have `dispute_raised_at` after the declared 2026-11-01 snapshot, the latest at 2027-01-26. Ranking is unaffected — every feature is time-gated and the tripwire passed — but the label counts three months of future disputes, so absolute rupee figures are scaled to exposure a real operator could not yet have measured. Recorded in `05_censoring_audit.csv` and surfaced in the app header, not buried.
2. **Rupee figures are a floor.** The model under-predicts in decile 9 by +1.15pp (3.93% predicted vs 5.08% observed), so the expected-cost calculation understates savings exactly where the policy operates. This errs safe, but it is a property of the number, not a disclaimer.
3. **Sensitivity CSV reading trap.** Raising `ops_review_cost` appears to increase savings because it also raises the do-nothing baseline. Mitigated in-app with an inline warning and a total-cost readout; the CSV itself still requires the caveat to read correctly. Open in `blockers.md`.
4. **Stratified basis is ~11% low.** If Tab 3 falls back to the 5,000-row sample, inverse weights recover ₹10,73,068 against the true ₹11,99,620, because 83 sampled disputes stand in for 407. The app labels the curve as an estimate whenever that path is taken.
5. **No drift detection.** Nothing monitors whether the deployed thresholds still hold as the score distribution moves. Out of scope for this iteration and named as such.

---

## 13. Deployment view

**Current target:** Streamlit Community Cloud. Single process, artifacts read from the repository at local paths, no database, no message queue, no separate model-serving layer. At 120K rows and a 26-feature linear model, a database would add operational surface without adding capability.

**External dependencies:** exactly one, optional — the Anthropic API for reviewer notes. With no key present, the app is fully functional: score, queue, and economics all work offline.

**Boot sequence:** load artifacts (cached) → load model (cached) → assert contract → render, or fail closed with the specific mismatch printed.

**What would change for production, and what would not.** The offline/online seam would not move. What sits on either side of it would: `data/processed/` becomes a versioned model registry; raw CSV reads become a transaction event stream; the boot-time contract check becomes a deploy-time gate in CI; and a drift monitor is added against the threshold assumptions in §12.5. The economics layer — which depends on no model internals — is the piece that would need the least change.

---

## 14. Extension points

| Want to change | Touch | Do **not** touch |
|---|---|---|
| The model | NB04 + re-export `04_feature_columns.csv`, `04_model_card.csv`, `04_model_coefficients.csv` | `economics.py` — it consumes tuples, not models |
| The cost assumptions | `05_economics_params.csv`, or the sliders live | the model, the features |
| The band count | `economics.py::optimise_bands`, `scoring.py::recommend_action*` | the notebooks' export shapes |
| A new feature | The knowability contract **first**, then NB03, then `scoring.py::build_instant_features` (both, or the contract check fails at boot) | the app's tabs |
| The explanation copy | `explain.py::SYSTEM_PROMPT` / `template_note` | anything in the scoring path |

The rule underneath all five rows: **the knowability contract and the feature column list are the two files that must never be edited alone.** Everything else in this system is recoverable from a re-run; those two, edited in isolation, produce a system that scores confidently and wrongly.
