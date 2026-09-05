# ChargebackLens

### Transaction Dispute-Risk Decision Engine

> **From probability to policy to economics.**

[![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B?logo=streamlit)](https://streamlit.io/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-ML-F7931E?logo=scikit-learn)](https://scikit-learn.org/)
[![Plotly](https://img.shields.io/badge/Plotly-Visualization-3F4F75?logo=plotly)](https://plotly.com/python/)

**Live Demo:** [Coming Soon — Deployed Link](#)

---

## Overview

ChargebackLens is a **chargeback/dispute-risk decision engine** designed to answer a practical question faced by payment and risk teams:

> **Given a transaction, what is the economically sensible action — allow it, step it up, or send it for manual review?**

The project goes beyond building a binary classifier.

It combines:

1. **Calibrated dispute-risk probability**
2. **Operational risk policy**
3. **Rupee-denominated economics**
4. **Reviewer-oriented risk prioritization**
5. **A narrowly scoped AI explanation layer**

The central idea is simple:

```text
Transaction
     ↓
Risk Probability
     ↓
Operational Decision
     ↓
Economic Consequence
     ↓
Reviewer Explanation
```

ChargebackLens is intentionally built as a **decision-support system**, not as a production payment authorization system.

---

## Why ChargebackLens?

A chargeback creates multiple costs for a merchant:

- The disputed transaction amount
- A fixed dispute fee
- Operational cost of handling the dispute

However, intervention also has a cost.

For example, forcing a legitimate customer through an additional verification step can cause abandonment. Sending every suspicious transaction to a human reviewer can also be more expensive than the dispute exposure it prevents.

Therefore, the objective is not simply:

> "Predict whether this transaction will be disputed."

It is:

> **"Estimate the probability of dispute accurately enough to make an economically justified decision."**

This distinction drives the architecture of the entire project.

---

# Objectives

ChargebackLens has four primary objectives.

### 1. Produce a calibrated probability

The model should output a probability that can be interpreted as a probability of dispute, rather than merely an arbitrary ranking score.

### 2. Convert probability into an operational policy

The probability is translated into three decision bands:

| Risk band | Operational action |
|---|---|
| Low | **Allow** |
| Medium | **Step-up** |
| High | **Manual Review** |

Two thresholds are used instead of a binary allow/block rule because different levels of risk warrant different amounts of customer friction and operational effort.

### 3. Evaluate decisions economically

The system estimates the cost and savings associated with intervention using explicit assumptions such as:

- Dispute fee
- Operations/review cost
- Merchant margin
- Step-up abandonment rate

The goal is to identify the operating policy that maximizes estimated net savings.

### 4. Make the result understandable to a reviewer

The application is designed to surface the relevant risk signals behind a transaction-level decision rather than presenting an unexplained probability.

---

# Current Status

## ✅ Completed

- Data cleaning and validation
- Transaction/customer/merchant/dispute processing
- Label construction
- Leakage-safe feature engineering
- Feature knowability analysis
- Temporal train/test splitting
- Baseline model development
- Main model development
- Model selection
- Probability calibration
- Test-set evaluation
- Threshold optimization
- Three-band policy optimization
- Economics analysis
- Sensitivity analysis
- Segment-level economics
- Feature importance analysis
- Frozen model/artifact export
- Streamlit Risk Queue
- Streamlit Economics interface
- Streamlit Home page
- Project documentation

## 🚧 Under Development

### Live Transaction Scoring

The Streamlit interface for entering a new transaction and obtaining a live:

```text
Transaction Input
       ↓
Feature Construction
       ↓
Calibrated Probability
       ↓
Risk Band
       ↓
Economic Decision
       ↓
Reviewer Explanation
```

is the next application stage.

The page is already present in the application as an **Under Development** surface.

---

# Model Results

The final deployed scorer is an **unweighted Logistic Regression model with sigmoid calibration**.

The model was selected after comparing prescribed and tuned candidates on temporally separated validation data.

### Headline test-set results

| Metric | Result |
|---|---:|
| Features | **26** |
| Base dispute rate | **0.8995%** |
| Test PR-AUC | **0.0872** |
| Precision @ top 1% | **14.6%** |
| Lift @ top 1% | **16.2×** |
| Precision @ top 5% | **7.78%** |
| Brier score | **0.008567** |
| Expected Calibration Error | **0.00185** |

The dataset is highly imbalanced, with disputes representing roughly 0.9% of transactions.

For this reason, **PR-AUC and precision at operational review capacities** are treated as the primary ranking metrics rather than ROC-AUC.

---

# Why Calibration Matters

The economics layer consumes probabilities directly.

An arbitrary model score cannot safely be multiplied by a transaction amount and interpreted economically.

ChargebackLens therefore calibrates the selected model before its probabilities are passed to the economics layer.

The deployed model's maximum calibrated probability is approximately:

```text
0.334
```

The calibration results also show that the model is slightly conservative in the highest-risk region.

For example:

```text
Top 5% predicted risk:
Predicted dispute rate ≈ 5.52%
Observed dispute rate  ≈ 7.78%
```

This means the resulting economic estimates should be interpreted as **conservative decision estimates**, rather than precise forecasts of future savings.

---

# Model Selection

ChargebackLens deliberately does not assume that a more complex model is automatically better.

The project evaluated both linear and gradient-boosted approaches.

The final deployed scorer is:

```text
Logistic Regression
        +
Sigmoid Calibration
```

rather than the more complex HistGradientBoosting model.

This decision was driven by held-out validation evidence.

The tuned HGB model showed substantially greater train/test separation and did not outperform the selected linear model on the final test metrics.

This is an intentional design decision:

> **Model complexity is justified by measured generalization improvement, not by model sophistication alone.**

---

# Data Pipeline

The project uses five pre-generated source tables:

```text
transactions.csv
customers.csv
merchants.csv
fulfilment.csv
disputes.csv
```

The raw data is treated as a **read-only input contract**.

The processing pipeline is:

```text
Raw CSVs
   │
   ▼
Data Validation & Cleaning
   │
   ▼
Label Construction
   │
   ▼
Leakage-Safe Feature Engineering
   │
   ▼
Temporal Train/Test Split
   │
   ▼
Model Training
   │
   ▼
Calibration
   │
   ▼
Evaluation
   │
   ▼
Economics & Threshold Optimization
   │
   ▼
Frozen Artifacts
   │
   ▼
Streamlit Application
```

---

# Leakage Prevention

Chargeback prediction contains a particularly important leakage risk.

Some information, especially fulfilment information such as:

- delivery status
- delivery timestamps

may only become available after the point at which a dispute-risk decision would need to be made.

ChargebackLens therefore uses an explicit **feature knowability** framework.

Each feature is evaluated according to when it becomes knowable.

The model is trained only on information that would be available at the decision point.

The project also uses a **temporal split** rather than a random split:

```text
Earlier transactions
       │
       ▼
Training data

Later transactions
       │
       ▼
Test data
```

The temporal boundary used in the modelling pipeline is:

```text
2026-08-01
```

This prevents future behaviour from being randomly mixed into the training data.

---

# Economics Layer

The economics layer is what turns ChargebackLens from a classification project into a decision engine.

The baseline assumptions are:

```text
Dispute fee             = ₹1,500
Operations review cost  = ₹300
Merchant margin         = 18%
Step-up abandonment     = 25%
```

The simplified cost model considers:

### False negative

A disputed transaction that was allowed:

```text
Transaction amount
+ dispute fee
+ operational cost
```

### False positive / step-up

A legitimate transaction subjected to step-up:

```text
Transaction amount
× merchant margin
× abandonment rate
```

### True positive / manual review

A correctly identified dispute sent for review:

```text
Operations review cost
```

### True negative

A legitimate transaction that is allowed:

```text
₹0 incremental cost
```

These costs are used to evaluate candidate thresholds.

---

# Three-Band Decision Policy

ChargebackLens uses two thresholds instead of one.

```text
                 Risk Probability
                       │
       ┌───────────────┼───────────────────┐
       │               │                   │
       ▼               ▼                   ▼
     ALLOW          STEP-UP          MANUAL REVIEW
       │               │                   │
    Low risk       Medium risk          High risk
```

At the current economic assumptions, the optimized operating points are approximately:

```text
Allow → Step-up       0.02443
Step-up → Review      0.08240
```

The three-band policy produces approximately:

```text
Net savings: ₹1,199,620
```

compared with approximately:

```text
Binary policy: ₹1,080,993
```

The three-band structure therefore provides an estimated improvement of:

```text
₹118,627
```

over the binary policy under the model's current assumptions.

---

# Sensitivity Analysis

Economic decisions depend on assumptions.

ChargebackLens therefore evaluates how the optimal policy changes when the step-up abandonment rate changes.

| Step-up abandonment | Allow → Step-up | Step-up → Review | Reviews | Step-ups | Net savings |
|---:|---:|---:|---:|---:|---:|
| 10% | 0.01429 | 0.14601 | 41 | 6,255 | ₹1,811,639 |
| 20% | 0.02434 | 0.11350 | 108 | 3,004 | ₹1,333,030 |
| **25%** | **0.02443** | **0.08240** | **308** | **2,786** | **₹1,199,620** |
| 30% | 0.04400 | 0.05388 | 794 | 428 | ₹1,098,732 |
| 40% | 0.04441 | 0.04496 | 1,164 | 33 | ₹1,087,874 |

The important takeaway is:

> The conclusion that intervention creates positive value is reasonably robust, but the exact operating threshold is sensitive to the abandonment assumption.

This is why the application exposes economics as an explicit decision layer rather than hiding the assumptions inside the model.

---

# Segment-Level Economics

A global policy can hide important differences between transaction segments.

ChargebackLens therefore evaluates economics across:

- Transaction amount buckets
- Merchant categories
- Payment methods

One of the most important findings is that **manual review is not economically attractive for every segment**.

For example:

```text
wallet traffic:
Manual-review net = −₹300
Reviews = 1
Disputes caught = 0
```

At the other end of the spectrum:

```text
Transactions > ₹10,000:
Savings per intervention ≈ ₹1,434
```

The resulting operational recommendation is not simply:

> "Deploy the model everywhere."

Instead:

> **Route review capacity according to ticket size and segment economics.**

For low-ticket and wallet traffic, step-up can still be economically useful while manual review may not be.

---

# Streamlit Application

The current Streamlit application is organized into four navigation surfaces:

```text
ChargebackLens
│
├── Home
├── Risk Queue
├── Economics
└── Score Transaction
```

---

## 1. Home

The Home page introduces:

- What ChargebackLens is
- The project objective
- The decision workflow
- The application surfaces
- The current policy snapshot

The intended mental model is:

```text
Transaction
     ↓
Risk
     ↓
Decision
     ↓
Economics
     ↓
Explanation
```

---

## 2. Risk Queue

The Risk Queue provides a reviewer-oriented view of pre-scored transactions.

Transactions are ranked by calibrated dispute probability.

The queue allows a reviewer to inspect:

- Payment ID
- Transaction time
- Amount
- Merchant category
- Payment method
- Calibrated risk
- Recommended action

A selected transaction can then be inspected in greater detail.

The application uses a stratified test-set sample rather than the complete test set so the demonstration contains sufficient high-risk transactions to make the queue useful.

The sample contains:

```text
4,406 Allow
286 Step-up
308 Manual Review
83 Disputes
```

**Important:** because the sample intentionally over-represents high-risk transactions, its observed dispute rate should not be interpreted as the population dispute rate.

---

## 3. Economics

The Economics interface is designed to answer:

> **What happens to the decision if our assumptions change?**

It surfaces:

- Current policy thresholds
- Policy-band volumes
- Dispute rates by band
- Threshold/savings relationships
- Sensitivity to economic assumptions
- Segment economics

This allows a reviewer to see that the model's output and the business decision are separate layers.

---

## 4. Score Transaction

The live transaction scoring interface is currently:

> **Under Development**

The intended implementation will accept transaction-level inputs and perform:

```text
Raw transaction inputs
        ↓
Feature construction
        ↓
Feature-order validation
        ↓
Calibrated model
        ↓
Dispute probability
        ↓
Three-band policy
        ↓
Economic interpretation
        ↓
Reviewer explanation
```

This page will be connected only after the production scoring contract is finalized.

---

# AI / LLM Component

The project uses an LLM deliberately and narrowly.

The LLM is **not responsible for**:

- Model scoring
- Feature selection
- Threshold selection
- Economic optimization
- Risk classification

Instead, the LLM is intended only for:

> **Generating a concise reviewer note explaining an already-computed decision.**

The architecture is:

```text
             Calibrated Model
                    │
                    ▼
             Risk Probability
                    │
                    ▼
             Policy Decision
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
      Economics          Top Risk Signals
                              │
                              ▼
                       Reviewer Note
                              │
                       ┌──────┴──────┐
                       │             │
                  Anthropic API   Deterministic
                     available       fallback
```

If an API key is unavailable or the external service fails, the application can fall back to deterministic explanation text.

This keeps the core decision system independent of an external LLM.

---

# Architecture

ChargebackLens intentionally separates the **offline modelling phase** from the **online application phase**.

```text
                    ┌──────────────────────┐
                    │   Raw CSV datasets   │
                    │     Read-only        │
                    └──────────┬───────────┘
                               │
                               ▼
                 ┌─────────────────────────┐
                 │      Jupyter Phase       │
                 │                         │
                 │  Clean                   │
                 │  Engineer                │
                 │  Split                   │
                 │  Train                   │
                 │  Calibrate               │
                 │  Evaluate                │
                 │  Optimize economics      │
                 └────────────┬────────────┘
                              │
                              ▼
                 ┌─────────────────────────┐
                 │   Frozen Artifacts      │
                 │                         │
                 │  Model                  │
                 │  Features               │
                 │  Predictions            │
                 │  Thresholds              │
                 │  Economics               │
                 │  Importances             │
                 └────────────┬────────────┘
                              │
                              ▼
                 ┌─────────────────────────┐
                 │     Streamlit App       │
                 │                         │
                 │  Home                   │
                 │  Risk Queue             │
                 │  Economics              │
                 │  Score Transaction*     │
                 └────────────┬────────────┘
                              │
                              ▼
                    Optional LLM Layer
                    Reviewer note only

                    * currently under
                      development
```

The Streamlit application does **not retrain the model**.

The raw data is not required by the application.

This keeps the deployed interface fast, reproducible, and auditable.

---

# Project Structure

```text
chargebacklens/
│
├── data/
│   ├── raw/
│   │   ├── transactions.csv
│   │   ├── customers.csv
│   │   ├── merchants.csv
│   │   ├── fulfilment.csv
│   │   └── disputes.csv
│   │
│   └── processed/
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
│       │
│       └── models/
│           ├── baseline_model.joblib
│           ├── main_model.joblib
│           └── calibrated_model.joblib
│
├── notebooks/
│   ├── 01_data_cleaning_merging.ipynb
│   ├── 02_eda.ipynb
│   ├── 03_feature_engineering.ipynb
│   ├── 04_model_building.ipynb
│   └── 05_model_evaluation.ipynb
│
├── app/
│   ├── streamlit_app.py
│   ├── scoring.py
│   ├── economics.py
│   └── explain.py
│
├── SCOPE.md
├── METRICS.md
├── FAILURES.md
├── requirements.txt
└── README.md
```

---

# Notebook Pipeline

The project is divided into five notebooks.

### Notebook 01 — Data Cleaning & Merging

Responsible for:

- Loading source datasets
- Schema validation
- Data-quality checks
- Deduplication
- Foreign-key validation
- Label construction
- Master-table creation

The cleaned master table contains:

```text
119,988 rows
24 columns
1,050 positive disputes
≈0.875% dispute rate
```

All 20 defined data-quality checks passed.

---

### Notebook 02 — Exploratory Data Analysis

Responsible for:

- Dispute-rate analysis
- Segment analysis
- Amount analysis
- Merchant/category analysis
- Payment-method analysis
- Identifying potential confounds

EDA findings are exported into inspectable artifacts rather than being required by the application.

---

### Notebook 03 — Feature Engineering

Responsible for:

- Instant transaction features
- Trailing behavioural features
- Merchant-level features
- Customer-level features
- Temporal feature construction
- Feature knowability checks
- Temporal train/test split

The final modelling contract contains:

```text
26 features
23 numeric
3 categorical
```

---

### Notebook 04 — Model Building

Responsible for:

- Baseline model
- Main model
- Hyperparameter search
- Model comparison
- Model selection
- Probability calibration
- Feature importance analysis
- Model artifact export

The final deployed scorer is:

```text
Unweighted Logistic Regression
+
Prefit Sigmoid Calibration
```

---

### Notebook 05 — Model Evaluation & Economics

Responsible for:

- PR-AUC
- Precision@1%
- Precision@5%
- Brier score
- Calibration analysis
- Threshold optimization
- Three-band policy optimization
- Sensitivity analysis
- Segment economics
- Final scored application sample

The notebook does not retrain the model.

It consumes the frozen model predictions produced by Notebook 04.

---

# Reproducibility

A single random seed is used throughout the modelling pipeline:

```python
RANDOM_SEED = 42
```

The project also uses a fixed temporal boundary:

```python
SPLIT_DATE = "2026-08-01"
```

The modelling workflow is therefore deterministic given the same source datasets and software environment.

---

# Technology Stack

| Layer | Technology |
|---|---|
| Language | Python |
| Data manipulation | Pandas, NumPy |
| Machine learning | scikit-learn |
| Model persistence | joblib |
| Visualization | Plotly |
| Application | Streamlit |
| Explanation layer | Anthropic API |
| Development | Jupyter |
| Data format | CSV |
| Documentation | Markdown |

---

# Key Design Decisions

## Temporal split instead of random split

Random splitting can allow future behaviour to influence training data.

ChargebackLens uses chronological separation to better approximate the real deployment scenario:

```text
Past → Train
Future → Test
```

---

## PR-AUC instead of ROC-AUC as the headline metric

The dispute rate is approximately 0.9%.

At such an extreme class imbalance, ROC-AUC can provide an overly optimistic view of ranking performance.

ChargebackLens therefore emphasizes:

- PR-AUC
- Precision@1%
- Precision@5%
- Lift

These metrics are closer to the experience of a risk team operating with limited review capacity.

---

## Calibration before economics

Economic calculations consume the magnitude of the probability.

Therefore:

```text
Model score
     ↓
Calibration
     ↓
Probability
     ↓
Economics
```

rather than:

```text
Model score
     ↓
Economics
```

---

## Three actions instead of binary blocking

The system distinguishes:

```text
Allow
Step-up
Manual Review
```

because risk intervention has different costs depending on its severity.

---

## Segment economics

A single global threshold can hide segments where intervention is not worthwhile.

ChargebackLens therefore evaluates economics across transaction and merchant segments before recommending deployment.

---

## LLM as an explanation layer

The LLM does not control the risk decision.

This ensures that:

- Scoring remains reproducible
- Thresholds remain deterministic
- Economics remain auditable
- The application continues working without an API key

---

# Known Limitations

ChargebackLens is a **demo-scale decision-support system**, not a production payment authorization system.

### 1. Historical evaluation

The model is evaluated on the supplied historical dataset.

It has not been validated on live production traffic.

### 2. Synthetic/pre-generated data

The project operates on the provided pre-generated CSV dataset and should not be interpreted as evidence of production performance.

### 3. Censoring

A substantial portion of test-set positive labels are raised after the modelling snapshot boundary.

This means some late-period transactions may not yet have had sufficient time to reveal their final dispute outcome.

### 4. Conservative economics

The calibrated model under-predicts observed dispute frequency in the highest-risk decile.

Consequently, economic savings estimates should be interpreted as conservative.

### 5. Economic assumptions

The optimal policy depends on assumptions such as:

```text
Dispute fee
Review cost
Merchant margin
Step-up abandonment rate
```

These should be measured using real merchant operational data before production deployment.

### 6. No live payment integration

The current system does not connect to:

- Payment gateways
- Transaction event streams
- Merchant systems
- Production authorization infrastructure

### 7. No automated retraining

There is currently no:

- Model registry
- Automated retraining pipeline
- Drift monitoring
- Automated model refresh

These are potential future production extensions.

### 8. Live transaction scoring is not yet complete

The Streamlit Risk Queue and Economics surfaces are implemented.

The live transaction scoring interface is currently under development.

---

# Security & Scope Boundary

ChargebackLens is strictly a **defensive risk-management system**.

It is designed to help identify transactions that may require additional scrutiny.

The project does not implement:

- Detection-evasion techniques
- Adversarial transaction generation
- Methods for bypassing risk controls
- Offensive fraud tooling
- Techniques intended to help malicious actors avoid detection

This boundary is intentional and architectural.

---

# Future Roadmap

The next development stages are:

### Phase 1 — Complete live transaction scoring

```text
Manual transaction input
        ↓
Feature construction
        ↓
Calibrated prediction
        ↓
Risk band
        ↓
Economic decision
        ↓
Reviewer explanation
```

### Phase 2 — Improve explanation quality

Introduce transaction-specific explanations while retaining the deterministic fallback.

### Phase 3 — Production-style artifact management

Potentially replace flat-file artifacts with:

```text
Model Registry
+
Versioned Artifacts
+
Model Metadata
```

### Phase 4 — Real-time transaction integration

A future production architecture could replace the local artifact interface with a transaction event stream while preserving the same conceptual separation:

```text
Event Stream
     ↓
Feature Service
     ↓
Model
     ↓
Policy
     ↓
Economics
     ↓
Action
```

### Phase 5 — Monitoring

Potential production extensions include:

- Data drift monitoring
- Calibration monitoring
- Performance monitoring
- Segment-level monitoring
- Threshold monitoring
- Economic outcome monitoring

---

# Running Locally

Clone the repository:

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd chargebacklens
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it.

### macOS / Linux

```bash
source .venv/bin/activate
```

### Windows

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the Streamlit application:

```bash
streamlit run app/streamlit_app.py
```

The application should then open at:

```text
http://localhost:8501
```

---

# Project Documentation

Additional technical documentation is available in:

| File | Purpose |
|---|---|
| `SCOPE.md` | Project scope and boundaries |
| `METRICS.md` | Model and economics results |
| `FAILURES.md` | Development blockers, failures, and resolutions |
| `notebooks/` | Complete modelling and evaluation pipeline |

---

# Deployment

The Streamlit application is intended to be deployed as a lightweight demo application.

### Live application

**[Deploying Soon — Live Demo](#)**

The deployed application will expose the current Streamlit interface:

```text
Home
│
├── Risk Queue
├── Economics
└── Score Transaction
      └── Under Development
```

---

# What Makes This Project Different?

ChargebackLens is deliberately not framed as:

> "I trained a model to predict chargebacks."

Instead, it asks:

> **"If the model says a transaction has a certain dispute probability, what should the business actually do about it?"**

That requires three things beyond classification:

```text
Probability
     +
Policy
     +
Economics
```

The project therefore treats the model as one component of a larger decision system.

The most important design principle is:

> **A good risk model is not necessarily a good risk decision.**

A useful system must connect model confidence to operational capacity, customer friction, and financial consequences.

---

# Final Architecture at a Glance

```text
                     CHARGEBACKLENS
                           │
                           ▼
                  ┌─────────────────┐
                  │   Transaction   │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │ Calibrated Risk │
                  │  Probability    │
                  └────────┬────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │     Decision Policy     │
              │                         │
              │ Allow / Step-up /       │
              │ Manual Review           │
              └────────────┬────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │    Economics    │
                  │                 │
                  │ Cost / Savings  │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │   Explanation   │
                  │                 │
                  │ Reviewer Note   │
                  └─────────────────┘
```

---

## Built with

**Python · Pandas · NumPy · scikit-learn · Plotly · Streamlit · Anthropic API**

---

## Status

**Current:** 🟢 Model + evaluation + economics + Risk Queue + Streamlit application

**Next:** 🟡 Live transaction scoring

**Deployment:** 🟡 Preparing public deployment

**Demo:** [Coming Soon — Deployed Link](#)
