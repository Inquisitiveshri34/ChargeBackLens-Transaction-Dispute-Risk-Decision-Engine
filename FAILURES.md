# ChargebackLens — Blockers Log

**Purpose:** a running record of things that stopped the build, what actually caused them, and what fixed them. One entry per blocker, newest at the bottom. This is the raw material for `FAILURES.md` at submission time — `FAILURES.md` gets the one or two entries with real before/after numbers and a genuine lesson; this file keeps everything, including the small ones, so nothing has to be reconstructed from memory later.

**What counts as a blocker:** anything that stopped forward progress and needed a diagnosis, however briefly. A five-minute library bug is worth logging — the cost of writing it down is a minute, and the cost of hitting the same thing again in notebook 5 without a record is longer than that.

**Entry format:** ID · notebook/file · symptom · root cause · fix · prevention · status.

---

## BLK-001 — `add_vline` with an annotation raises `TypeError` on a date axis

| | |
|---|---|
| **Date** | Notebook 2 build |
| **Where** | `02_eda.ipynb`, Cell 9 (Chart 2 — weekly dispute rate) |
| **Severity** | Low — cosmetic feature, hard failure, quick fix |
| **Status** | ✅ Resolved, fix committed |

### Symptom

The cell raised on the `SPLIT_DATE` marker, with a traceback ending several frames deep inside Plotly rather than in project code:

```
TypeError: Addition/subtraction of integers and integer-arrays with Timestamp
is no longer supported. Instead of adding/subtracting `n`, use `n * obj.freq`
```

The offending line looked entirely ordinary:

```python
fig.add_vline(x=pd.Timestamp(SPLIT_DATE), line_dash="dot", line_color="crimson",
              annotation_text="SPLIT_DATE", annotation_position="top left")
```

The wording of the error points at pandas and at frequency arithmetic, neither of which the cell is doing. That misdirection is the only genuinely costly part of this blocker — the instinct is to go looking for a resampling bug in the `weekly` DataFrame built two lines above, which is not where the problem is.

### Root cause

A Plotly bug, not a project bug. To position an annotation on an axis-spanning line, `plotly/shapeannotation.py` computes the midpoint of the line's endpoints via a helper that does `float(sum(x)) / len(x)`. Python's `sum()` starts its accumulator at integer `0`, so the first operation is `0 + Timestamp`, which pandas refuses.

The trigger is the **combination** of a datetime x-value and an annotation. Either alone is fine. Verified on `plotly==5.24.1` / `pandas 3.0.2`:

| Call | Result |
|---|---|
| `add_vline(x=Timestamp, annotation_text=...)` | ❌ `TypeError` (int + Timestamp) |
| `add_vline(x="2026-08-01", annotation_text=...)` | ❌ `TypeError` (int + str) |
| `add_vline(x=Timestamp)` — no annotation | ✅ works |
| `add_vline(x=Timestamp.timestamp()*1000, annotation_text=...)` | ✅ works |
| `add_shape(...)` + `add_annotation(...)` | ✅ works |

Fixed upstream in Plotly 7.x, where the original call succeeds. The local environment is on 5.x.

### Fix applied

Draw the shape and the annotation as two separate calls, which never enters the midpoint-calculation code path:

```python
split_ts = pd.Timestamp(SPLIT_DATE)

# add_vline(x=<datetime>, annotation_text=...) raises TypeError on plotly 5.x —
# its label-placement helper sums the endpoints, and int + Timestamp is invalid.
# Drawing the shape and the annotation separately avoids that code path entirely.
fig.add_shape(type="line", x0=split_ts, x1=split_ts, y0=0, y1=1, yref="paper",
              line=dict(dash="dot", color="crimson"))
fig.add_annotation(x=split_ts, y=1.02, yref="paper", text="SPLIT_DATE",
                   showarrow=False, xanchor="left", font=dict(color="crimson"))
```

`yref="paper"` reproduces `add_vline`'s full-height span independent of the y-range; `y=1.02` sits the label just clear of the plot area.

### Why this fix over the alternatives

- **Epoch-milliseconds (`Timestamp.timestamp() * 1000`)** works, but leaves a magic number in the notebook that a reader has to decode, and breaks silently if the axis type ever changes.
- **Upgrading Plotly to 7.x** fixes it properly, but a mid-build dependency bump risks changing chart rendering across notebooks 2 and 5 for a cosmetic gain, and `requirements.txt` is meant to be pinned to the environment that pickles the models (dev plan §1.2).
- **`add_shape` + `add_annotation`** works identically on 5.x and 7.x, needs no version constraint, and is self-documenting with the two-line comment. Chosen for portability — the Streamlit Cloud deployment (dev plan §10) resolves its own dependency versions, and this fix is correct under either.

### Prevention

- The comment stays in the cell permanently. Without it, a future reader "simplifies" it back to `add_vline` and reintroduces the failure.
- **Scope check:** `02_eda.ipynb` Cell 9 is the only place in the project that draws a vertical marker on a date axis. Notebook 5's threshold-sweep chart marks the optimal threshold on a **numeric** x-axis, where plain `add_vline(x=..., annotation_text=...)` is safe. No other cell needs this treatment.
- Pin `plotly` in `requirements.txt` once the environment settles, so the deployed app and the notebooks agree on which of the two behaviours is in play.

### Cost

Roughly ten minutes, almost all of it spent following the error message toward pandas before recognising the failure was inside a Plotly helper. No data, artifact, or downstream result was affected — the chart's data was already correct, only the marker failed to render.

---

## BLK-002 — `ip_billing_state_mismatch` is specified against a column that does not exist

| | |
|---|---|
| **Date** | Notebook 3 build |
| **Where** | `03_feature_engineering.ipynb`, `build_instant_features()` |
| **Severity** | Medium — a specified feature could not be built at all |
| **Status** | ✅ Resolved, substitute shipped and documented |

*This entry was written up after the fact from `feature_engineering.md` §6 and §7.3, which recorded the decision at the time and referenced it as `BLK-002` before the entry itself existed. Verify the wording against the notebook before it goes into `FAILURES.md`.*

### Symptom

`ip_billing_state_mismatch` appears in `chargebacklens_lld.md` §4.3's `FEATURE_KNOWABILITY` dict, in dev plan §4.1 step 3, and in EDA §2.4's decision table. It is not computable. No table in the dataset carries a billing state: `transactions` has `ip_state` only, `customers` has no geography column at all, and `merchants` has none.

### Root cause

A specification written against a schema that was never generated. The data spec (`chargebacklens_data_spec.md` §3.2) defines `customers.csv` with seven columns, none of them a location — so the feature was impossible from the moment the generator ran, and three separate documents carried it forward without anyone checking it against §3.2.

### Fix applied

Substituted `ip_state_changed_from_prev_txn` — computable from `transactions` alone, leakage-safe under the same `closed='left'` trailing discipline as the other velocity features, and answering the nearest available question ("is this customer transacting from an unusual place"). Recorded in `03_feature_knowability.csv` with the substitution reason in its `rationale` column, so the artifact itself explains the swap.

### Why this fix over the alternatives

- **Dropping the feature silently** would have left three documents describing a feature the matrix doesn't have.
- **Synthesising a billing state** would mean writing to `data/raw/`, which HLD §2 forbids outright.
- **Regenerating `customers.csv` with a geography column** would invalidate every count in the data spec and force notebooks 1–2 to be re-run for one feature of unknown value.

### Prevention

The substitute turned out to be **uninformative on this dataset** (`feature_engineering.md` §7.3): it fires on 92.0% of rows conditional on having a prior transaction, against a ~93% expectation under independent draws. The generator assigns `ip_state` per transaction with no customer-level home state, so there is nothing to detect. Confirmed in the rebuilt notebook 4 — permutation importance **+0.000012 ± 0.000809**, rank 19 of 26, with a standard deviation sixty-seven times its mean. It is not merely small, it is indistinguishable from a shuffled column.

*(Figure updated after the notebook 4 rebuild; the earlier `+0.000182` came from the superseded run, which measured importance on the test set against a different fitted model. See BLK-003.)*

The substitution is still the right call, and the finding is worth reporting: it is a property of the synthetic data, not a modelling failure. On genuine payments data the feature would carry real signal.

Broader prevention: features specified in the LLD are only real once checked against `chargebacklens_data_spec.md` §3's column lists. Notebook 3's practice of writing the feature contract to disk *before* building anything is what surfaced this at declaration time rather than at fit time.

### Cost

Contained to notebook 3. No downstream artifact was wrong — the substitute is in the matrix, in the contract, and in both splits, and its near-zero importance is explained rather than mysterious.

---

## BLK-003 — `HistGradientBoostingClassifier` has no `.feature_importances_`

| | |
|---|---|
| **Date** | Notebook 4 build |
| **Where** | `04_model_building.ipynb`, Cell 11 (feature importances) |
| **Severity** | Medium — specified by two design documents, hard failure, no in-place substitute |
| **Status** | ✅ Resolved, replaced with `permutation_importance` |

### Symptom

```
AttributeError: 'HistGradientBoostingClassifier' object has no attribute 'feature_importances_'
```

on the line the dev plan explicitly instructs:

```python
main_pipeline.named_steps["clf"].feature_importances_
```

### Root cause

Not a version issue and not a fitting issue — the attribute has never existed on this estimator. `feature_importances_` is exposed by `GradientBoostingClassifier`, `RandomForestClassifier` and the other tree ensembles built on sklearn's `Tree` object. `HistGradientBoostingClassifier` is a separate histogram-based implementation that does not accumulate impurity decrease per feature, so there is nothing to expose.

Both `chargebacklens_lld.md` §4.6 and `chargebacklens_dev_plan.md` §5.1 step 8 instruct pulling it. The instruction was written from the general shape of sklearn's tree API rather than from this specific estimator's attribute list.

### Fix applied

`sklearn.inspection.permutation_importance` on the fitted pipeline, scored against the metric the project actually reports:

```python
pi = permutation_importance(
    selected_model, X_cal, y_cal,          # validation block, NOT test
    scoring="average_precision",
    n_repeats=8,
    random_state=RANDOM_SEED,
    n_jobs=2,
)
```

Exported as `04_feature_importances.csv` (26 rows × 5 cols) with `importance_std`, a `rank`, and an `informative` flag set by a 2σ screen (`importance > 2 * importance_std`).

### Why this fix over the alternatives

- **Switching the estimator to `GradientBoostingClassifier`** to recover the attribute would trade a 120K-row-capable histogram implementation for a much slower one, and would change the model to suit a reporting convenience. Backwards.
- **SHAP** is already named in HLD §12 as explicitly optional, and would add an install and a runtime cost for an explanation the app can serve from a ranked table.
- **`permutation_importance`** scores against `average_precision` — the metric in `METRICS.md`, not impurity decrease, which measures something else. It is model-agnostic, so if §6's retuning swaps the estimator, this cell needs no change. And because it permutes the **raw input columns**, it returns one row per `feature_name` rather than one per post-`ColumnTransformer` column, which is the shape `app/explain.py` actually wants — the specified approach would have returned 39 one-hot column names for the baseline branch and required a reverse mapping.

**Amended in the notebook 4 rebuild:** the original fix computed importances on the **test set**. That was defensible — nothing was tuned from them — but it was unnecessary, because the rebuild introduced a dedicated validation block (`cal_blk`, 14,947 rows, 128 positives) that is held out from fitting and already carries every other selection decision. Importances now come from that block, so the test set is read exactly once in the whole notebook, in the final scoring cell. The cost is a noisier estimate on a quarter of the rows, which is why `n_repeats` went from 5 to 8 and why `importance_std` is load-bearing rather than decorative.

Runtime: 26 features × 8 repeats = 208 scoring passes over 14,947 rows, a few seconds with `n_jobs=2`.

### Prevention

- The `informative` column in `04_feature_importances.csv` is a 2σ screen, not a ranking. Eighteen of 26 features fail it, and six score ≤ 0 — a permutation importance below its own standard deviation means "shuffling this column made no measurable difference," which is a different statement from "this feature is weakly useful." The app's reviewer note must only quote features where `informative == True`.
- `importance_std` is exported alongside `importance` precisely because several features (`amount_vs_own_avg`, `amount_vs_merchant_avg_ratio`) have a standard deviation larger than their mean. The app's reviewer note must not quote a feature whose importance is inside its own noise.
- **Same failure surface elsewhere:** dev plan §7.2 tells `app/scoring.py` to recover the fitted column order from `feature_names_in_` on the pipeline. That attribute exists on the `ColumnTransformer` but is two layers inside a `CalibratedClassifierCV` pickle. Notebook 4 exports `04_feature_columns.csv` instead, for the same reason this entry exists — do not read an attribute off an estimator without checking that estimator's own API.
- `chargebacklens_lld.md` §4.6 and dev plan §5.1 step 8 should both be amended to say `permutation_importance`, or the next clean re-run reintroduces the failure.

### Cost

About fifteen minutes, most of it spent confirming the attribute genuinely does not exist rather than assuming a fitting problem. No artifact was affected — the models were already fitted correctly and the importances file simply had not been written yet.

---

## BLK-004 — a duplicated feature column surfaces three cells later as an unrelated `ValueError`

| | |
|---|---|
| **Date** | Notebook 4 build |
| **Where** | `04_model_building.ipynb` (superseded version), Cell 5 (X / y / meta) — caused in Cell 4 |
| **Severity** | Medium — would have silently widened `X` and misaligned the app's column positions |
| **Status** | ✅ Resolved, then **superseded** — the mutating cell no longer exists (see *Superseded by the rebuild* below) |

### Symptom

```
ValueError: The truth value of a Series is ambiguous.
Use a.empty, a.bool(), a.item(), a.any() or a.all().
```

raised inside a zero-variance check that has nothing to do with truth values:

```python
const = [c for c in numeric_cols if X_train[c].nunique() == 1]
```

The traceback ends in `pandas/core/generic.py::__nonzero__`, which points at a boolean-context bug in the comprehension. There isn't one.

### Root cause

`feature_cols` contained `has_prior_30d` twice, so `X_train[c]` returned a **DataFrame** rather than a Series. `DataFrame.nunique()` returns a Series, and `Series == 1` has no single truth value — hence the error, three cells away from the cause.

The duplicate came from Cell 4:

```python
numeric_cols = numeric_cols + ["has_prior_30d"]
```

which is not idempotent. Cell 3 rebuilds `numeric_cols` from `03_feature_knowability.csv`; Cell 4 appends to it. Re-running Cell 4 alone — which happens constantly while iterating on the derivation — appends a second copy. Cell 3's set-equality assert cannot catch it: it ran earlier, and sets deduplicate anyway.

### Fix applied

Two changes. Append conditionally:

```python
if "has_prior_30d" not in numeric_cols:
    numeric_cols = numeric_cols + ["has_prior_30d"]
```

and assert uniqueness at the point the fitted order is fixed:

```python
assert len(feature_cols) == len(set(feature_cols)), \
    f"duplicate feature names: {sorted({c for c in feature_cols if feature_cols.count(c) > 1})}"
assert not (set(numeric_cols) & set(categorical_cols)), "a column is tagged both numeric and categorical"
```

Plus a width assert in Cell 5 (`X.shape[1] == 26 + ADD_HAS_PRIOR_30D`) and `X.columns.is_unique`, so the failure names itself instead of surfacing as a pandas type error.

### Why this fix over the alternatives

- **Re-running Cell 3 before Cell 4 every time** is a discipline, not a fix, and dev plan §9 requires the notebook to run top-to-bottom without manual cell ordering.
- **Rebuilding `numeric_cols` from the contract inside Cell 4** would work, but duplicates Cell 3's job in two places — the exact drift the "derive roles from the artifact, never hand-type them" rule exists to prevent.
- **The guard plus the assert** keeps the derivation in one place, makes the cell safe to re-run, and converts any future recurrence into a named error at the line that causes it.

### Prevention

The uniqueness assert is the real protection, and it protects against more than this one cause. A duplicate in `feature_cols` would otherwise have been survivable: `ColumnTransformer` would happily fit the same column twice, `HGB_CAT_MASK` would still be the right length, and the model would train without error — but every `position` in `04_feature_columns.csv` after the duplicate would be off by one, and `app/scoring.py` builds its feature row from those positions. That is a silent misprediction in the deployed app, traceable to nothing.

**Same failure surface:** any notebook cell that mutates a list or DataFrame it also reads from. Notebook 3 has the same pattern in its feature-assembly cells; notebook 5 will have it in the threshold and segment loops. The general rule is that a cell which appends to module-level state must either be idempotent or rebuild that state from disk first.

### Superseded by the rebuild

The notebook 4 rebuild removed `has_prior_30d` entirely. `feature_engineering.md` §7.2 had recommended deriving it to disambiguate `amount_vs_own_avg`'s `1.0` sentinel, and it was worth trying — but it earned nothing. In the rebuilt model `amount_vs_own_avg` itself scores a permutation importance of **−0.000434**, i.e. shuffling it *improves* PR-AUC slightly; a flag disambiguating a column that carries no signal disambiguates nothing. Dropping it also settles a smaller argument: the fitted width is now exactly the contract's width, 26 columns straight out of `03_feature_knowability.csv`'s `model_role`, with no append step anywhere in the notebook.

So the specific bug is gone by construction rather than by guard — there is no longer a cell that mutates a list it also reads from. The uniqueness assert was dropped with it, which is the right call only because the append it protected against was also dropped. **If any future cell appends to `NUMERIC` or `FEATURES`, restore the assert in the same commit.**

### Cost

Around ten minutes, all of it spent reading a traceback that pointed at a boolean-context problem in a comprehension rather than at a list append two cells earlier. No artifact was affected — the error fired before anything was fitted or written.

---

## BLK-005 — `DataFrame` has no `.between()`

| | |
|---|---|
| **Date** | Notebook 4 build |
| **Where** | `04_model_building.ipynb`, Cell 14 (definition of done) |
| **Severity** | Low — belt-and-braces check, hard failure, one-line fix |
| **Status** | ✅ Resolved |

### Symptom

```
AttributeError: 'DataFrame' object has no attribute 'between'
```

from:

```python
bool(test_predictions.filter(like="proba_").between(0, 1).all().all())
```

### Root cause

`.between()` is a `Series` method. `.filter(like="proba_")` returns a DataFrame of four probability columns, which never had it. A straightforward API mix-up, written on the assumption that `.between()` broadcasts the way comparison operators do.

### Fix applied

```python
proba_block = test_predictions.filter(like="proba_")
bool(((proba_block >= 0) & (proba_block <= 1)).all().all())
```

Chained comparison operators *do* broadcast elementwise on a DataFrame; `.all().all()` then collapses columns and then rows. A `notna().all().all()` check was added on the same block while it was in hand.

### Why this fix over the alternatives

`.apply(lambda s: s.between(0, 1))` also works but iterates column-wise for no benefit. `.stack().between(0, 1)` materialises a long Series unnecessarily. The operator form is the shortest and reads as what it does.

### Prevention

Marginal — this is a straight API error, not a design flaw, and the notebook already had the substantive version of the same check: `score_split()` asserts `np.isfinite(p).all() and (0.0 <= p).all() and (p <= 1.0).all()` on the raw NumPy array, per model, at the moment each probability column is produced. The definition-of-done check is a restatement, and it broke on the restatement rather than on the substance.

Logged anyway because this file's stated policy is that a five-minute library bug is worth a minute of writing down, and because the general shape — assuming a Series method exists on a DataFrame — will recur in notebook 5's threshold sweep, which does a lot of column-block arithmetic.

**After the rebuild:** the definition-of-done cell checks one column rather than a block — `test_pred.proba_calibrated.between(0, 1).all()` — so `.between()` is now called on a genuine Series and the entry's fix is no longer in the notebook. The narrowing is deliberate: the check exists to validate the **deployed** model's output, and the other three probability columns are diagnostic comparators that notebook 5 reads but the app never loads.

### Cost

Under five minutes. Nothing downstream affected; the models and all four CSVs had already been written by the time this cell ran.

---

## BLK-006 — the main model loses to its own baseline on test PR-AUC

| | |
|---|---|
| **Date** | Notebook 4 build |
| **Where** | `04_model_building.ipynb`, Cells 8 and 10 — surfaces in the definition-of-done print |
| **Severity** | **High** — blocks dev plan §6.4's definition of done for notebook 5 |
| **Status** | ✅ Resolved — both scoped responses executed; notebook 4 rebuilt around the result |

### Symptom

The notebook ran clean. All six definition-of-done checks passed. The directional print at the end reads:

```
PR-AUC baseline → main : 0.0839 → 0.0517 (⚠️ DOES NOT IMPROVE)
```

| | Train PR-AUC | Test PR-AUC | Ratio |
|---|---:|---:|---:|
| baseline (LogisticRegression) | 0.0667 | **0.0839** | 0.79 — generalises |
| main (HGB) | 0.5130 | 0.0517 | **9.9 — memorises** |

Test base rate is 0.0090, so the baseline is a 9.3× lift and the main model a 5.7× lift. Both beat random; the specified main model is simply the worse of the two.

### Root cause

Capacity set without reference to the positive count. `max_iter=300` at `max_depth=6`, sklearn's default `min_samples_leaf=20`, no `l2_regularization`, run to all 300 iterations with `early_stopping=False`, on 643 positives in 74,731 rows — and with `class_weight='balanced'` making each positive worth roughly 116 negatives. A depth-6 tree can isolate individual reweighted positives into their own leaves and be rewarded for doing so. The hyperparameters come from `chargebacklens_lld.md` §4.5, which fixed them before the split's positive count was known.

The second half of the cause is in the data, and it is the more interesting half. Notebook 4's permutation importances rank `phone_verified` (0.0258), `email_domain_type` (0.0244) and `log_amount` (0.0134) at the top — precisely the clean, large, monotone spreads EDA §2.5–§2.6 found. The trailing velocity features are thin (`feature_engineering.md` §7.1: `txns_last_24h` non-zero on 2.5% of rows, `prior_disputes_before_this_txn` on 1.9%), and `ip_state_changed_from_prev_txn` carries nothing at all (BLK-002). There is very little interaction structure in this synthetic data for a boosted ensemble to exploit and a great deal of room for it to overfit. On this dataset an additive model is not a strawman — it is the appropriate model.

### Fix applied

Both scoped responses were executed, in the order written, and the notebook was rebuilt around the outcome.

**Response 1 — the capacity sweep ran, and it worked.** A 16-configuration randomized search over `learning_rate` / `max_leaf_nodes` / `min_samples_leaf` / `l2_regularization` / `max_features`, scored with `TimeSeriesSplit(n_splits=4)` inside the fit block, with `early_stopping=True` replacing the fixed 300 iterations. The search's own answer is the diagnosis restated: it selected **4 leaf nodes** and `min_samples_leaf=400`. Asked how much tree it wanted, the search said barely any.

| HGB | Train PR-AUC | Test PR-AUC | Ratio |
|---|---:|---:|---:|
| prescribed (`max_depth=6`, 300 iters, balanced) | 0.5130 | 0.0517 | **9.9 — memorises** |
| tuned (4 leaves, `min_samples_leaf=400`, early stopping) | 0.1055 | **0.0812** | **1.30 — generalises** |

Test PR-AUC improved **0.0517 → 0.0812**, a 57% gain, entirely from removing capacity. The overfitting half of the diagnosis is fixed.

**Response 2 — it still lost, so the additive model ships.** The tuned HGB at 0.0812 remains below the logistic regression at **0.0872**. Selection was made on the validation block before test was read, using a rule written down before it was applied: rank by validation PR-AUC, form a tie set from candidates whose paired bootstrap CI against the leader contains zero, break the tie on `(model-class simplicity, validation log-loss)`. All five candidates landed in the tie set — with 128 validation positives nothing separates — and the tie-break selected `LR_plain`.

| Test | PR-AUC | Lift@1% | P@5% | Brier |
|---|---:|---:|---:|---:|
| prescribed baseline (LR balanced) | 0.0842 | 17.2× | 0.0769 | 0.1404 |
| tuned HGB (`proba_main`) | 0.0812 | 15.5× | 0.0721 | 0.0086 |
| **deployed (LR + sigmoid)** | **0.0872** | **16.2×** | **0.0778** | **0.0086** |

A paired bootstrap on test puts the tuned-HGB-minus-deployed gap at −0.0060, CI [−0.0168, +0.0060] — so the HGB is *not* significantly worse either. The honest claim is not "the linear model wins," it is "on 407 test positives nothing separates these models, so the selection rule picked the simpler and better-calibrated one, and it was picked before test was read."

### Why this approach over the alternatives

- **Tuning against the test set** would be the fast fix and would invalidate every number in `METRICS.md`. The whole temporal-split argument in HLD §7 exists to prevent exactly this.
- **Reporting the HGB as the model anyway** and hoping the PR curve in notebook 5 obscures it — dishonest, and the comparison table the dev plan requires would expose it immediately.
- **Dropping the baseline from the report** so nothing contradicts the main model — worse. LLD §4.5's stated reason for fitting three models in sequence is that "a single model presented alone is a claim, while three models compared side-by-side is evidence." The evidence came back inconvenient; that is what evidence does.

### Prevention

- The directional check is deliberately a **printed warning, not an `assert`** — a failure here is a finding for notebook 5 and `FAILURES.md`, not a reason to halt a notebook whose own definition of done (models fit, reload, and score) was met.
- The train PR-AUC column in `04_train_predictions.csv` is what made this diagnosable in one line. It exists to measure the train/test **gap**, never to be reported.
- **Same failure surface:** any future hyperparameter change. If notebook 4 is re-run, all four CSVs and all four `.joblib` files must be re-exported together — a mixed artifact set is dev plan §9's stale-artifact failure.

### Cost

The diagnosis was immediate and took one table. The fix cost a full rebuild of notebook 4 — a three-way temporal split, a hyperparameter search, a written selection rule, and a re-export of every artifact — plus the invalidation of every number in the superseded `model_building.md`. The search itself runs in 68 seconds; the design work around it was the expense.

Nothing downstream was corrupted, because nothing downstream had been built yet. Had this been found during notebook 5 instead, the economics layer, the threshold sweep and `METRICS.md` would all have been written against a model that was about to be replaced.

**This is the strongest candidate in this file for `FAILURES.md`.** It has real before/after numbers (0.0517 → 0.0812 on capacity alone, still losing to 0.0872), a diagnosis that connects the model to the data rather than to a library, and a decision made on evidence against a documented expectation — including the part where the evidence came back inconvenient twice.

---

## BLK-007 — `class_weight='balanced'` makes the probabilities unusable by the economics layer

| | |
|---|---|
| **Date** | Notebook 4 rebuild |
| **Where** | `04_model_building.ipynb`, Cells 11 and 19 — consequence lands in notebook 5 |
| **Severity** | **High** — would have silently inflated every rupee figure in the submission |
| **Status** | ✅ Resolved — deployed model fits unweighted; weighted variants retained as comparators only |

### Symptom

No error. The prescribed baseline scores a perfectly respectable test PR-AUC of 0.0842 and a **Brier score of 0.1404**, against a test base rate of 0.8995%. Its maximum predicted probability is 0.9913.

A constant predictor that always outputs the base rate scores a Brier of `r(1−r) = 0.008914`. The prescribed baseline is therefore **fifteen times worse than predicting nothing at all**, while ranking transactions well.

### Root cause

`class_weight='balanced'` reweights each positive by roughly 116× (the inverse class frequency), which is a legitimate way to keep a rare class from being ignored by the loss. But logistic regression fits probabilities, and reweighting the loss shifts the fitted intercept: the model learns the conditional probability of the *reweighted* population, in which disputes are ~50% of the mass, not the real one where they are 0.9%. The outputs are a monotone transform of the right answer, so every **ranking** metric is unaffected — PR-AUC, precision@k and the review queue all look fine — and every **magnitude** is roughly 50× too large.

That is exactly the failure HLD §7 names when it says calibration is what makes the economics layer honest rather than decorative: `expected_cost_matrix()` multiplies a probability by a rupee amount. Multiply by 0.4 instead of 0.008 and the sweep reports savings that do not exist, with no error anywhere.

The instruction is in `chargebacklens_lld.md` §4.5 and dev plan §5.1 steps 4–5, applied to both the baseline and the main model. EDA §2.1 justified it from the 113:1 imbalance — correctly, as a reason not to let the loss ignore positives, but the conclusion was carried into a project whose entire downstream layer consumes magnitudes.

### Fix applied

The escalation grid fits both `class_weight=None` and `class_weight='balanced'` across six values of `C`, and the selection rule's tie-break is validation **log-loss** — a proper scoring rule, which is precisely the thing that separates two models with near-identical rankings and wildly different scales.

```
LR_weighted   val_pr_auc 0.05408   val_brier 0.1412   val_log_loss 0.4478
LR_plain      val_pr_auc 0.05257   val_brier 0.0083   val_log_loss 0.0437
```

The two rank the same to within bootstrap noise (gap +0.0017, CI [−0.0020, +0.0060]). The tie-break selected `LR_plain`, whose raw Brier of 0.008335 already beats the constant-rate reference before any calibration is applied.

### Why this fix over the alternatives

- **Keep `balanced` and calibrate it away.** This works — a sigmoid recovers the scale — but it means applying a transform to undo a transform that was applied for no benefit. The weighted model bought zero ranking improvement here.
- **Keep `balanced` and only ever use ranks downstream.** Would gut the project. The three-band decision and the whole economics layer exist because the probability is a probability.
- **Fit unweighted and check the loss isn't ignoring positives.** What was done. At 0.9% with 26 features the unweighted fit finds the signal fine — its PR-AUC is the highest of any candidate on test.

### Prevention

- `evaluate()` reports `brier`, `log_loss` and `max_proba` on **every** model, always. `max_proba` is the cheapest tell: a model whose maximum output is 0.99 on a 0.9%-base-rate problem is reporting on a different population than the one it will be deployed against.
- One definition-of-done check is now `deployed Brier <= prescribed-baseline Brier`, which fails loudly if a weighted model is ever selected without repair.
- **Same failure surface:** any resampling technique. SMOTE, random undersampling and `scale_pos_weight` in XGBoost all distort the base rate the same way and all leave ranking metrics untouched. If any of them is tried in a later iteration, calibrate before the economics layer touches the output — or don't use them.

### Cost

No time lost — this was found by the metric table rather than by debugging. The cost avoided is the real number: notebook 5's threshold sweep, sensitivity analysis and segment economics would all have run without error against probabilities inflated ~50×, and the error would have been invisible in every chart.

---

## BLK-008 — the prescribed isotonic calibration destroys ranking

| | |
|---|---|
| **Date** | Notebook 4 rebuild |
| **Where** | `04_model_building.ipynb`, Cell 17 (calibration method selection) |
| **Severity** | Medium — would have cost ~10% of PR-AUC in exchange for nothing |
| **Status** | ✅ Resolved — prefit sigmoid on a held-out temporal block |

### Symptom

`chargebacklens_lld.md` §4.5 specifies `CalibratedClassifierCV(estimator=fitted_pipeline, method='isotonic', cv=3)`. Fitted that way and measured on the validation block:

```
   method  val_pr_auc  val_brier  val_log_loss
  sigmoid    0.048567   0.008351      0.044070
none(raw)    0.048567   0.008330      0.044111
 isotonic    0.043765   0.008367      0.048669
```

Isotonic loses **10% of PR-AUC** and is the worst of the three on log-loss. Calibration was supposed to change the scale, not the ranking.

### Root cause

Two separate mechanisms, both in the prescribed call.

**Isotonic regression is a step function.** It fits a piecewise-constant non-decreasing map, so scores that were distinct on either side of a step come out **identical**. Every collapsed tie is a ranking decision destroyed, and at the top of a queue sorted by probability that is exactly where the decisions matter. The LLD's stated reason for choosing isotonic over sigmoid — ">500 positives, enough for a stable non-parametric fit" — counts the positives in the whole training set, but an isotonic fit on a 0.9% problem is really estimating a handful of interior knots from the few hundred positives that land in the upper bins.

**`cv=3` is not a calibration wrapper, it is an ensemble.** `CalibratedClassifierCV` with an integer `cv` refits the base estimator on each fold and averages the three calibrated fold-models' predictions. The output is not "your model, rescaled" — it is a three-model ensemble, whose ranking differs from the original for reasons that have nothing to do with calibration. That also makes the dev plan §5.2 check "`proba_calibrated` is not identical to `proba_main`" pass for the wrong reason: it would pass even if the calibration map were the identity.

The third problem is temporal. `cv=3` shuffles across the training window, so a fold model trained on July gets calibrated against February. Everything else in this project is split by date specifically to avoid that.

### Fix applied

Prefit calibration on a held-out temporal block: fit the model on `fit_blk` (Jan–24 Jun), fit a **single** sigmoid map on `cal_blk` (24 Jun–31 Jul), never shuffle across the boundary.

```python
from sklearn.frozen import FrozenEstimator
CalibratedClassifierCV(FrozenEstimator(estimator), method="sigmoid").fit(X_cal, y_cal)
```

One model, one strictly-monotone map, so PR-AUC and precision@k are **invariant by construction** — confirmed on test at 0.087248 for both `proba_selected` and `proba_calibrated`, identical to six decimal places, while `max_proba` moves 0.474 → 0.334. That invariance is now a definition-of-done check in its own right ("ranking preserved through calibration").

The method is not assumed either. Cell 17 fits sigmoid, isotonic, and no calibration at all on an inner split of the fit block, scores all three on the validation block, and picks by log-loss. Sigmoid won by 0.00004 over doing nothing — the honest reading being that **an unweighted logistic regression is already calibrated**, and the sigmoid map is close to the identity.

`sklearn.frozen.FrozenEstimator` is 1.6+; `cv="prefit"` was removed in the same release. The notebook wraps this in `make_prefit_calibrator()` with a version fallback, since the Streamlit Cloud deployment resolves its own dependency versions.

### Why this fix over the alternatives

- **Isotonic with more data** — the problem is the step function at this positive count, not the sample size of the calibration set.
- **`cv=5` instead of `cv=3`** — more folds, same category error: still an ensemble, still shuffled across time.
- **No calibration at all** — nearly the right answer, and it scored within 0.00004 of the chosen one. Rejected because a project whose central claim is "the probability is real" should demonstrate the check, and because the sigmoid costs nothing: it is one fitted parameter pair applied to a held-out block, and it leaves the ranking untouched.

### Prevention

- Keep the three-way comparison cell permanently. A calibration method asserted rather than measured is the same mistake in a different place.
- **`METRICS.md` must not claim calibration improved the model.** It improved the *scale* marginally and left everything else alone. On test, the raw selected model's Brier (0.008535) is fractionally **better** than the calibrated one's (0.008567) — noise, but it would make a "calibration improved Brier" sentence false as written. Dev plan §6.4's check that Brier improves main → calibrated does hold (0.008583 → 0.008567), because `main` is the HGB; state which comparison is meant.
- **Same failure surface:** notebook 5's PR curve compares three models. If it plots `proba_calibrated` and `proba_selected` as separate curves they will lie exactly on top of each other, which is correct and should be labelled as such rather than looking like a plotting bug.

### Cost

About twenty minutes, mostly spent confirming that the PR-AUC drop was a property of isotonic rather than a bug in the calibration split. No artifact was affected — this was caught during the rebuild, before anything was exported.

---

## BLK-009 — two notebooks bin the same deciles differently and the cross-check fails on four rows

| | |
|---|---|
| **Date** | Notebook 5 build |
| **Where** | `05_model_evaluation.ipynb`, Cell 11 (calibration curve) |
| **Severity** | Low — assertion fired correctly, no wrong number was ever produced |
| **Status** | ✅ Resolved |

### Symptom

```
AssertionError: calibration bins disagree with 04_reliability_bins.csv
```

from the cross-check that notebook 5's recomputed decile reliability matches the table notebook 4 already froze:

```python
_a = calibration_curve.sort_values(["model", "bin"])["observed_frequency"].to_numpy()
_b = nb4_reliability.sort_values(["model", "bin"])["observed_rate"].to_numpy()
assert np.allclose(_a, _b), "calibration bins disagree with 04_reliability_bins.csv"
```

The first read of this is alarming — it looks like the two notebooks disagree about how well the model is calibrated.

### Root cause

They do not. **45,246 rows do not divide by 10.** Each decile wants 4,524.6 rows, so six bins get 4,525 and four get 4,524 — and *which* bins get the extra row depends entirely on how the remainder is distributed. Notebook 5's first implementation used `np.floor(rank * n_bins / N)`; notebook 4 used `pd.qcut`. The two rules disagree at four bin edges:

| bin | notebook 5 (rank-and-floor) | notebook 4 (`qcut`) |
|---|---:|---:|
| 0–5 | identical | identical |
| 6 | 4,525 | 4,524 |
| 7 | 4,524 | 4,525 |
| 8 | 4,525 | 4,524 |
| 9 | 4,524 | 4,525 |

One row moves across each of those four edges. The resulting observed rates differ in the **sixth decimal place** — decile 9 came out 0.050840 against notebook 4's 0.050829, a gap of 1.1e-05. `np.allclose` defaults to `rtol=1e-05`, so a difference that size lands exactly on the tolerance boundary and trips it.

Both tables were correct. Neither ECE, nor the decile-9 under-prediction finding, nor any exported number was affected.

### Fix applied

Match notebook 4's convention rather than loosening the tolerance:

```python
# qcut specifically, because that is what notebook 4 used to build
# 04_reliability_bins.csv. 45,246 doesn't divide by 10, so six bins hold 4,525
# rows and four hold 4,524 — and different equal-count rules put the remainder in
# different bins. A rank-and-floor implementation shifts one row across four bin
# edges, moves the observed rates by ~1e-05, and fails the cross-check below for
# a reason that has nothing to do with calibration. Match the upstream convention
# rather than loosening the tolerance.
assert len(np.unique(y_proba)) >= n_bins * 10, "too many tied scores for qcut deciles"
bins = pd.qcut(y_proba, n_bins, labels=False)
```

With `qcut`, all four columns (`n`, `predicted_mean`, `observed_frequency`, `gap`) match to full float precision for both models, so the assertion was **tightened** at the same time — from one `np.allclose` on observed rates to three checks, one of them an exact integer equality on bin sizes:

```python
assert (_mine["n"].to_numpy() == _nb4["n"].to_numpy()).all(), "bin sizes disagree — binning rule drifted"
assert np.allclose(_mine["observed_frequency"], _nb4["observed_rate"]), "observed rates disagree"
assert np.allclose(_mine["predicted_mean"], _nb4["predicted_mean"]), "predicted means disagree"
```

The `unique >= n_bins * 10` guard is there because `pd.qcut` raises on duplicate bin edges. All 45,246 calibrated probabilities are distinct here, so it never fires — but it would fire loudly rather than silently dropping bins if a future model produced tied scores.

### Why this fix over the alternatives

- **Raising the tolerance** (`np.allclose(..., rtol=1e-3)`) makes the symptom go away and destroys the check. An assertion that passes regardless of which binning rule was used is not testing anything; the whole point of this cross-check is to catch a stale or regenerated upstream artifact.
- **Dropping the cross-check** loses the only mechanism connecting notebook 5's calibration story to the table notebook 4 exported.
- **Matching `qcut`** makes the two artifacts byte-comparable, lets the assertion be *stricter* than it was, and costs one line.

### Prevention

- The eight-line comment stays in the cell. Without it, a reader "simplifies" the `qcut` call back to a manual rank-and-floor and reintroduces the failure.
- **Scope check:** any other place where notebook 5 recomputes an aggregate that an earlier notebook already exported is exposed to the same class of bug. Currently that is one other site — the `np.allclose` against `04_test_metrics.csv` in Cell 5 — and it is safe, because PR-AUC and precision@k have no binning step and no remainder to distribute.
- The general shape is worth remembering rather than the specific fix: **two notebooks computing "the same" equal-count bins over a row count that doesn't divide evenly will disagree**, and the disagreement will be small enough to look like a floating-point problem and large enough to fail a default-tolerance assert.

### Cost

About ten minutes, most of it spent testing candidate binning rules (`qcut`, `qcut` on ranks, `np.array_split`, `searchsorted` on quantiles) against notebook 4's exported bin sizes to identify which one it had used. Three of the four reproduce the target exactly; `np.array_split` does not.

---

## Template for the next entry

```markdown
## BLK-00N — <one-line title>

| | |
|---|---|
| **Date** | |
| **Where** | notebook / file / cell |
| **Severity** | Low / Medium / High |
| **Status** | 🔴 Open / 🟡 Worked around / ✅ Resolved |

### Symptom
What was observed, verbatim where possible (error text, wrong number, wrong chart).

### Root cause
What was actually wrong — not the first hypothesis, the confirmed one. Note explicitly
if the error message pointed somewhere misleading.

### Fix applied
The code or decision that resolved it.

### Why this fix over the alternatives
What else was tried or considered, and why it lost.

### Prevention
The assert, comment, or check that stops a recurrence. Say which other parts of the
project share the same failure surface, and which don't.

### Cost
Time lost, and whether any artifact or number downstream was affected.
```

---

## Candidates to watch (not yet blockers)

Named here so that if they do fire, the diagnosis starts from a hypothesis instead of a blank page.

**Cleared:**

- ~~**Notebook 3 — trailing-feature leakage.**~~ The 40-customer check ran and passed: 39 stale customers found (one short of spec §3.2.1's 40, explained by notebook 1's dropped duplicate/orphan rows), and every time-gated value is ≤ the ungated truth with strict inequality somewhere. `feature_engineering.md` §5.
- ~~**Notebook 4 — calibration silently not running.**~~ Checked and passed. In the rebuilt notebook the reload check scores the same test row at 0.00338 through `main_model.joblib` against 0.00775 through `calibrated_model.joblib`, and an explicit `assert not np.allclose(...)` guards the whole column. Note the stronger check that replaced it: `proba_calibrated` must have **identical PR-AUC** to `proba_selected` (monotone map) while having **different values** — see BLK-008.
- ~~**Notebook 4 — the main model overfits.**~~ Train/test PR-AUC ratio went from 9.9 to 1.30 after the capacity sweep. BLK-006.
- ~~**Notebook 5 — Brier score worsening after calibration.**~~ Measured in notebook 4 ahead of schedule: 0.008583 (tuned HGB) → 0.008567 (deployed). But read BLK-008's prevention note before quoting it — the *raw* selected model scores 0.008535, fractionally better than its own calibrated version, so the sentence has to name which comparison it means.

- ~~**Notebook 5 — the threshold sweep's grid is mostly empty.**~~ Confirmed and fixed. Notebook 5 measured it directly: **67 of the 100** points in `np.linspace(0.01, 0.99, 100)` flag zero transactions against a `max_proba` of 0.3344. Replaced with 101 points drawn from quantiles of the score, and the definition of done now asserts `(threshold_sweep_df["n_flagged"] > 0).all()` so an empty grid point can never reach an export again. `model_evaluation.md` §4.5.
- ~~**Notebook 5 — the confusion matrix at 0.5 is empty.**~~ Half right, and the other half is more interesting. Three of the four columns predict **zero** positives at 0.5, as predicted — but `proba_baseline` predicts **8,736** (19.3% of the test set, 3.3% precision), because `class_weight='balanced'` inflated its scale by roughly 50× (BLK-007). So 0.5 is uninformative for the deployed model and actively misleading for the baseline, in opposite directions. The note's original wording — "zero predicted positives for every model" — was wrong on the one column that matters for the failure narrative. Reported instead at the operating threshold 0.02443. `model_evaluation.md` §4.6.
- ~~**Notebook 5 — Brier score is nearly meaningless at this base rate.**~~ Resolved by reporting the skill score alongside it in `05_model_comparison.csv`. The deployed model scores **+3.90%** against the constant-rate reference. The number this surfaced that the note did not anticipate: `proba_baseline`'s skill score is **−14.75**, i.e. the prescribed baseline is fifteen times worse than emitting the base rate on every row. That is the most legible single statement of BLK-007 and it belongs in `FAILURES.md`.
- ~~**Notebook 5 — an unbalanced-looking segment economics table.**~~ The expected finding showed up, but only after a methodology change: a threshold optimised *within* a segment is non-negative by construction, so that column alone can never identify a bad segment. Segments are now evaluated at the **global** policy and decomposed into review and step-up halves. Result: `method = wallet`'s review band nets **−₹300** (1 review, 0 catches) while its step-up band earns ₹9,779. `model_evaluation.md` §4.9.

**Still open:**

- **Notebook 5 — the economics layer is systematically conservative.** Unchanged and confirmed in `05_calibration_curve.csv`: the deployed model under-predicts in decile 9 by +1.15pp (3.93% predicted, 5.08% observed), and the top-5% slice predicts 5.52% against an observed 7.78%. Every rupee figure is therefore a floor, not an estimate. This errs in the safe direction — a model over-predicting at the top would be the dangerous one — but it stays on this list until `METRICS.md` states it next to the first rupee figure rather than leaving a reader to discover it.
- **Notebook 5 — two sensitivity columns are not comparable across rows.** New, found while reading `05_sensitivity_analysis.csv`. `dispute_fee` and `ops_review_cost` both appear inside `fn_cost = amount + dispute_fee + ops_review_cost`, so raising either raises the do-nothing baseline that `net_savings_inr` is measured *against*. Their net-savings columns therefore rise even where the policy gets **worse**: at `ops_review_cost = 800` the net saving reads ₹1,269,369 against ₹1,199,620 at ₹300, but total cost actually rose by ₹133,751 — the baseline just rose by ₹203,500. `merchant_margin` and `step_up_abandon_rate` do not appear in `fn_cost`, so those rows *are* comparable, which fortunately includes the one parameter dev plan §6.2 step 10 singled out. Anyone reading the CSV without this note will conclude that paying reviewers more saves money. Either add a `total_cost_inr` column to the export or carry the caveat into `METRICS.md`.
- **Notebook 5 / METRICS.md — 72% of the test label is post-snapshot.** Measured in `05_censoring_audit.csv`: **294 of 407** test positives were raised after 2026-11-01, latest 2027-01-26. This does not bias the ranking (every feature is time-gated, notebook 3's tripwire passed) but it scales every rupee figure to an exposure a real operator could not yet have observed. Predicted by `feature_engineering.md` §7.4 and `eda.md` §6.1; stays open until it is written into `METRICS.md` in plain language.
- **App — `joblib.load()` failing on Streamlit Cloud after working locally.** A `scikit-learn` version mismatch against the version that pickled the model. The three current pickles were written by **`scikit-learn 1.7.2`** — pin that exactly in `requirements.txt`, per dev plan §1.2 and §10.3, and record `joblib` and `numpy` from the same environment. `04_model_card.csv` now carries the `sklearn_version` used at fit time so the pin can be checked rather than remembered. One thing got easier: the deployed `calibrated_model.joblib` is now a logistic pipeline plus a one-parameter sigmoid — kilobytes, not the megabytes the three-fold HGB ensemble weighed.
- **App — `04_feature_columns.csv` drifting from the fitted model.** The app builds its feature row from that file's `order` column. The width is now pinned at 26 and derived entirely from `03_feature_knowability.csv`'s `model_role`, with no toggle and no append (BLK-004), so the drift risk is much lower than it was — but the app should still assert its loaded column count against the model before scoring anything rather than misaligning silently.
- **App — the reviewer note quoting a meaningless feature.** Eighteen of 26 features fail the 2σ screen in `04_feature_importances.csv` and six score ≤ 0. `app/explain.py` must filter on `informative == True` before naming a driver, or it will confidently tell a reviewer that a shuffled-noise column drove the score. One upside of shipping a logistic regression: `04_model_coefficients.csv` gives real per-term contributions, so the note can be built from coefficient × standardised value rather than the SHAP-free approximation LLD §5.2 was hedging toward.
