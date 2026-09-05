# ChargebackLens — Scope

## 1. Problem statement

A merchant on a payments platform loses money to chargebacks in three ways at once: the disputed transaction amount, a fixed dispute fee charged regardless of outcome, and the operational cost of responding to the case. A plain fraud classifier only addresses the first of these, and it ignores the fact that **blocking a legitimate customer also costs money** — a customer forced into a step-up verification has some probability of abandoning the purchase entirely.

**ChargebackLens exists to answer one question a merchant actually has:** given a transaction, what is the rupee-optimal action — allow it, step it up, or send it to manual review — and how confident should the merchant be in that recommendation?

This reframes the project from "build an accurate classifier" to "build a system that converts a probability into a bounded, explainable, economically-justified decision."

---

## 2. Objectives

### 2.1 Calibrated dispute-risk probability

Produce a calibrated probability of dispute risk and evaluate it honestly on data the model has not seen during training.

The model output is intended to be a probability, not merely a ranking score, because the downstream economics layer consumes the magnitude of that probability.

### 2.2 Rupee-denominated decision layer

Place a decision layer on top of the calibrated probability.

The current policy has three operational actions:

| Risk band | Action |
|---|---|
| Low risk | **Allow** |
| Medium risk | **Step-up** |
| High risk | **Manual Review** |

The policy is driven by two thresholds and evaluated using explicit economic assumptions.

### 2.3 Reviewer-facing application

Provide a Streamlit demo surface that allows a reviewer to:

- Understand what ChargebackLens does
- Browse a risk-ranked transaction queue
- Inspect transaction-level risk information
- Explore the economic consequences of policy assumptions
- Access the planned transaction-scoring surface

The current application navigation is:

```text
Home
│
├── Risk Queue
├── Economics
└── Score Transaction
      └── Under Development
```

The live transaction-scoring interface is the next development stage.

### 2.4 Narrow LLM explanation layer

Use an LLM only for one bounded explanatory task: generating a short factual reviewer note from an already-computed decision and its relevant risk signals.

The LLM does **not** determine:

- Risk probability
- Features
- Thresholds
- Economic optimization
- Operational classification

A deterministic offline fallback is maintained so the core application does not depend on an external API.

---

## 3. Data scope

ChargebackLens operates on five fixed, pre-generated CSV inputs:

```text
transactions.csv
customers.csv
merchants.csv
fulfilment.csv
disputes.csv
```

The raw CSVs are a **read-only input contract**.

No component in the system generates or modifies the raw data.

The data pipeline performs:

```text
Load
  ↓
Validate
  ↓
Clean / Deduplicate
  ↓
Label
  ↓
Feature Engineering
  ↓
Temporal Split
  ↓
Model Training
  ↓
Calibration
  ↓
Evaluation
  ↓
Economics
  ↓
Frozen Artifacts
  ↓
Streamlit Application
```

The cleaned master table contains 119,988 rows and 24 columns, with 1,050 positive disputes and a 0.8751% base dispute rate. All 20 defined data-quality checks passed.

---

## 4. Feature scope

The model uses features that are knowable at the point of decision.

This is a first-class constraint because several fields in the source data, particularly fulfilment information such as delivery status and delivery timestamps, are only knowable after the decision window.

Feature engineering therefore includes:

- Instant transaction features
- Customer-level features
- Merchant-level features
- Leakage-safe trailing behavioural features
- Temporal feature construction
- Feature knowability tagging

The final modelling contract contains **26 features**.

A temporal train/test split is used with:

```text
SPLIT_DATE = 2026-08-01
```

The feature pipeline uses time-gated historical information and explicitly excludes post-decision information.

---

## 5. Modelling scope

The modelling phase includes:

- Baseline Logistic Regression
- HistGradientBoostingClassifier
- Hyperparameter search
- Model comparison
- Model selection
- Probability calibration
- Permutation-based feature importance
- Frozen model artifact export

The final deployed scorer is:

```text
Unweighted Logistic Regression
        +
Prefit Sigmoid Calibration
```

The model is selected using held-out validation evidence rather than complexity as an objective.

The test set is kept separate from model selection and is used for final evaluation after the modelling decisions are complete.

---

## 6. Evaluation scope

The evaluation layer reports metrics appropriate to the approximately 0.9% dispute base rate.

Primary metrics include:

- PR-AUC
- Precision at top 1%
- Precision at top 5%
- Lift
- Brier score
- Brier skill score
- Log loss
- Calibration / reliability
- Train/test generalization gap

ROC-AUC may be computed diagnostically, but it is deliberately not treated as a headline metric because the extreme class imbalance makes it less informative for the operational problem.

---

## 7. Economics scope

The economics layer converts calibrated probabilities into operational decisions and evaluates their financial consequences.

The baseline economic assumptions are:

```text
Dispute fee             = ₹1,500
Operations review cost  = ₹300
Merchant margin         = 18%
Step-up abandonment     = 25%
```

The economics layer includes:

- Binary threshold sweep
- Joint optimization of two policy thresholds
- Allow / Step-up / Manual Review policy
- Sensitivity analysis
- Segment-level economics
- Review-band and step-up-band decomposition

The economics layer is downstream of model calibration and does not depend on model internals.

---

## 8. Application scope

The Streamlit application consumes frozen processed artifacts.

The application is designed to:

- Load the calibrated model once
- Load read-only application artifacts
- Display the risk queue
- Display policy/economic analysis
- Provide a Home page explaining the system
- Provide a planned transaction-scoring surface

The application must not retrain the model.

The application must not write to the raw data directory.

The live transaction-scoring page is currently under development and is intentionally not presented as a functioning production scorer.

---

## 9. Explanation scope

The explanation component receives already-computed information and generates a concise reviewer note.

Its role is:

```text
Risk probability
      +
Policy decision
      +
Relevant risk signals
      ↓
Reviewer note
```

The explanation layer is optional from an infrastructure perspective. If the Anthropic API is unavailable or no API key is present, a deterministic fallback is used.

---

## 10. Explicit non-objectives

The following are explicitly outside the scope of ChargebackLens.

### 10.1 Production payment authorization

ChargebackLens is a decision-support system evaluated on historical data.

It is **not** a live production authorization gate.

There is no real-time integration with a live payments system.

### 10.2 Data generation

The five CSVs are fixed, pre-generated inputs.

No component writes to:

```text
data/raw/
```

### 10.3 Offensive or evasion functionality

The project does not include:

- Evasion testing
- Adversarial example generation
- Detection bypass techniques
- Functionality that could help a bad actor avoid detection

This is a hard architectural boundary.

### 10.4 Automated production retraining

The project does not currently include:

- Automated model retraining
- Model registry infrastructure
- Automated model refresh
- Production drift-monitoring infrastructure

These are potential future production extensions, not part of the current system.

### 10.5 Full fraud platform

ChargebackLens is specifically scoped to **chargeback/dispute risk**.

It is not intended to become a general-purpose fraud detection platform.

### 10.6 LLM-controlled decisions

The LLM cannot:

- Score transactions
- Select features
- Choose thresholds
- Optimize economics
- Override the policy

Its responsibility is limited to explanation.

---

## 11. Architecture boundary

The project is deliberately split into two phases.

### Offline phase

```text
Raw CSVs
   ↓
Jupyter notebooks
   ↓
Training / calibration / evaluation
   ↓
Frozen artifacts
```

### Online phase

```text
Frozen artifacts
   ↓
Streamlit
   ↓
Risk Queue / Economics / Transaction Scoring
   ↓
Optional reviewer-note generation
```

The notebook owns training and evaluation.

The application consumes the resulting artifacts.

This separation exists for reproducibility, speed, auditability, and clear separation of responsibilities.

---

## 12. Non-functional requirements

### Reproducibility

A single random seed is used throughout the stochastic parts of the modelling pipeline.

```text
RANDOM_SEED = 42
```

### Auditability

The project maintains:

- Explicit data-quality checks
- Feature knowability metadata
- Temporal split assertions
- Artifact round-trip checks
- Model comparison artifacts
- Threshold and economics artifacts
- A blockers/failures record

### Application latency

The application must not retrain models or repeatedly process the raw data.

Its normal per-request workload is limited to artifact access, inference, deterministic decision logic, economics calculations, and optionally one external explanation call.

### Graceful degradation

The explanation layer has an offline fallback.

The core risk queue and economics functionality do not depend on the LLM being available.

---

## 13. Current implementation boundary

### Implemented

- Data cleaning and validation
- Label construction
- Leakage-safe feature engineering
- Temporal splitting
- Model training and selection
- Calibration
- Final test evaluation
- Threshold optimization
- Three-band economics
- Sensitivity analysis
- Segment economics
- Risk Queue
- Economics application surface
- Home page

### Under development

- Live transaction scoring
- Final production-style scoring contract between the feature pipeline and Streamlit
- Transaction-specific reviewer explanation integrated into the scoring workflow

---

## 14. Future boundary

If ChargebackLens is extended toward production, the natural architectural evolution is:

```text
Versioned Model Registry
        +
Feature Service
        +
Transaction Event Stream
        +
Monitoring
        +
Production Policy Controls
```

The current offline/online separation should remain intact.

The project should grow by replacing the demo-scale artifact interfaces, not by collapsing training, evaluation, and serving back into one application script.
