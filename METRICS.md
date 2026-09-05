# ChargebackLens — Metrics

## 1. Evaluation contract

The final evaluation uses a temporally separated test set and the deployed probability column:

```text
proba_calibrated
```

This is the selected unweighted Logistic Regression model followed by a prefit sigmoid calibration.

The test set contains:

- **45,246 transactions**
- **407 disputes**
- **0.8995% dispute base rate**

The final evaluation notebook ran top-to-bottom without error, all 10 definition-of-done checks passed, and all nine output CSVs were exported and round-trip verified.

---

## 2. Headline results

| Metric | Result |
|---|---:|
| Deployed model | **LR_plain + prefit sigmoid** |
| Features | **26** |
| Test transactions | **45,246** |
| Test positives | **407** |
| Test base rate | **0.8995%** |
| Test PR-AUC | **0.08725** |
| PR-AUC lift over base rate | **9.70×** |
| Precision @ top 1% | **14.60%** |
| Lift @ top 1% | **16.23×** |
| Precision @ top 5% | **7.78%** |
| Recall @ top 5% | **43.24%** |
| Brier score | **0.008567** |
| Constant-rate Brier reference | **0.008914** |
| Brier skill score | **+3.90%** |
| Log loss | **0.042857** |
| Maximum calibrated probability | **0.3344** |
| Expected calibration error | **0.00185** |
| Net savings at deployed policy | **₹1,199,620** |
| Do-nothing cost | **₹3,069,547** |
| Binary-policy net savings | **₹1,080,993** |
| Three-band improvement | **+₹118,627** |
| Test positives raised after snapshot | **294 / 407 (72.2%)** |

---

## 3. Model comparison

The four probability columns produced during model development are:

| Probability column | Model | PR-AUC | Lift @ 1% | Precision @ 5% | Brier | Brier skill | Max p |
|---|---|---:|---:|---:|---:|---:|---:|
| `proba_baseline` | LR, `class_weight='balanced'` | 0.0842 | 17.2× | 7.69% | 0.1404 | **−14.75** | 0.991 |
| `proba_main` | Tuned HGB | 0.0812 | 15.5× | 7.21% | 0.0086 | +0.0371 | 0.399 |
| `proba_selected` | Unweighted LR, uncalibrated | 0.0872 | 16.2× | 7.78% | 0.0085 | +0.0426 | 0.474 |
| **`proba_calibrated`** | **Unweighted LR + sigmoid** | **0.0872** | **16.2×** | **7.78%** | **0.0086** | **+0.0390** | **0.334** |

The selected and calibrated columns have identical ranking metrics and different probability values. That is the expected signature of the monotone calibration transform.

The prescribed weighted baseline has good ranking performance but unusable probability scale: its Brier score is 0.1404 against a constant-rate reference of 0.008914, producing a Brier skill score of **−14.75**.

---

## 4. Generalization and model selection

The first prescribed HistGradientBoosting configuration overfit substantially:

| Model | Train PR-AUC | Test PR-AUC | Train/Test ratio |
|---|---:|---:|---:|
| Prescribed HGB | 0.5130 | 0.0517 | **9.9** |
| Tuned HGB | 0.1055 | 0.0812 | **1.30** |
| Deployed LR + sigmoid | 0.0705 | 0.0872 | **0.81** |

The tuned HGB improved test PR-AUC from **0.0517 to 0.0812**, but remained below the selected Logistic Regression model at **0.0872**.

The final model selection therefore favoured the simpler additive model after held-out evidence showed that the boosted model's additional complexity did not provide a reliable advantage.

---

## 5. Calibration

Calibration was evaluated on temporally separated data.

### Decile reliability

| Model | ECE | Worst bin gap |
|---|---:|---:|
| `main_hgb` | 0.00137 | +0.00795 |
| `calibrated` | 0.00185 | **+0.01153** |

Nine of ten deciles track within approximately ±0.0022.

The highest-risk decile predicts approximately **3.93%** against an observed **5.08%**, an under-prediction of approximately **1.15 percentage points**.

The important conclusion is not that calibration improved every reliability metric. It did not.

The defensible conclusion is:

> **Sigmoid calibration corrected the probability scale from a maximum of approximately 0.474 to 0.334 while preserving ranking exactly.**

The raw selected model's Brier score was 0.008535, fractionally better than its calibrated value of 0.008567. Therefore the project does not claim that calibration improved the selected model's Brier score.

---

## 6. Why PR-AUC is the headline ranking metric

The test dispute base rate is approximately **0.9%**.

With 44,839 non-disputed transactions in the test set, ROC-AUC can look strong while saying relatively little about the precision achievable in the small portion of the queue that a risk team can actually review.

ChargebackLens therefore emphasizes:

- PR-AUC
- Precision at top 1%
- Precision at top 5%
- Lift

ROC-AUC was computed diagnostically but deliberately excluded from the headline metrics.

---

## 7. Operating policy

The final policy uses two jointly optimized thresholds:

```text
Allow → Step-up       0.024425
Step-up → Review      0.082395
```

This produces:

| Band | Probability range | Transactions | Share | Disputes | Dispute rate | Lift vs base |
|---|---|---:|---:|---:|---:|---:|
| Allow | < 0.02443 | 42,152 | 93.2% | 204 | 0.484% | 0.54× |
| Step-up | 0.02443 – 0.08240 | 2,786 | 6.2% | 151 | 5.42% | 6.03× |
| Manual Review | ≥ 0.08240 | 308 | 0.7% | 52 | 16.88% | 18.77× |

At the operating threshold used for the policy:

```text
41,948 true negatives
 2,891 false positives
   204 false negatives
   203 true positives
```

Precision is approximately **6.56%** and recall is approximately **49.88%**.

Operationally, this means:

> **2,891 legitimate customers see friction to catch 203 disputes.**

That trade-off is evaluated economically rather than treated as a purely statistical classification decision.

---

## 8. Binary policy versus three-band policy

The binary threshold sweep produces:

| | Value |
|---|---:|
| Optimal threshold | approximately 0.024 |
| Flagged | 3,168 (7.00%) |
| Precision | 6.44% |
| Recall | 50.12% |
| Net savings | **₹1,080,993** |

The three-band policy produces:

| | Binary | Three-band |
|---|---:|---:|
| Net savings | ₹1,080,993 | **₹1,199,620** |
| Improvement | — | **+₹118,627** |

The three-band policy therefore provides measured economic justification for separating medium-risk transactions from high-risk transactions rather than treating all flagged transactions identically.

---

## 9. Economics assumptions

The deployed policy uses:

```text
Dispute fee             = ₹1,500
Operations review cost  = ₹300
Merchant margin         = 18%
Step-up abandonment     = 25%
```

The cost model distinguishes:

### Manual review

```text
₹300 operations cost
```

for both disputed and non-disputed transactions that enter review.

### Step-up

For a legitimate transaction:

```text
amount × merchant margin × abandonment rate
```

For a disputed transaction, the model assumes the step-up deters the disputing party and therefore avoids the dispute cost.

### Allow

For a disputed transaction:

```text
amount + dispute fee + operations cost
```

For a non-disputed transaction:

```text
₹0 incremental cost
```

The three-band policy is optimized jointly under these assumptions.

---

## 10. Sensitivity analysis

The most important sensitivity parameter is the step-up abandonment rate.

| Step-up abandonment | Allow → Step-up | Step-up → Review | Reviews | Step-ups | Net savings |
|---:|---:|---:|---:|---:|---:|
| 10% | 0.01429 | 0.14601 | 41 | 6,255 | ₹1,811,639 |
| 20% | 0.02434 | 0.11350 | 108 | 3,004 | ₹1,333,030 |
| **25%** | **0.02443** | **0.08240** | **308** | **2,786** | **₹1,199,620** |
| 30% | 0.04400 | 0.05388 | 794 | 428 | ₹1,098,732 |
| 40% | 0.04441 | 0.04496 | 1,164 | 33 | ₹1,087,874 |

The conclusion is robust:

> Net savings remain positive across the tested abandonment range.

The operating point is not robust:

```text
Allow → Step-up:
0.0143 → 0.0444
```

This is approximately a **3.1× movement**.

Therefore, `step_up_abandon_rate` should be measured from real merchant/customer behaviour before production deployment rather than treated as a permanent model constant.

### Sensitivity-table caveat

`dispute_fee` and `ops_review_cost` are included in the false-negative cost and therefore change the do-nothing baseline against which `net_savings_inr` is measured.

Consequently, their net-savings values are **not directly comparable across rows**.

For example, at `ops_review_cost = 800`, the reported net saving is ₹1,269,369 versus ₹1,199,620 at ₹300, while actual total cost increased by ₹133,751.

Net-savings comparisons are valid across the `merchant_margin` and `step_up_abandon_rate` rows, but not directly across `dispute_fee` or `ops_review_cost` rows unless the baseline is held fixed or total cost is compared.

---

## 11. Segment economics

Segment economics are evaluated under the **global deployed policy**.

This matters because optimizing a threshold separately within each segment guarantees a non-negative result: the do-nothing policy is always available.

ChargebackLens therefore evaluates:

- Amount buckets
- Merchant categories
- Payment methods

and decomposes the global result into review and step-up bands.

Selected results:

| Segment | n | Mean amount | Savings / intervention | Review band net | Reviews |
|---|---:|---:|---:|---:|---:|
| `method = wallet` | 4,063 | ₹676 | ₹47 | **−₹300** | 1 |
| `merchant_category = ticketing` | 4,561 | ₹825 | ₹50 | ₹1,890 | 25 |
| `amount < ₹500` | 15,434 | ₹262 | ₹78 | ₹3,280 | 4 |
| `merchant_category = travel` | 4,529 | ₹12,155 | ₹1,094 | ₹455,369 | 163 |
| `method = emi` | 1,856 | ₹13,966 | ₹1,294 | ₹206,358 | 57 |
| `amount > ₹10,000` | 2,288 | ₹18,859 | ₹1,434 | ₹417,582 | 128 |

The key finding is:

> **Manual review on wallet traffic nets −₹300 — one review, zero catches.**

However, the wallet segment as a whole is not necessarily unprofitable:

```text
Wallet step-up band net = ₹9,779
Wallet review band net   = −₹300
```

Therefore the sharper recommendation is:

> **Route the review queue by ticket size.**

The economics are especially attractive for higher-ticket transactions:

```text
amount > ₹10,000
Savings per intervention ≈ ₹1,434
```

compared with:

```text
wallet
Savings per intervention ≈ ₹47
```

The higher-ticket intervention is therefore approximately **31×** as valuable per intervention.

---

## 12. Censoring caveat

The largest limitation on the absolute economic figures is label censoring.

The audit found:

| Measure | Value |
|---|---:|
| Test positives | 407 |
| Raised after snapshot | **294** |
| Share after snapshot | **72.2%** |
| `raised_at` values nulled by Notebook 1 | 4 |
| Latest observed `raised_at` | 2027-01-26 03:45:10 |

Nearly three-quarters of the test positives would not have been observable to an operator standing on the declared snapshot date.

This does **not** bias the ranking because the feature pipeline is time-gated and its leakage tripwire passed.

It does mean that the labels include roughly three months of future disputes. Therefore:

> **The absolute rupee figures should be treated as a floor rather than a point estimate of what a real merchant could have measured at the snapshot date.**

This caveat should be read alongside every economic conclusion.

---

## 13. Application sample

The Streamlit Risk Queue uses:

```text
05_scored_test_sample.csv
```

with **5,000 rows**.

The sample is intentionally stratified:

```text
4,406 Allow
286 Step-up
308 Manual Review
83 Disputes
```

All 308 manual-review rows are retained, with the remaining rows sampled from the other actions.

This is useful for demonstrating the queue, but it has an important implication:

> **The sample's dispute rate is not the population dispute rate.**

The application should not present the sample's observed dispute rate as if it were the test-set or population rate.

---

## 14. Feature importance

Permutation importance is evaluated against average precision on the held-out validation block.

The exported table contains:

- `feature_name`
- `importance`
- `importance_std`
- `rank`
- `informative`

The `informative` flag is a 2σ screen.

Of the 26 features:

- **18 fail the 2σ informative screen**
- **6 have importance ≤ 0**

Examples include:

```text
account_age_implausible
day_of_week
prior_disputes_before_this_txn
amount_vs_own_avg
txns_last_24h
checkout_latency_ms
```

The substitute feature:

```text
ip_state_changed_from_prev_txn
```

has:

```text
importance = +0.000012
importance_std = 0.000809
rank = 19 / 26
```

This is consistent with the synthetic data generation process and should not be described as meaningful predictive signal.

The application explanation layer must therefore use only features marked:

```text
informative == True
```

---

## 15. Definition of done

The final evaluation passed all 10 checks:

- [x] Deployed PR-AUC beats the prescribed baseline
- [x] Calibration improves Brier versus the tuned HGB
- [x] Brier skill score is positive
- [x] Threshold grid is fully populated
- [x] Two policy thresholds are correctly ordered
- [x] Net savings are positive
- [x] At least one segment contains an uneconomic review band
- [x] Scored sample is ≤ 5,000 rows
- [x] Scored sample contains the columns required by the application
- [x] All nine evaluation exports were written and round-trip verified

**10 of 10 passed.**

---

## 16. What the metrics do and do not establish

The results establish that, on the supplied temporally separated test data:

1. The selected model ranks disputes meaningfully above the base rate.
2. The calibrated probability has a usable scale for the economics layer.
3. A three-band policy produces more realized savings than the evaluated binary policy under the current assumptions.
4. Economic value varies substantially by transaction segment.
5. The exact operating thresholds are sensitive to customer-friction assumptions.

They do **not** establish production performance.

The results should not be interpreted as:

- A live fraud-loss forecast
- A production authorization guarantee
- A production ROI estimate
- Evidence that the policy should be deployed unchanged
- Evidence that the synthetic/pre-generated dataset represents a real merchant population

The project is a **decision-support prototype** whose main claim is architectural:

> **A calibrated risk probability becomes more useful when it is connected explicitly to operational policy and economic consequences.**
