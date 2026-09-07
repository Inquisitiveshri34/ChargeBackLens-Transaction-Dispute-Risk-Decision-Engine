# FAILURES.md — what broke, what caused it, and what it cost

**Project:** ChargebackLens · Razorpay AI Buildathon, Track 02
**Full log:** `blockers.md` keeps every blocker, including the five-minute ones. This document carries the entries that have real before/after numbers and a lesson that generalises.

Nine blockers were logged during this build. Three of them would have shipped a wrong number without raising a single error, and those three are documented in full below. The rest are summarised in §6.

**The pattern worth naming up front:** the failures that raised exceptions cost minutes. The failures that ran cleanly and produced plausible-looking numbers were the expensive ones. Every one of the three headline entries below belongs to the second category, and every one was caught by a metric table rather than by a traceback.

---

## 1. The prescribed main model lost to its own baseline

**Where:** `04_model_building.ipynb` · **Severity:** High — this blocked the definition of done for the entire evaluation notebook · **Status:** Resolved; notebook 4 rebuilt around the finding

### What was observed

The notebook ran clean. All six definition-of-done checks passed. Then the directional print at the end read:

```
PR-AUC baseline → main : 0.0839 → 0.0517 (⚠️ DOES NOT IMPROVE)
```

The gradient-boosted model that the design documents specified as the *main* model scored below the logistic regression specified as its *baseline*.

| | Train PR-AUC | Test PR-AUC | Ratio |
|---|---:|---:|---:|
| baseline (`LogisticRegression`) | 0.0667 | **0.0839** | 0.79 — generalises |
| main (`HistGradientBoostingClassifier`) | 0.5130 | 0.0517 | **9.9 — memorises** |

A train/test ratio of 9.9 is not a subtle overfit. It is a model that has memorised its training set.

### Root cause — two halves, and the second is the interesting one

**Capacity was set without reference to the positive count.** `max_depth=6`, 300 iterations, scikit-learn's default `min_samples_leaf=20`, no L2 regularisation, `early_stopping=False` — on **643 training positives in 74,731 rows**, with `class_weight='balanced'` making each positive worth roughly 116 negatives. A depth-6 tree can isolate individual reweighted positives into their own leaves and be rewarded for doing so. Those hyperparameters came from a design document written **before the split's positive count was known**.

**And there is very little interaction structure in this data to exploit.** The top features by permutation importance are `phone_verified` (0.0224), `email_domain_type` (0.0230) and `log_amount` (0.0308) — precisely the clean, large, monotone spreads the EDA found. The velocity features are thin (`txns_last_24h` non-zero on 2.5% of rows, `prior_disputes_before_this_txn` on 1.9%). The generator built dispute probability from a handful of marginal effects and no interactions. So there was plenty of room for a boosted ensemble to overfit and almost nothing for it to gain.

### The fix — two responses, executed in order

**Response 1: a capacity sweep. It worked.** A 16-configuration randomised search over `learning_rate`, `max_leaf_nodes`, `min_samples_leaf`, `l2_regularization` and `max_features`, scored with `TimeSeriesSplit(n_splits=4)` inside the fit block, with `early_stopping=True` replacing the fixed 300 iterations.

**The search's own answer is the diagnosis restated: it selected 4 leaf nodes and `min_samples_leaf=400`.** Asked how much tree it wanted, it said barely any.

| HGB configuration | Train PR-AUC | Test PR-AUC | Ratio |
|---|---:|---:|---:|
| prescribed (`max_depth=6`, 300 iters, balanced) | 0.5130 | 0.0517 | **9.9** |
| tuned (4 leaves, `min_samples_leaf=400`, early stopping) | 0.1055 | **0.0812** | **1.30** |

**Test PR-AUC improved 0.0517 → 0.0812, a 57% gain, entirely from removing capacity.**

**Response 2: it still lost, so the simpler model ships.** At 0.0812 the tuned HGB remains below the unweighted logistic regression at **0.0872**. Selection was made on the validation block, before test was read, under a rule written down in advance (rank by validation PR-AUC → bootstrap tie set → break on model-class simplicity and log-loss). All five candidates landed in the tie set — with 128 validation positives, nothing separates — and the tie-break selected the logistic regression.

| Test | PR-AUC | Lift@1% | P@5% | Brier |
|---|---:|---:|---:|---:|
| prescribed baseline (LR balanced) | 0.0842 | 17.2× | 0.0769 | 0.1404 |
| tuned HGB | 0.0812 | 15.5× | 0.0721 | 0.0086 |
| **deployed (LR + sigmoid)** | **0.0872** | **16.2×** | **0.0778** | **0.0086** |

### What was rejected, and why

- **Tuning against the test set.** The fast fix, and it would have invalidated every number in `METRICS.md`. The entire temporal-split argument exists to prevent exactly this.
- **Reporting the HGB as the model anyway** and hoping the comparison table obscured it. Dishonest, and the required side-by-side table would have exposed it immediately.
- **Dropping the baseline from the report** so nothing contradicted the main model. Worse. The stated reason for fitting three models in sequence is that *a single model presented alone is a claim, while three models compared side-by-side is evidence*. The evidence came back inconvenient — that is what evidence does.

### What it cost, and what it saved

The diagnosis took one table. The fix cost a full rebuild of notebook 4 — a three-way temporal split, a hyperparameter search, a written selection rule, and a re-export of every artifact — plus the invalidation of every number in the superseded documentation. The search itself runs in 68 seconds; the design work around it was the expense.

**Nothing downstream was corrupted, because nothing downstream had been built yet.** Had this surfaced during the economics notebook instead, the threshold sweep, sensitivity analysis and every figure in `METRICS.md` would have been written against a model that was about to be replaced.

### The lesson

**A directional check that fails is a finding, not an error.** This was deliberately implemented as a *printed warning* rather than an `assert`, because the notebook's own definition of done — models fit, reload, and score — was met. Halting there would have hidden the most informative result in the project.

The stronger version: **the result is that a document prescribed three modelling choices, all three were measured, all three were wrong on this data, and the replacement was a *simpler* model than the one specified.** That is a better outcome to report than a tuned ensemble would have been.

---

## 2. `class_weight='balanced'` made the probabilities unusable — and raised no error

**Where:** `04_model_building.ipynb`, with the consequence landing in the economics layer · **Severity:** High — would have silently inflated every rupee figure in the submission · **Status:** Resolved

### What was observed

Nothing. No exception, no warning, no failed assertion.

The prescribed baseline scored a perfectly respectable test PR-AUC of **0.0842**. It also scored a Brier of **0.1404** against a test base rate of 0.8995%, with a maximum predicted probability of **0.9913**.

A constant predictor that always outputs the base rate scores a Brier of `r(1−r) = 0.008914`.

**The prescribed baseline was therefore fifteen times worse than predicting nothing at all — while ranking transactions well.** Expressed as a skill score against that reference: **−14.75**.

### Root cause

`class_weight='balanced'` reweights each positive by roughly 116× (the inverse class frequency). That is a legitimate technique for keeping a rare class from being ignored by the loss, and the EDA justified it correctly from the 113:1 imbalance.

But **logistic regression fits probabilities, and reweighting the loss shifts the fitted intercept.** The model learns the conditional probability of the *reweighted* population, in which disputes are ~50% of the mass, not the real one where they are 0.9%.

The output is a monotone transform of the right answer. So:

- **every ranking metric is unaffected** — PR-AUC, precision@k, and the review queue all look fine;
- **every magnitude is roughly 50× too large.**

And the economics layer multiplies a probability by a rupee amount. Multiply by 0.4 instead of 0.008 and the sweep reports savings that do not exist, in every chart, with no error anywhere.

### The fix

The escalation grid fitted both `class_weight=None` and `class_weight='balanced'` across six values of `C`, and the selection rule's tie-break is validation **log-loss** — a proper scoring rule, which is precisely the thing that separates two models with near-identical rankings and wildly different scales:

```
LR_weighted   val_pr_auc 0.05408   val_brier 0.1412   val_log_loss 0.4478
LR_plain      val_pr_auc 0.05257   val_brier 0.0083   val_log_loss 0.0437
```

The two rank the same to within bootstrap noise (gap +0.0017, CI [−0.0020, +0.0060]). The tie-break selected `LR_plain`, whose raw Brier of 0.008335 already beats the constant-rate reference **before any calibration is applied**.

| | Prescribed baseline | Deployed |
|---|---:|---:|
| Test PR-AUC | 0.0842 | **0.0872** |
| Brier | 0.1404 | **0.008567** |
| Brier skill score | **−14.75** | **+0.039** |
| max predicted probability | 0.991 | **0.334** |

### What was rejected, and why

- **Keep `balanced` and calibrate it away.** This works — a sigmoid recovers the scale — but it means applying a transform to undo a transform applied for no benefit. The weighted model bought zero ranking improvement here.
- **Keep `balanced` and only ever use ranks downstream.** This would gut the project. The three-band decision and the entire economics layer exist *because* the probability is a probability.

### The lesson

**`max_proba` is the cheapest tell in the whole pipeline.** A model whose maximum output is 0.99 on a 0.9%-base-rate problem is reporting on a different population than the one it will be deployed against. The evaluation function now reports `brier`, `log_loss` and `max_proba` on **every** model, always, and one definition-of-done check is `deployed Brier ≤ prescribed-baseline Brier`.

**Same failure surface, worth naming explicitly:** SMOTE, random undersampling, and `scale_pos_weight` in XGBoost all distort the base rate the same way and all leave ranking metrics untouched. If any of them is tried in a later iteration, calibrate before the economics layer touches the output — or don't use them.

**Cost:** no time lost — this was found by the metric table, not by debugging. The cost *avoided* is the real number: the threshold sweep, sensitivity analysis and segment economics would all have run without error against probabilities inflated ~50×.

---

## 3. The prescribed calibration destroyed 10% of the ranking

**Where:** `04_model_building.ipynb`, calibration-method selection · **Severity:** Medium — would have cost ~10% of PR-AUC in exchange for nothing · **Status:** Resolved

### What was observed

The design document specified `CalibratedClassifierCV(estimator=fitted_pipeline, method='isotonic', cv=3)`. Fitted that way and measured on the validation block:

```
   method  val_pr_auc  val_brier  val_log_loss
  sigmoid    0.048567   0.008351      0.044070
none(raw)    0.048567   0.008330      0.044111
 isotonic    0.043765   0.008367      0.048669
```

**Isotonic loses 10% of PR-AUC and is the worst of the three on log-loss.** Calibration was supposed to change the scale, not the ranking.

### Root cause — three separate problems in one prescribed call

**Isotonic regression is a step function.** It fits a piecewise-constant non-decreasing map, so scores that were distinct on either side of a step come out **identical**. Every collapsed tie is a ranking decision destroyed, and at the top of a queue sorted by probability, that is exactly where the decisions matter. The stated reason for choosing isotonic — ">500 positives, enough for a stable non-parametric fit" — counts positives across the whole training set, but an isotonic fit on a 0.9% problem is really estimating a handful of interior knots from the few hundred positives that land in the upper bins.

**`cv=3` is not a calibration wrapper — it is an ensemble.** With an integer `cv`, `CalibratedClassifierCV` refits the base estimator on each fold and averages three calibrated fold-models' predictions. The output is not "your model, rescaled"; it is a three-model ensemble whose ranking differs from the original for reasons that have nothing to do with calibration.

That also means the specified sanity check — "`proba_calibrated` is not identical to `proba_main`" — **would have passed for the wrong reason.** It would pass even if the calibration map were the identity.

**And `cv=3` shuffles across time.** A fold model trained on July gets calibrated against February. Everything else in this project is split by date specifically to avoid that.

### The fix

Prefit calibration on a held-out temporal block: fit the model on the FIT block (Jan–24 Jun), fit a **single** sigmoid map on the CAL block (24 Jun–31 Jul), never shuffle across the boundary.

```python
from sklearn.frozen import FrozenEstimator
CalibratedClassifierCV(FrozenEstimator(estimator), method="sigmoid").fit(X_cal, y_cal)
```

One model, one strictly-monotone map, so **PR-AUC and precision@k are invariant by construction** — confirmed on test at 0.087248 for both the uncalibrated and calibrated columns, identical to six decimal places, while `max_proba` moves 0.474 → 0.334.

That invariance is now a definition-of-done check in its own right: *ranking preserved through calibration*. It is a strictly better check than the specified one, because it can only pass for the right reason.

The method was not assumed either — sigmoid, isotonic, and no calibration at all were fitted on an inner split of the fit block, scored on validation, and picked by log-loss.

### The uncomfortable finding, reported anyway

**Sigmoid won by 0.00004 in log-loss over doing nothing at all.**

The honest reading is that **an unweighted logistic regression is already calibrated**, and the fitted sigmoid is close to the identity map. Calibration here is a check that passed, not a step that rescued anything.

Two consequences that are stated in `METRICS.md` rather than smoothed over:

- The uncalibrated HGB actually has a *lower* ECE (0.00137) than the deployed model (0.00185). The defensible claim is that calibration corrected the **scale** at zero cost to ranking, not that it improved reliability.
- On test, the raw selected model's Brier (0.008535) is fractionally **better** than its calibrated version's (0.008567). Noise — but it makes a bare "calibration improved Brier" sentence false as written, so the claim always names which comparison it means.

### The lesson

**A calibration method asserted rather than measured is the same mistake as a hyperparameter set without reference to the data.** The three-way comparison cell stays in the notebook permanently.

---

## 4. Two-thirds of the specified threshold grid was empty

**Where:** `05_model_evaluation.ipynb`, threshold sweep · **Severity:** Medium — caught before it produced a wrong number, because it was predicted in advance · **Status:** Resolved

This one is included because it is the clearest example of the project's most useful habit: **naming a likely failure before it fires, so the diagnosis starts from a hypothesis instead of a blank page.**

The blockers log carried an entry flagging this as "the single most likely way notebook 5 produces a confidently wrong number," written before the sweep ran. The measurement confirmed it exactly:

> **67 of the 100 points** in the specified `np.linspace(0.01, 0.99, 100)` grid flag **zero transactions**, because the deployed model's maximum test probability is 0.3344.

Two-thirds of the sweep would have been a flat line sitting at the do-nothing baseline, and the reported "optimal threshold" would have been wherever that plateau began — **an artifact of the grid, not a decision.** It would have produced a number, a chart, and no error.

**Fixed** by drawing 101 points from **quantiles of the score** instead, which puts every grid point where transactions actually are and gives the top of the distribution the resolution the decision needs. The definition of done now asserts `(threshold_sweep_df["n_flagged"] > 0).all()`, so an empty grid point can never reach an export again.

**Same root cause, one section over.** The specified interim confusion matrix at threshold 0.5 was equally uninformative — and in a more interesting way than predicted:

```
at threshold 0.5:
  proba_baseline       predicted positives: 8736
  proba_main           predicted positives: 0
  proba_selected       predicted positives: 0
  proba_calibrated     predicted positives: 0
```

Three of four columns predict nothing. The fourth predicts 8,736 — 19.3% of the test set at 3.3% precision — because of the `class_weight` scale inflation from §2. **So 0.5 is uninformative for the deployed model and actively misleading for the baseline, in opposite directions.** Reported instead at the operating threshold of 0.02443, where it says something worth saying: 2,891 legitimate customers see friction to catch 203 disputes.

---

## 5. Two failures of specification against reality

Both were caught at declaration time rather than at fit time, and both illustrate the same discipline: **check a specified thing against the artifact that would have to support it, before building on it.**

### 5.1 A specified feature that could not exist

`ip_billing_state_mismatch` appears in three separate design documents. **It is not computable.** No table in the dataset carries a billing state — `transactions` has `ip_state` only, `customers` has no geography column at all, and `merchants` has none. The feature was specified against a schema that was never generated, and three documents carried it forward without anyone checking it against the data spec's column lists.

**Substituted** with `ip_state_changed_from_prev_txn`, computable from `transactions` alone and leakage-safe under the same trailing discipline as the other velocity features. Synthesising a billing state was rejected outright — that would have meant writing to `data/raw/`, which the architecture forbids.

**And the substitute turned out to be uninformative, which is itself the finding.** It fires on 92.0% of rows conditional on having a prior transaction, against a ~93% expectation under independent draws. Permutation importance: **+0.000012 ± 0.000809** — rank 19 of 26, with a standard deviation sixty-seven times its mean. Not merely small: indistinguishable from a shuffled column.

The cause is a property of the generator, not a modelling failure. **`ip_state` is assigned per transaction with no customer-level home state**, so there is nothing for the feature to detect. On genuine payments data it would carry real signal.

**What made this cheap:** notebook 3 writes the feature contract to disk *before building anything*. The impossibility surfaced when the contract was declared, not three notebooks later.

### 5.2 A method the estimator has never had

```
AttributeError: 'HistGradientBoostingClassifier' object has no attribute 'feature_importances_'
```

on the exact line two design documents instruct. Not a version issue and not a fitting issue — **the attribute has never existed on this estimator.** `feature_importances_` is exposed by the tree ensembles built on scikit-learn's `Tree` object; `HistGradientBoostingClassifier` is a separate histogram-based implementation that does not accumulate impurity decrease per feature, so there is nothing to expose. The instruction was written from the general shape of the sklearn tree API rather than from this estimator's attribute list.

**Replaced** with `permutation_importance`, scored against `average_precision` — the metric the project actually reports, rather than impurity decrease, which measures something else. Three side benefits: it is model-agnostic, so a later estimator swap needs no change here; it permutes **raw input columns**, returning one row per feature name rather than 39 post-one-hot column names requiring a reverse mapping; and it comes with a standard deviation, which turned out to be load-bearing.

That standard deviation is why `04_feature_importances.csv` carries an `informative` flag from a 2σ screen. **Eighteen of 26 features fail it and six score ≤ 0** — a permutation importance below its own standard deviation means "shuffling this column made no measurable difference," which is a materially different statement from "this feature is weakly useful."

**Same failure surface, avoided elsewhere:** the design plan also tells the app to recover the fitted column order from `feature_names_in_`. That attribute exists on the `ColumnTransformer` but sits two layers inside a `CalibratedClassifierCV` pickle, and its presence depends on how the estimator was fitted. Notebook 4 exports `04_feature_columns.csv` explicitly instead. **The general rule: do not read an attribute off an estimator without checking that estimator's own API.**

---

## 6. The smaller entries

Logged in full in `blockers.md`. Included here because the file's stated policy is that a five-minute library bug is worth a minute of writing down.

| ID | Symptom | Root cause | Cost |
|---|---|---|---|
| **BLK-001** | `TypeError: Addition/subtraction of integers and integer-arrays with Timestamp` on a Plotly `add_vline` | A Plotly bug, not a project bug: the annotation-placement helper computes a midpoint with `sum()`, whose accumulator starts at integer `0`, so the first operation is `0 + Timestamp`. Triggered only by a datetime x-value **and** an annotation together. Fixed by drawing shape and annotation separately. | ~10 min, most of it following an error message that pointed at pandas |
| **BLK-004** | `ValueError: The truth value of a Series is ambiguous` raised inside a zero-variance check that has nothing to do with truth values | A non-idempotent list append three cells earlier put a feature name in twice, so `X_train[col]` returned a DataFrame instead of a Series. Would have silently widened the feature matrix and **misaligned every column position the app reads** — a silent misprediction traceable to nothing. Later removed by construction in the rebuild. | ~10 min |
| **BLK-005** | `AttributeError: 'DataFrame' object has no attribute 'between'` | `.between()` is a `Series` method. Straight API mix-up in a belt-and-braces check; the substantive version of the same check was already passing on the raw arrays. | <5 min |
| **BLK-009** | `AssertionError: calibration bins disagree` between two notebooks' decile tables | **45,246 rows do not divide by 10.** Six deciles get 4,525 rows and four get 4,524, and *which* bins get the extra row depends entirely on the binning rule. One notebook used `pd.qcut`, the other rank-and-floor. One row moves across four bin edges, observed rates differ in the **sixth decimal place**, and `np.allclose`'s default `rtol=1e-05` lands exactly on that boundary. **Both tables were correct.** | ~10 min |

**BLK-009 is worth one extra line, because the fix went the harder way.** Raising the tolerance would have made the symptom disappear and destroyed the check — an assertion that passes regardless of which binning rule was used is not testing anything. Matching the upstream convention instead made the two artifacts byte-comparable and let the assertion be **tightened**, from one `np.allclose` to three checks including an exact integer equality on bin sizes.

The general shape is worth remembering more than the specific fix: **two notebooks computing "the same" equal-count bins over a row count that doesn't divide evenly will disagree, and the disagreement will be small enough to look like a floating-point problem and large enough to fail a default-tolerance assert.**

---

## 7. Still open

Named here rather than closed, because an open item that is written down is cheaper than one that is rediscovered.

| Item | Status |
|---|---|
| **The sensitivity CSV has a reading trap.** `dispute_fee` and `ops_review_cost` both sit inside the false-negative cost, so raising either also raises the do-nothing baseline that net savings is measured against. Their net-savings columns rise even where the policy gets worse. | Documented in `METRICS.md` §7.4 with the explicit comparability rule. The cleaner fix — adding a `total_cost_inr` column to the export — is not yet done. |
| **72% of the test label is post-snapshot.** Measured and exported; the mechanism is that `raised_at` extends to 2027-01-26 against a declared 2026-11-01 snapshot. | Now stated in plain language in `METRICS.md` §7.1, next to the first rupee figure. Closed as a documentation item; remains a permanent limitation of the dataset. |
| **`04_model_card.csv` does not record the fitted `C`** or the winning HGB configuration. Both exist in cell output and `04_hgb_search_results.csv`, but the card is the file a reader checks. | Two rows to add. |
| **The train/test gap table is computed outside any notebook cell.** It is quoted in `METRICS.md` §8 and traces to an exported CSV, but has no printing cell. | Against the project's own traceability rule. One cell to add. |
| **The design documents still describe the superseded approach.** The LLD and dev plan still specify `class_weight='balanced'`, isotonic calibration with `cv=3`, and `.feature_importances_`. | **A clean re-run from those documents would reintroduce all three failures in §1–§3.** They should be amended before anyone re-runs the pipeline from the specs rather than from the notebooks. |

---

## 8. What this file is actually evidence of

Four things, in order of how much they matter:

1. **The failures that mattered raised no exceptions.** Sections 1, 2 and 4 all describe code that ran cleanly and produced plausible numbers. They were caught by metric tables, skill scores, and a `max_proba` column — not by tracebacks. That is why the evaluation function reports Brier, log-loss and `max_proba` on every model unconditionally, whether or not anyone asked for them.

2. **Specifications were tested, not obeyed.** Three prescribed modelling choices and four prescribed evaluation mechanics were measured, found wrong on this data, and replaced — each with a number attached to the replacement. None of them was a preference. Every one was specified before the relevant property of the data was known, and every one is falsified by a printed figure.

3. **The inconvenient results were kept.** The deployed model is *simpler* than the one specified. Calibration barely helped. Eighteen of 26 features are indistinguishable from noise. One segment's review band loses money. Every one of those is in `METRICS.md`.

4. **Predicting a failure makes it cheap.** The blockers log carries a "candidates to watch" section that pre-loads hypotheses for likely future problems. The empty threshold grid in §4 was on that list before it fired, which turned a potentially wrong headline number into a ten-minute fix and a one-line assertion.
