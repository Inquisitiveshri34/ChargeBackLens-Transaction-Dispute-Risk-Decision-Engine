# METRICS.md — every number, and where it comes from

**Project:** ChargebackLens · Razorpay AI Buildathon, Track 02
**Companion documents:** `SCOPE.md` (what is and isn't claimed), `FAILURES.md` (what broke and what it cost), `README.md` (how to reproduce)
**Environment:** `scikit-learn 1.7.2`, `plotly 5.24.1`, `RANDOM_SEED = 42`

**The rule this document follows:** every figure below traces to a specific cell in a specific exported CSV. Nothing is typed from memory, rounded for effect, or reconstructed from a draft. Section 10 is the traceability index — it maps each headline number to the file it was read from, so any claim here can be checked without re-running a notebook.

**Read §7 before quoting any rupee figure.** Four caveats apply to the economics, all of them measured, all of them exported. They are not disclaimers bolted on at the end; they change how the numbers should be read.

---

## 1. The one-screen summary

| | |
|---|---|
| **Deployed model** | Unweighted `LogisticRegression`, 26 features, with a prefit sigmoid calibrator |
| **Test PR-AUC** | **0.0872** against a 0.8995% base rate — **9.7× the base rate** |
| **Lift at the top 1% of the queue** | **16.2×** — 66 disputes caught in 452 reviewed |
| **Precision / recall at the top 5%** | **7.78% / 43.2%** |
| **Brier skill score** vs. a constant base-rate predictor | **+3.90%** |
| **Expected calibration error** | **0.00185** across ten deciles |
| **Cost of allowing every transaction** | **₹30,69,547** |
| **Net savings under the deployed policy** | **₹11,99,620** — 39.1% of that exposure |
| **Operating thresholds** | allow/step-up **0.02443** · step-up/review **0.08240** |
| **Segments where manual review loses money** | **1** — `method = wallet`, at −₹300 |
| **Share of test positives raised after the snapshot** | **72.2%** — the project's largest caveat (§7.1) |

---

## 2. Data quality

Source: `01_data_quality_log.csv` (20 rows × 6 cols), `data_cleaning_merging.md`

| | |
|---|---|
| Raw inputs | transactions 120,000 · customers 35,000 · merchants 60 · fulfilment 66,140 · disputes 1,091 |
| Master table | **119,988 × 24** (120,000 raw − 12 duplicate `payment_id` rows) |
| Positive class | **1,050** disputes |
| **Base dispute rate** | **0.8751%** — inside the spec's declared 0.8–1.0% band |
| Quality checks failing their expected count | **0 of 20** |
| Leakage tripwire on the master table | clean — zero forbidden columns present |

**Fourteen cleaning rules were applied, each with a found-vs-expected count.** The notable ones:

| Issue | Rows | Handling |
|---|---:|---|
| Non-standard `ip_state` strings | 360 | normalised to 2-letter codes — 110 distinct values collapsed to 36 |
| `delivered_at` earlier than `shipped_at` | 790 | both timestamps nulled, row kept and flagged |
| `delivered` with a null `delivered_at` | 330 | flagged, not repaired |
| Empty `device_id` | 60 | field set to `NA`, **row kept** — a customer with a missing device has one fewer known device, not one fewer transaction |
| Empty `email_domain_type` | 15 | set to `"unknown"` as an explicit fourth category, never folded into a real one |
| `raised_at` earlier than `created_at` | 12 | timestamp nulled, **dispute still counts for the label** |
| Non-positive `amount` | 8 | flagged `exclude_from_modelling`, row kept with its `payment_id` printed |
| Out-of-window `created_at` | 3 | flagged (2019-06-09, 2099-03-17, 2099-11-02) |

**Orphan foreign keys**, which the data spec designs in deliberately: 140 orphan `fulfilment` rows and 35 orphan `disputes` rows logged, dropped, and their counts asserted against the spec.

**One specification error found and reported rather than absorbed.** The data spec states that `issuer_bank` has 62,400 nulls. The file actually has **63,600** — exactly `upi (52,800) + wallet (10,800)`. The structural rule (null on every UPI and wallet row) holds perfectly; the spec's arithmetic does not. Validating the rule instead of the count is what let this pass honestly. The spec line should be corrected.

---

## 3. The dataset and the split

Sources: `03_feature_matrix.csv`, `03_train.csv`, `03_test.csv`, `03_feature_knowability.csv`

| | Rows | Positives | Rate |
|---|---:|---:|---:|
| Working set (after 11 flagged exclusions) | 119,977 | 1,050 | 0.8752% |
| **Train** (`created_at` < 2026-08-01) | 74,731 | 643 | 0.8604% |
| **Test** (`created_at` ≥ 2026-08-01) | 45,246 | 407 | 0.8995% |

Within train, three further disjoint temporal blocks were used so that no selection decision touched the test set:

| Block | Rows | Window | Positives | Rate |
|---|---:|---|---:|---:|
| FIT | 59,784 | 2026-01-01 → 2026-06-24 | 515 | 0.8614% |
| CAL / VAL | 14,947 | 2026-06-24 → 2026-07-31 | 128 | 0.8564% |
| TEST | 45,246 | 2026-08-01 → 2026-10-31 | 407 | 0.8995% |

**Every model was fitted on FIT. Every selection decision — hyperparameters, model class, calibration method, feature importances — was made on CAL/VAL. TEST was read in exactly one cell, after everything was decided.**

128 validation positives is thin, and the selection rule was built around that fact rather than in spite of it: it leans on a paired bootstrap, not on a fourth decimal place (§5.3).

**Class imbalance: 113:1.** 118,927 negatives against 1,050 positives. This is the number that rules out accuracy as a metric — predicting "never disputed" scores 99.1% — and that justifies reporting PR-AUC and precision@k instead of ROC-AUC.

**On the temporal split, stated honestly.** The weekly dispute-rate series shows no strong monotonic drift, and the two split rates (0.8604% / 0.8995%) are close. The temporal split is therefore justified as a **methodological precaution** against future-to-past leakage, not as a response to observed drift in this dataset. Overstating it would be dishonest.

---

## 4. The feature contract

Source: `03_feature_knowability.csv` (46 rows × 5 cols), written **before the first feature was built**

| `model_role` | Count | What it is |
|---|---:|---|
| `numeric` | 23 | fitted |
| `categorical` | 3 | fitted — `method`, `merchant_category`, `email_domain_type` |
| `meta` | 3 | `payment_id`, `created_at`, `amount` — carried for traceability, never fitted |
| `label` | 1 | `is_disputed` |
| `excluded` | 16 | 12 tagged `forbidden` + 4 available but deliberately unused |

**Fitted width: 26 features.** Derived from this artifact's `model_role` column, never hand-typed.

### 4.1 Verification that the contract held

| Check | Result |
|---|---|
| Forbidden columns present in `03_feature_matrix.csv` | **0** |
| NaNs in the feature matrix | **0** |
| Declared contract vs. built columns | **exact match** |
| `03_train.csv` + `03_test.csv` = `03_feature_matrix.csv` | 74,731 + 45,246 = 119,977 ✓ |
| Time-gating tripwire | **passed** — 39 stale customers found, every gated value strictly below the ungated truth |

The tripwire deserves a sentence. The data spec plants 40 customers whose `prior_disputes` snapshot column is stale. The notebook found **39** — one short, consistent with notebook 1 having dropped 10 duplicate customers and 41 dispute rows. The assertion was deliberately written as `> 0` rather than `== 40`, because a hard equality would fail for a correct reason, and an assert that fails for correct reasons gets removed.

### 4.2 The signal that was refused

`delivery_status` shows a real, visible 3.1× spread:

| `delivery_status` | Dispute rate | Volume |
|---|---:|---:|
| lost | 2.68% | 1,979 |
| in_transit | 1.35% | 9,240 |
| returned | 1.30% | 3,300 |
| delivered | 0.86% | 51,474 |

It is tagged `forbidden` and asserted out of the feature matrix, because it is only knowable weeks after the moment a routing decision has to be made. `01_cleaned_fulfilment.csv` is never even loaded by notebook 3 — the cheapest possible enforcement is a file that is never opened.

---

## 5. Model performance

Source: `05_model_comparison.csv` (4 rows × 17 cols), cross-checked with `np.allclose` against `04_test_metrics.csv`

### 5.1 The four probability columns, side by side

| Column | What it is | PR-AUC | Lift@1% | P@5% | Brier | Brier skill | max p |
|---|---|---:|---:|---:|---:|---:|---:|
| `proba_baseline` | LR, `class_weight='balanced'` (as prescribed) | 0.0842 | 17.2× | 0.0769 | 0.1404 | **−14.75** | 0.991 |
| `proba_main` | HGB, tuned | 0.0812 | 15.5× | 0.0721 | 0.0086 | +0.0371 | 0.399 |
| `proba_selected` | LR, unweighted, uncalibrated | 0.0872 | 16.2× | 0.0778 | 0.0085 | +0.0426 | 0.474 |
| **`proba_calibrated`** | **the same LR + prefit sigmoid — deployed** | **0.0872** | **16.2×** | **0.0778** | **0.0086** | **+0.0390** | **0.334** |

Two things to read here.

**The last two rows have identical ranking metrics and different values.** That is the signature of a correct calibration — a strictly monotone map cannot change an ordering — and it is an explicit definition-of-done check rather than an observation made afterwards.

**The skill-score column is the one that matters.** A constant predictor emitting the test base rate scores a Brier of `r(1−r) = 0.008914`. The prescribed baseline's 0.1404 is therefore **fifteen times worse than predicting nothing at all**, while ranking transactions perfectly respectably. That single number is the most legible statement of the `class_weight` defect documented in `FAILURES.md` §2.

### 5.2 What the deployed model actually catches

| | Value |
|---|---|
| Test set | 45,246 transactions, 407 disputes (0.8995%) |
| PR-AUC | **0.0872** — 9.7× the base rate |
| Top 1% of the queue (452 transactions) | **66 disputes caught**, precision 14.60%, **16.2× lift** |
| Top 5% of the queue (2,262 transactions) | precision **7.78%**, recall **43.2%** |

Recall at 5% is the number a risk team feels: **reviewing 5% of volume surfaces 43% of the disputes.**

### 5.3 How the model was chosen

The selection rule was written down before it was applied:

1. Rank candidates by validation PR-AUC.
2. Bootstrap the paired gap between the leader and each rival, 500 resamples. If the 95% CI contains zero, the rival joins the **tie set**.
3. Break the tie on `(model-class simplicity, validation log-loss)`.

Five candidates were evaluated. **All five landed in the tie set** — with 128 validation positives, nothing separates on ranking. So the tie-break did the real work, and validation log-loss is what split the two logistic variants: **0.0437 unweighted against 0.4478 weighted**, for models that rank identically. `LR_plain` was selected.

Every configuration tried is exported to `04_hgb_search_results.csv` (16 rows) and `04_validation_leaderboard.csv` (5 rows), so the search is auditable rather than asserted.

**The honest claim is not "the linear model wins."** A paired bootstrap on test puts the tuned-HGB-minus-deployed gap at −0.0060, CI [−0.0168, +0.0060] — not significant in either direction. The claim is: *on 407 test positives nothing separates these models, so a rule fixed in advance picked the simpler and better-calibrated one, and it was picked before test was read.*

### 5.4 Why the signal in this dataset is additive

The hyperparameter search over 16 HGB configurations selected **4 leaf nodes and `min_samples_leaf=400`**. Asked how much tree it wanted, the search said barely any — that is a stump ensemble, very nearly an additive model.

Consistent with that, permutation importance ranks exactly the clean monotone spreads EDA found, with no interaction terms surfacing:

| Feature | Importance | ± | Clears 2σ? |
|---|---:|---:|---|
| `log_amount` | 0.03075 | 0.00389 | ✅ |
| `email_domain_type` | 0.02295 | 0.00282 | ✅ |
| `phone_verified` | 0.02243 | 0.00312 | ✅ |
| `merchant_category` | 0.01296 | 0.00183 | ✅ |
| `method` | 0.01097 | 0.00175 | ✅ |
| `has_prior_history` | 0.00307 | 0.00100 | ✅ |
| `amount_vs_merchant_avg_ratio` | 0.00265 | 0.00093 | ✅ |
| `delivery_sla_days_filled` | 0.00248 | 0.00105 | ✅ |

**Eight of 26 features clear the 2σ screen. Eighteen do not, and six score ≤ 0.** None were dropped — a feature that measures as worthless *and was predicted to* is a finding worth reporting, and retro-fitting the feature set to the importances would have destroyed it.

⚠️ **The app's reviewer note must filter on `informative == True`** before naming a driver, or it will confidently tell a reviewer that a shuffled-noise column drove the score.

### 5.5 The ticket-size confound, settled

EDA flagged that `emi` (2.44%), `netbanking` (1.45%) and `travel` (2.27%) all show elevated raw dispute rates — and that all three are high-ticket segments, so their rates might be `amount` wearing a category label. Shipping a logistic regression made this checkable:

| Term | Coefficient | Odds ratio |
|---|---:|---:|
| `merchant_category_edtech` | −1.688 | 0.185 |
| `email_domain_type_corporate` | −1.609 | 0.200 |
| `email_domain_type_personal` | −1.410 | 0.244 |
| `merchant_category_travel` | **−1.236** | 0.291 |
| `log_amount` | **+1.127** | 3.086 |
| `method_upi` | −1.006 | 0.366 |
| `method_emi` | **−0.836** | 0.434 |

**`travel` and `emi` both carry negative coefficients once `log_amount` is in the model.** Their raw rates were ticket size in disguise. This is the sharpest single observation in the modelling work.

*(Coefficients are on one-hot columns fitted with L2 with no reference level dropped, so read them as relative contributions within a family, not as standalone log-odds.)*

### 5.6 Six features measure as worthless, all of them explainable

`account_age_implausible` (constant at 0 rows — a passed assertion, not a feature), `day_of_week`, `prior_disputes_before_this_txn`, `amount_vs_own_avg`, `txns_last_24h` and `checkout_latency_ms` all score ≤ 0.

`ip_state_changed_from_prev_txn` scores **+0.000012 ± 0.000809** — rank 19 of 26, with a standard deviation sixty-seven times its mean, i.e. indistinguishable from a shuffled column. This was **predicted from first principles before the model was fitted**: the feature fires on 92.0% of rows conditional on having a prior transaction, against a ~93% expectation under independent draws. The generator assigns `ip_state` per transaction with no customer-level home state, so there is nothing to detect. It is a property of the synthetic data, not a modelling failure — on genuine payments data the feature would carry real signal.

---

## 6. Calibration

Source: `05_calibration_curve.csv` (20 rows × 7 cols), cross-checked to **exact** float equality against `04_reliability_bins.csv`

| Model | ECE | Worst decile gap |
|---|---:|---:|
| `main_hgb` (uncalibrated) | 0.00137 | +0.00795 |
| `calibrated` (deployed) | 0.00185 | **+0.01153** (decile 9) |

**Two things read honestly here, and both belong in the record.**

**First, nine of ten deciles track within ±0.0022.** The tenth does not: it predicts 3.93% against an observed 5.08%. The model **under-predicts exactly where the economics operates**, which makes every rupee figure below a floor rather than an estimate. The top-5% slice predicts 5.52% against an observed 7.78%.

**Second, the uncalibrated HGB has the *lower* ECE.** Sigmoid calibration slightly worsened aggregate reliability while preserving ranking exactly. So the defensible claim is not that calibration improved the model. It is that **calibration corrected the scale** — `max_proba` 0.474 → 0.334 — **at zero cost to ranking**. Say that, and not more.

The honest headline from the calibration-method selection is that sigmoid beat doing nothing at all by 0.00004 in log-loss: **an unweighted logistic regression is already calibrated**, and the fitted sigmoid is close to the identity map. Calibration here is a check that passed, not a step that rescued anything.

---

## 7. Economics — and the four things to read alongside every rupee figure

Source: `05_economics_params.csv`, `05_policy_bands.csv`, `05_threshold_sweep.csv`, `05_segment_economics.csv`, `05_sensitivity_analysis.csv`, `05_censoring_audit.csv`

### 7.0 The parameters and the cost model

| Parameter | Value |
|---|---:|
| `dispute_fee` | ₹1,500 |
| `ops_review_cost` | ₹300 |
| `merchant_margin` | 0.18 |
| `step_up_abandon_rate` | 0.25 |

The three-band cost model adds **no fifth parameter**:

| Action | If disputed | If not disputed |
|---|---|---|
| manual review | `ops_review_cost` | `ops_review_cost` |
| step-up | 0 — deterred at the 3DS prompt | `amount × margin × abandon_rate` |
| allow | `amount + dispute_fee + ops_review_cost` | 0 |

The single assumption added is that a step-up deters the disputing party. It is stated in the function's docstring rather than buried. Adding a separate step-up prevention rate would have been more realistic and less auditable, and the sensitivity analysis already shows where the uncertainty concentrates.

### 7.1 The headline, with its caveats attached

| | Value |
|---|---:|
| Cost of allowing everything (the do-nothing baseline) | **₹30,69,547** |
| Net savings under the deployed three-band policy | **₹11,99,620** |
| As a share of exposure | **39.1%** |

**Caveat 1 — 72.2% of the label is post-snapshot.** `05_censoring_audit.csv`: **294 of 407 test positives were raised after the 2026-11-01 snapshot**, with the latest at 2027-01-26. Nearly three-quarters of the disputes this policy is scored against would not have been observable to an operator standing on the snapshot date. This does **not** bias the ranking — every feature is time-gated and the tripwire passed — but the label counts three months of future disputes, so the absolute rupee figures are scaled to an exposure a real merchant could not yet have measured. This is the largest single caveat in the project and it belongs here, next to the first rupee figure, not in a footnote.

**Caveat 2 — the number is a floor.** Per §6, the deployed model under-predicts in decile 9 by 1.15pp, so the expected-cost calculation understates the savings from flagging at high thresholds. This errs in the safe direction — a model over-predicting at the top would be the dangerous one — but it is a property of the number, not a disclaimer about it.

**Caveat 3 — the conclusion is robust, the operating point is not.** See §7.4.

**Caveat 4 — one band of one segment loses money.** See §7.5.

### 7.2 The deployed policy

Source: `05_policy_bands.csv`

| Band | Range on `proba_calibrated` | n | Share | Disputes | Rate in band | Lift |
|---|---|---:|---:|---:|---:|---:|
| allow | < 0.02443 | 42,152 | 93.2% | 204 | 0.484% | 0.54× |
| step-up | 0.02443 – 0.08240 | 2,786 | 6.2% | 151 | 5.42% | **6.03×** |
| manual review | ≥ 0.08240 | 308 | 0.7% | 52 | 16.88% | **18.77×** |

**The policy's cost, stated in customers rather than rupees.** At the allow/step-up threshold of 0.02443, the confusion matrix reads 41,948 TN · 2,891 FP · 204 FN · 203 TP — precision 6.56%, recall 49.88%. In plain language: **2,891 legitimate customers see friction in order to catch 203 disputes.** That is the honest framing of what a 6.2% step-up band means.

### 7.3 Two thresholds beat one, measurably

| | Binary (one threshold) | Three-band (two thresholds) |
|---|---:|---:|
| Net savings | ₹10,80,993 | **₹11,99,620** |
| Delta | — | **+₹1,18,627** |

The binary optimum sits at threshold 0.02405, flagging 3,168 transactions (7.00%) at 6.44% precision and 50.12% recall. **The curve is flat between roughly 0.024 and 0.042 — the argmax is not a precise point and should not be presented as one.**

That ₹1,18,627 is the concrete justification for the three-band design, which until it was measured was an argument from how risk teams operate rather than a demonstrated gain.

### 7.4 Sensitivity — four parameters swept, not one

On `step_up_abandon_rate`, the parameter that matters most:

| `step_up_abandon_rate` | allow/step-up cut | step-up/review cut | n review | n step-up | Net savings |
|---:|---:|---:|---:|---:|---:|
| 0.10 | 0.01429 | 0.14601 | 41 | 6,255 | ₹18,11,639 |
| 0.20 | 0.02434 | 0.11350 | 108 | 3,004 | ₹13,33,030 |
| **0.25** | **0.02443** | **0.08240** | **308** | **2,786** | **₹11,99,620** |
| 0.30 | 0.04400 | 0.05388 | 794 | 428 | ₹10,98,732 |
| 0.40 | 0.04441 | 0.04496 | 1,164 | 33 | ₹10,87,874 |

**Net savings stay positive across the whole range** (₹10.9L–₹18.1L, a 1.7× spread) — the conclusion survives. **But the allow/step-up cut moves 0.0143 → 0.0444, a factor of 3.1.** As friction becomes more expensive, the policy shifts from mass step-up (6,255 transactions at rate 0.10) to targeted review (1,164 at rate 0.35): the two bands trade places.

**`step_up_abandon_rate` is the one parameter a merchant must measure rather than assume.** It is also the single highest-value measurement available to anyone deploying this.

⚠️ **A reading trap in `05_sensitivity_analysis.csv` that is not obvious from the table.** `dispute_fee` and `ops_review_cost` both appear inside `fn_cost = amount + dispute_fee + ops_review_cost`, so raising either also raises the **do-nothing baseline that net savings is measured against**. Their net-savings columns therefore rise even where the policy gets worse. At `ops_review_cost = 800` the net saving reads ₹12,69,369 against ₹11,99,620 at ₹300 — but the actual total cost rose by ₹1,33,751; the baseline simply rose by ₹2,03,500 more.

> **Net savings are comparable across `merchant_margin` and `step_up_abandon_rate` rows, and are *not* comparable across `dispute_fee` or `ops_review_cost` rows.** For those two, compare total cost or hold the baseline fixed.

Anyone reading that CSV without this note will conclude that paying reviewers more saves money.

### 7.5 Segment economics — where this should not be deployed

Source: `05_segment_economics.csv` (15 segments across amount bucket, merchant category and payment method, all above `MIN_SEGMENT_N = 300`)

A methodological point makes this finding real. Optimising a threshold *within* each segment guarantees a non-negative answer everywhere, because the do-nothing threshold is always in the grid — **that column alone cannot identify a bad segment.** So each segment is also evaluated at the **single global policy that would actually ship**, decomposed into its review and step-up halves, because a segment can be profitable overall while its review band loses money.

Sorted by return per intervention:

| Segment | n | Mean amount | Savings per intervention | Review band net | n review |
|---|---:|---:|---:|---:|---:|
| `method = wallet` | 4,063 | ₹676 | ₹47 | **−₹300** | 1 |
| `merchant_category = ticketing` | 4,561 | ₹825 | ₹50 | ₹1,890 | 25 |
| `amount < ₹500` | 15,434 | ₹262 | ₹78 | ₹3,280 | 4 |
| `merchant_category = gaming` | 9,050 | ₹380 | ₹114 | ₹23,411 | 28 |
| … | | | | | |
| `merchant_category = travel` | 4,529 | ₹12,155 | ₹1,094 | ₹4,55,369 | 163 |
| `method = emi` | 1,856 | ₹13,966 | ₹1,294 | ₹2,06,358 | 57 |
| `amount > ₹10,000` | 2,288 | ₹18,859 | ₹1,434 | ₹4,17,582 | 128 |

**The finding, stated precisely.** Manual review on `wallet` traffic nets **−₹300** — one review, zero catches. Meanwhile `amount > ₹10,000` returns **₹1,434 per intervention, 31× wallet's ₹47**.

**And the recommendation that follows is sharper than "don't deploy on wallet."** Wallet's *step-up* band earns ₹9,779 — the friction pays for itself there; the human reviewer does not. So:

> **Route the review queue by ticket size. On wallet and sub-₹500 traffic, keep the step-up band and skip manual review entirely.**

That is the same ticket-size axis the EDA predicted the finding would land on, now measured rather than expected.

---

## 8. What is deliberately not reported

**ROC-AUC.** All four probability columns score around 0.83, against PR-AUCs around 0.087. At a 0.8995% base rate, ROC-AUC is dominated by the 44,839-row true-negative mass and stays misleadingly high for a mediocre model. It was computed, printed once in a side cell with that one-line reason, and **not exported to any CSV** — notebook 4 enforced the same decision mechanically by naming its column `roc_auc_DIAGNOSTIC_ONLY`. It is absent from this document on purpose.

**Accuracy.** At 113:1, predicting "never disputed" scores 99.1%. The metric carries no information here.

**Train-set performance as a result.** `04_train_predictions.csv` exists to measure the train/test **gap**, never to be reported as a result:

| | Train PR-AUC | Test PR-AUC | Ratio |
|---|---:|---:|---:|
| `proba_baseline` | 0.0668 | 0.0842 | 0.79 |
| `proba_main` (tuned HGB) | 0.1055 | 0.0812 | **1.30** |
| `proba_calibrated` (deployed) | 0.0705 | 0.0872 | 0.81 |

The *prescribed* HGB's ratio was **9.9** before it was retuned (`FAILURES.md` §1). At 1.30 the tuned version generalises; the deployed linear model sits at 0.81, scoring better on test than train, which at these positive counts is sampling noise plus a slightly higher test base rate.

---

## 9. Known limitations

1. **The data is synthetic**, and at least two findings are properties of the generator rather than of Indian payments: `ip_state` carries no customer-level home state (§5.6), and dispute labels were assigned without modelling a censoring horizon (§7.1).
2. **72.2% of test positives are post-snapshot** — the single largest caveat, restated here so it appears in both places a reader might look.
3. **128 validation positives** is a thin basis for model selection, which is why the selection rule uses a bootstrap tie set rather than raw ranking.
4. **The economics assume a step-up deters the disputing party.** This is the one un-derived assumption in the cost model.
5. **`account_age_implausible` fires on zero rows.** It is a passed assertion carried in the matrix as evidence the check ran, not a feature.
6. **The app's review-queue sample is stratified, not random.** `05_scored_test_sample.csv` retains all 308 `manual_review` rows plus a seeded draw of 4,692 others (4,406 allow · 286 step-up · 308 review · 83 disputes). A uniform 5,000-row draw at a 0.9% base rate would have contained roughly 34 reviewable rows and made the demo queue look empty. **The sample's dispute rate is not the population rate and the app must not quote it as one** — it reweights by inverse sampling weight to present population-scale figures.
7. **Two figures quoted in project documentation are computed outside a notebook cell** — the train/test gap table in §8 and the fitted `C` value. Both are traceable to exported CSVs but neither has a printing cell, which is a gap against the project's own traceability rule.

---

## 10. Traceability index

Every headline number in this document, mapped to the artifact it was read from.

| Number | Value | Source file |
|---|---|---|
| Base dispute rate | 0.8751% | `01_data_quality_log.csv`, `01_master_labelled.csv` |
| Data-quality checks passing | 20 of 20 | `01_data_quality_log.csv` |
| Class imbalance | 113:1 | `02_eda_segment_summary.csv` |
| Segment dispute rates | see §5.5 | `02_eda_segment_summary.csv` (64 rows) |
| Feature contract | 46 rows, 26 fitted | `03_feature_knowability.csv` |
| Train / test rows and rates | 74,731 / 45,246 | `03_train.csv`, `03_test.csv` |
| Hyperparameter search | 16 configs | `04_hgb_search_results.csv` |
| Model selection evidence | 5 candidates | `04_validation_leaderboard.csv` |
| Deployed model identity | `LR_plain` + sigmoid | `04_model_card.csv` |
| Permutation importances | 26 rows, 2σ flag | `04_feature_importances.csv` |
| Coefficients and odds ratios | 38 terms | `04_model_coefficients.csv` |
| Fitted column order | 26 rows | `04_feature_columns.csv` |
| PR-AUC, lift, Brier, skill score | see §5.1 | `05_model_comparison.csv` |
| ECE and decile reliability | 0.00185 | `05_calibration_curve.csv` |
| Threshold sweep, binary optimum | ₹10,80,993 | `05_threshold_sweep.csv` (101 rows) |
| Operating thresholds and params | 0.02443 / 0.08240 | `05_economics_params.csv` |
| **The deployed policy and its ₹11,99,620** | see §7.2 | **`05_policy_bands.csv`** |
| Sensitivity across four parameters | 22 rows | `05_sensitivity_analysis.csv` |
| Segment economics, wallet finding | −₹300 | `05_segment_economics.csv` |
| Censoring audit | 294 / 407 | `05_censoring_audit.csv` |
| App review-queue sample | 5,000 rows | `05_scored_test_sample.csv` |
