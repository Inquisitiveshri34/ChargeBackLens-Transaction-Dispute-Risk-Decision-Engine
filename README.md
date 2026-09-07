# ChargebackLens

**A calibrated chargeback-risk scorer that answers a rupee question, not a yes/no one.**

Built for the Razorpay AI Buildathon, Track 02 — AI Risk Manager.

🔗 **Live app:** `https://chargebacklens-transaction-dispute-risk-decision-engine.streamlit.app/`
📄 **The numbers:** [`METRICS.md`](METRICS.md) · **What broke:** [`FAILURES.md`](FAILURES.md) · **What it refuses to do:** [`SCOPE.md`](SCOPE.md)

---

## The problem

A merchant loses money to a chargeback in three places at once: the disputed amount, a fixed dispute fee charged regardless of outcome, and the operational cost of responding. A fraud classifier addresses the first of those and ignores the other side of the ledger entirely — **stopping a legitimate customer also costs money**, because a customer pushed into extra verification has a real chance of abandoning the purchase.

So "is this transaction risky?" is the wrong question. The one a merchant actually has is:

> Given this transaction, what is the **rupee-optimal action** — allow it, step it up, or send it to manual review — and how much confidence does that recommendation deserve?

ChargebackLens answers that one.

---

## What it does

On 45,246 held-out transactions with a 0.8995% dispute rate:

| | |
|---|---|
| **Net savings under the deployed policy** | **₹11,99,620** — 39.1% of a ₹30,69,547 exposure |
| **Lift at the top 1% of the queue** | **16.2×** — 66 disputes caught in 452 reviewed |
| **Recall at the top 5%** | **43.2%** — review 5% of volume, surface 43% of disputes |
| **Calibration error** | 0.00185 across ten deciles |

The policy is three bands, not two, with both cut points optimised jointly:

| Band | Score range | Share of volume | Dispute rate in band | Lift |
|---|---|---:|---:|---:|
| **allow** | < 0.02443 | 93.2% | 0.484% | 0.54× |
| **step-up** (3DS friction) | 0.02443 – 0.08240 | 6.2% | 5.42% | **6.03×** |
| **manual review** | ≥ 0.08240 | 0.7% | 16.88% | **18.77×** |

The second threshold is worth **₹1,18,627** over the best single-threshold policy — which turns "two thresholds match how risk teams actually operate" from an argument into a measurement.

---

## What makes this different from a classifier

**It reports where it shouldn't be deployed.** Segment economics under the shipping policy show that manual review on `wallet` traffic nets **−₹300** — one review, zero catches — while `amount > ₹10,000` returns ₹1,434 per intervention, **31× more**. The finding is sharper than "skip wallet": wallet's *step-up* band still earns ₹9,779. **Route the review queue by ticket size; keep the friction, drop the human reviewer, on low-ticket traffic.**

**It refuses visible signal.** `delivery_status` shows a genuine 3.1× spread — `lost` disputes at 2.68% against 0.86% for `delivered`. It is tagged `forbidden` and asserted out of the feature matrix, because it is only knowable weeks after the decision has to be made. The fulfilment table is never even loaded by the feature notebook. The EDA chart that shows this signal carries the word FORBIDDEN in its title, so the exclusion reads as a deliberate refusal rather than an oversight.

**It quotes its headline number with four caveats attached, all measured, all exported.** 72.2% of the test label was raised after the declared snapshot date. The model under-predicts where the money is, so the figure is a floor. The thresholds move 3.1× under a parameter nobody has measured. And one band of one segment loses money. A submission that reported the savings without those four lines would be reporting a larger number and a smaller result.

**It ships the model that won, not the one that was specified.** The prescribed gradient-boosted ensemble memorised its training set at a 9.9 train/test ratio, and after retuning still lost to a 26-feature logistic regression. The simpler model shipped. See [`FAILURES.md`](FAILURES.md).

---

## The app

Three tabs, all reading frozen artifacts. The app never trains and never touches the raw data.

**1 · Score a Transaction** — enter a transaction, get a calibrated probability, a recommended band, and a short reviewer note naming the actual drivers. The eight trailing features are exposed as manual-override sliders, because the app has no customer history at form-entry time; the caption says so plainly rather than pretending otherwise.

**2 · Review Queue** — a risk-ranked queue over a 5,000-row scored sample. The sample is **stratified**, retaining all 308 `manual_review` rows plus a seeded draw of the rest, because a uniform draw at a 0.9% base rate would have shown roughly 34 reviewable transactions and made the queue look empty. The tab reweights by inverse sampling weight so that population-scale figures stay honest.

**3 · Economics Explorer** — move the four cost assumptions and watch the optimal thresholds move. This is where the sensitivity finding becomes tangible: net savings stay positive across the whole range, but the allow/step-up cut moves by a factor of 3.1.

The reviewer note calls the Anthropic API when `ANTHROPIC_API_KEY` is set and falls back to a deterministic template when it isn't. **The fallback is the default path and is fully functional** — scoring, the queue and the economics have zero external dependencies.

---

## Quickstart

```bash
git clone <your-repo-url>
cd chargebacklens
pip install -r requirements.txt
```

**Run the app against the committed artifacts:**

```bash
streamlit run app/streamlit_app.py
```

It boots in under a second. No API key needed — the reviewer note uses its template fallback. To enable the LLM path:

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # or set it in Streamlit's Secrets panel
```

**Reproduce the pipeline from scratch:**

```bash
jupyter lab
# run notebooks/01 → 05 in order, top to bottom
```

Each notebook reads what the previous one wrote and ends by re-reading its own exports and asserting their shape. A stale artifact fails loudly at build time rather than confusingly three notebooks later.

⚠️ **Pin `scikit-learn==1.7.2`.** That is the version that pickled the three model files. A version mismatch on `joblib.load()` is the single most common way a deployment that worked locally crashes in the cloud.

---

## Repository layout

```
chargebacklens/
├── data/
│   ├── raw/                     # 5 pre-generated CSVs — read-only, never written to
│   └── processed/               # every artifact, numbered by producing notebook
│       └── models/              # the only 3 non-CSV files in the project
├── notebooks/
│   ├── 01_data_cleaning_merging.ipynb
│   ├── 02_eda.ipynb
│   ├── 03_feature_engineering.ipynb
│   ├── 04_model_building.ipynb
│   └── 05_model_evaluation.ipynb
├── app/
│   ├── streamlit_app.py         # three tabs
│   ├── scoring.py               # feature formulas + recommend_action — shared with nb 3 and 5
│   ├── economics.py             # threshold sweep, re-run live on slider change
│   └── explain.py               # Anthropic call + deterministic fallback
├── SCOPE.md · METRICS.md · FAILURES.md · README.md
└── requirements.txt
```

**Every data artifact is a CSV.** The only binary files in the project are the three fitted model objects, because a scikit-learn pipeline is not tabular data. Everything else — cleaned tables, the feature matrix, predictions, thresholds, economics parameters, even the feature-knowability tags — is a CSV, specifically so that any artifact can be opened, diffed, and checked by eye without deserialising anything.

The `01_`, `02_`, `03_` prefixes are deliberate: sorted alphabetically, `data/processed/` reads as the exact build order.

---

## How the pipeline works

**The architecture is one decision:** everything expensive, stochastic, or requiring a held-out evaluation runs **offline, once, in a notebook**. Everything interactive runs **online, in the app**, against artifacts the notebook already froze. The app cannot train; the notebooks do not serve requests. Only named artifact files cross that seam.

| Notebook | Does | Key output |
|---|---|---|
| **01 · Cleaning & merging** | 5 raw CSVs → one labelled master table; 14 cleaning rules, each with a found-vs-expected count | `01_master_labelled.csv` (119,988 × 24), base rate **0.8751%**, 20/20 quality checks matched |
| **02 · EDA** | Every chart justifies a downstream decision, including one chart drawn specifically to justify an *exclusion* | `02_eda_segment_summary.csv`; 113:1 imbalance; `email_domain_type` (12× spread) and `phone_verified` (6.3×) identified as the strongest signals |
| **03 · Feature engineering** | The feature contract is written to disk **before the first feature is built**, then three permanent asserts check the matrix against it | `03_feature_knowability.csv` (46 rows), `03_feature_matrix.csv`; temporal split at 2026-08-01; **0 forbidden columns, 0 NaNs**, time-gating tripwire passed |
| **04 · Model building** | Fit what was specified, measure it, escalate on evidence, select under a rule written down in advance | 3 `.joblib` files + 10 evidence CSVs; deployed model **PR-AUC 0.0872, 16.2× lift@1%** |
| **05 · Evaluation & economics** | Metrics first, then rupees — no threshold is chosen before the model's unglamorous baseline is on the page | 9 CSVs including the policy bands, sensitivity, segment economics and censoring audit; **10/10 definition-of-done checks passed** |

Three disciplines run through all five:

- **Round-trip verification.** Every export is immediately re-read and shape-asserted. A corrupted handoff becomes a loud failure at build time, not a confusing bug three notebooks later.
- **Temporal splitting everywhere.** Train/test, and a further three-way split inside train so that no selection decision touches the test set. TEST is read in exactly one cell, after everything is decided.
- **Deviations are logged, never silent.** Seven prescribed mechanics were replaced during this build. Each one is recorded with before/after numbers in `blockers.md` and summarised in `FAILURES.md`.

---

## The model

**Deployed:** an unweighted `LogisticRegression` over 26 features, with a prefit sigmoid calibrator fitted on a held-out temporal block.

That is a simpler model than the design documents specified, and it is the honest result rather than a shortcut. The hyperparameter search over 16 gradient-boosting configurations selected **4 leaf nodes** — asked how much tree it wanted, it said barely any. **The signal in this dataset is additive**, and on this data a linear model is not a strawman; it is the appropriate model.

The selection rule was written down before it was applied: rank by validation PR-AUC → form a tie set by paired bootstrap → break ties on model-class simplicity and log-loss. All five candidates tied on ranking (128 validation positives separate nothing), so the tie-break did the real work — and validation log-loss is what split the two logistic variants, 0.0437 unweighted against 0.4478 weighted.

**The honest claim is not "the linear model wins."** On 407 test positives nothing separates these models. The claim is that a rule fixed in advance picked the simpler and better-calibrated one, and picked it before test was read.

---

## What is deliberately not here

**No ROC-AUC.** All four models score around 0.83, against PR-AUCs around 0.087. At a 0.9% base rate, ROC-AUC is dominated by the 44,839-row true-negative mass. It was computed once in a side cell and exported nowhere — the column is even named `roc_auc_DIAGNOSTIC_ONLY` so the decision is enforced mechanically rather than remembered.

**No offense-capable functionality.** This is a hard architectural boundary, not a guideline. There is no evasion testing, no adversarial example generation, and no module anywhere in this repository that takes a *desired output* as an input. See [`SCOPE.md`](SCOPE.md) §3.

**No LLM in the decision path.** The Anthropic API is called in exactly one place, for one task: turning an already-scored transaction into a short reviewer note. It does not score, threshold, or compute features — those have reproducibility requirements an LLM call cannot cleanly satisfy.

---

## Stack

Python · pandas · NumPy · scikit-learn 1.7.2 · Plotly · Streamlit · Anthropic API (optional)

---

## Documentation

| File | What's in it |
|---|---|
| [`METRICS.md`](METRICS.md) | Every number in this README, with a traceability index mapping each one to the exported CSV cell it came from |
| [`FAILURES.md`](FAILURES.md) | The three failures that would have shipped a wrong number without raising an error, with before/after tables |
| [`SCOPE.md`](SCOPE.md) | What this system does, what it refuses to do, and the defense-only boundary |
| `blockers.md` | The complete running log, all nine entries, including the five-minute library bugs |
| `chargebacklens_hld.md` · `chargebacklens_lld.md` · `chargebacklens_dev_plan.md` | Architecture, module design, and the literal build order |
| `data_cleaning_merging.md` · `eda.md` · `feature_engineering.md` · `model_building.md` · `model_evaluation.md` | One write-up per notebook, produced from executed cell outputs |

---

## Limitations, stated plainly

The dataset is synthetic, and at least two findings are properties of the generator rather than of Indian payments. **72.2% of the test label was raised after the declared snapshot date**, so the rupee figures are scaled to an exposure a real operator could not yet have measured. Model selection rests on 128 validation positives. And `step_up_abandon_rate` — the parameter the thresholds are most sensitive to — is assumed, not measured; it is the single highest-value thing a merchant deploying this could go and measure on real traffic.

All four are quantified in [`METRICS.md`](METRICS.md) §7 and §9.
