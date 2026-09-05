# ChargebackLens — High-Level Design

**Track:** Razorpay AI Buildathon — Track 02, AI Risk Manager
**Companion documents:** `chargebacklens_lld.md` (module and function-level design), `chargebacklens_data_spec.md` (CSV schema, FK, and data-quality contract)
**Purpose of this document:** describe the system at the architecture level — what the major components are, how they talk to each other, why the system is split the way it is, and what decisions were made and why. The LLD answers "how is each function implemented"; this document answers "why does the system look like this."

---

## 1. Problem statement

A merchant on a payments platform loses money to chargebacks in three ways at once: the disputed transaction amount, a fixed dispute fee charged regardless of outcome, and the operational cost of responding to the case. A plain fraud classifier only addresses the first of these, and it ignores the fact that **blocking a legitimate customer also costs money** — a customer forced into a step-up verification has some probability of abandoning the purchase entirely.

**ChargebackLens exists to answer one question a merchant actually has:** *given a transaction, what is the rupee-optimal action — allow it, step it up, or send it to manual review — and how confident should the merchant be in that recommendation?*

This reframes the project from "build an accurate classifier" to "build a system that converts a probability into a bounded, explainable, economically-justified decision." That reframing drives every architectural choice below.

---

## 2. Objectives and non-objectives

**In scope:**
- A calibrated probability of dispute risk, evaluated honestly on data the model has not seen during training.
- A rupee-denominated decision layer that sits on top of that probability.
- A demo surface (Streamlit) that lets a reviewer score a transaction, browse a risk-ranked queue, and see how the economics respond to changing assumptions.
- A narrow, clearly-scoped use of an LLM for one explanatory task, with a fully offline fallback.

**Explicitly out of scope:**
- Real-time integration with a live payments system. This is a decision-support system evaluated on historical data, not a production authorization gate.
- Any offense-capable functionality — evasion testing, adversarial example generation, or anything that could be repurposed to help a bad actor avoid detection. Per the track's own bar, this disqualifies a submission outright, so it is treated as a hard architectural boundary, not a coding guideline (see §9).
- Data generation. The five CSVs are a fixed, pre-generated input contract (see `chargebacklens_data_spec.md`); no component in this system writes to `data/raw/`.

---

## 3. System context

```
                    ┌────────────────────────┐
                    │   Pre-generated CSVs    │
                    │  (fixed, read-only,     │
                    │   external to system)   │
                    └───────────┬─────────────┘
                                │ read-only
                                ▼
   ┌───────────────────────────────────────────────────────┐
   │                 OFFLINE PHASE (Jupyter)                │
   │   load → validate → engineer → split → train →         │
   │   calibrate → evaluate → economics → export            │
   └───────────────────────────┬────────────────────────────┘
                                │ writes
                                ▼
                    ┌────────────────────────┐
                    │   data/processed/*      │
                    │  (model, thresholds,    │
                    │   scored sample, JSON)  │
                    └───────────┬─────────────┘
                                │ read-only
                                ▼
   ┌───────────────────────────────────────────────────────┐
   │               ONLINE PHASE (Streamlit)                 │
   │   score a transaction · review queue · economics tab   │
   └───────────────────────────┬────────────────────────────┘
                                │ optional, one narrow call
                                ▼
                    ┌────────────────────────┐
                    │   Anthropic API         │
                    │  (reviewer-note text    │
                    │   generation only)      │
                    └────────────────────────┘
```

**Two humans interact with this system:** the person running the notebook (produces the artifacts, owns the modelling decisions) and a reviewer using the Streamlit app (consumes the artifacts, makes or reviews a decision on a transaction). The system is deliberately architected so these two roles never need to run each other's half — the app cannot train, and the notebook does not serve requests.

---

## 4. High-level architecture: the offline/online split

This is the single most important structural decision in the system, so it's worth stating explicitly and separately from the component list.

**Everything that is expensive, stochastic, or needs a held-out evaluation runs offline, once, in the notebook.** Everything that needs to be fast, repeatable, and interactive runs online, in the app, against artifacts the notebook already produced.

This split exists for three reasons:
1. **Reproducibility.** Training touches randomness (model initialization, calibration folds). If the app retrained on every page load, "the model" would not be a fixed, auditable artifact — it would be a moving target that could produce a different answer for the same transaction depending on when you asked. Training happens exactly once per notebook run, seeded, and the result is frozen to disk.
2. **Speed.** `HistGradientBoostingClassifier` plus isotonic calibration over 120K rows takes real time. A reviewer clicking through a queue of transactions cannot wait for that on every interaction. Freezing the model to a `.joblib` file means the app's only per-request cost is a single `predict_proba` call.
3. **Separation of concerns for judging.** A judge inspecting the repo should be able to see the entire evaluation story — baseline, main model, calibration, metrics, economics — in one linear notebook narrative, and separately see the entire user-facing product in the app, without the two being tangled into one script that does both badly.

The **data contract** between the two phases (exact files, formats, and producers/consumers) is fully specified in `chargebacklens_lld.md` §6. This HLD treats that contract as the seam: nothing crosses it except the six named artifact files.

---

## 5. Component overview

### 5.1 Data layer
Owns reading and validating the five source CSVs against the fixed schema in `chargebacklens_data_spec.md`. Nothing downstream is allowed to assume a column exists that isn't in that contract, and nothing downstream re-derives the label — it is computed once, here, and carried forward as a single column.

### 5.2 Feature engineering layer
Converts validated raw tables into one model-ready matrix. This is the component with the most risk in the entire system, because a payments-dispute dataset has an unusually sharp leakage hazard: several fields (delivery status, delivery timestamps) are only knowable *after* the window in which a dispute risk decision would need to be made. This layer's core responsibility is enforcing, mechanically, that no feature crosses that boundary. Every feature is tagged with when it becomes knowable, and that tagging is treated as a first-class design artifact, not an afterthought — it is exported into `METRICS.md` so a reader can audit it without reading code.

### 5.3 Modelling layer
Produces three artifacts in a fixed order — a baseline, a main model, and a calibrated version of the main model — because a single model presented alone is a claim, while three models compared side-by-side is evidence. Calibration is treated as a required step, not an optional improvement: the layer above (economics) is only valid if the probabilities it consumes are real probabilities, not just a score that ranks correctly.

### 5.4 Evaluation layer
Produces every number that goes into the project's metrics reporting. Its most important architectural property is what it deliberately does **not** treat as a headline number: ROC-AUC is excluded from the primary report because the ~0.9% base rate inflates it into a misleadingly good-looking figure. This is a judgment call made once, centrally, in this layer, rather than left to whoever writes the README to remember.

### 5.5 Economics layer
Sits on top of the calibrated probability and is the component that makes this a *risk manager* rather than a *classifier*. It converts a probability into a rupee cost under each possible outcome (correctly flagged, wrongly flagged, correctly allowed, wrongly allowed), sweeps every possible decision threshold, and reports the threshold that maximizes net savings — along with a sensitivity check on its own assumptions and a segment breakdown that can recommend **not** deploying the model in some segments. Architecturally, this layer is downstream of calibration and has no direct dependency on model internals — it only consumes `(probability, amount, actual_outcome)` tuples, which means the same economics module works unchanged if the underlying model is ever swapped.

### 5.6 Explanation layer
The only component that calls an external service. Scoped narrowly and deliberately: given a flagged transaction, its top contributing features, and the merchant's policy text, produce a short factual reviewer note. It is designed to degrade gracefully — a deterministic template stands in when no API key is present, so the rest of the system (scoring, the queue, the economics tab) is fully functional with zero external dependencies. This is an explicit design boundary against LLM-scope creep: the model does not touch scoring, threshold selection, or feature computation, all of which have correctness and reproducibility requirements an LLM cannot cleanly satisfy.

### 5.7 Application layer
The Streamlit app. Three tabs, each reading a different slice of the same frozen artifact set, sharing scoring and recommendation logic with the notebook via a small shared module so the two halves of the system cannot silently diverge on what a "high risk" transaction means.

---

## 6. End-to-end data flow

1. Five CSVs are read once, validated against the documented schema, and joined to produce a single labelled transaction table.
2. Every downstream feature is computed with an explicit knowability tag; a feature matrix is assembled and asserted clean of forbidden (leakage) columns.
3. The matrix is split **temporally**, not randomly — rows before a fixed date train the model, rows after it test the model — because a random split would let information about a merchant's future risk drift leak backward into training.
4. Three models are fit in sequence (baseline → main → calibrated), and all three are evaluated on the same held-out test set so the value of each step is visible.
5. The calibrated model's test-set probabilities feed the economics layer, which sweeps decision thresholds and finds the rupee-optimal operating point, including how that optimum shifts under different cost assumptions and across merchant/amount segments.
6. A fixed set of artifacts — the calibrated model, the ordered feature list, the economics parameters, the threshold sweep, a sampled scored test set, and feature importances — is written to disk. This is the only handoff point between the two phases.
7. The Streamlit app loads those artifacts once per process and, per request, either scores a new transaction the reviewer enters manually or looks up a pre-scored transaction from the sampled test set — never retraining, never touching the raw CSVs.
8. On request, the explanation layer turns a scored transaction and its top features into a short reviewer note, via the Anthropic API if available or a deterministic template if not.

---

## 7. Key design decisions and their rationale

| Decision | Alternative considered | Why this system rejects the alternative |
|---|---|---|
| Temporal train/test split | Random split | A random split lets a merchant's risk drift in month 9 leak backward into training on month 3 data — the model would look better than it will actually perform in production, where it only ever sees the future. |
| Report PR-AUC and precision@k as headline metrics | Report ROC-AUC | At a ~0.9% positive rate, ROC-AUC is dominated by the large true-negative mass and stays high even for a mediocre model. PR-AUC and precision-within-a-fixed-review-capacity are what a reviewer with limited queue capacity actually experiences. |
| Calibrate the model before using its output economically | Use raw model scores directly in the cost function | Raw gradient-boosting scores rank transactions correctly but are not real probabilities — multiplying an uncalibrated score by a rupee amount produces a cost estimate with no defensible meaning. Calibration is what makes the economics layer honest rather than decorative. |
| Three-band decision (allow / step-up / manual review) | Binary allow/block | A hard block on every flagged transaction ignores that review capacity is finite and that different confidence levels warrant different friction. Two thresholds instead of one is a small addition that makes the recommendation match how a real risk team actually operates. |
| Segment-level economics reporting, including "don't deploy here" segments | Report a single global optimal threshold | A single global number hides that low-ticket transactions can have review friction costs that exceed their dispute exposure. Surfacing that explicitly is more useful to a merchant than a flattering aggregate number, and it demonstrates the kind of judgment the track's evaluation criteria explicitly reward. |
| LLM used only for reviewer-note generation, with a deterministic fallback | LLM-driven scoring or threshold selection | Scoring and thresholding have hard requirements — reproducibility, auditability, latency — that an LLM call cannot cleanly guarantee. Confining the LLM to a bounded, low-stakes text-generation task, with a fallback that makes the rest of the app work with zero external dependency, is a deliberate statement of where AI is and isn't the right tool. |
| Offline notebook / online app split | A single script that trains and serves | Keeps training reproducible and one-shot, keeps the app fast and dependency-light, and keeps the evaluation narrative (notebook) and the product demo (app) separately readable by a judge. |

---

## 8. Technology stack

| Layer | Technology | Reason |
|---|---|---|
| Data manipulation | pandas, NumPy | Standard, well-understood, sufficient at 120K-row scale without needing distributed tooling |
| Visualization (EDA) | Plotly | Interactive figures embed directly in the notebook narrative; reused for in-app charts, avoiding a second charting library |
| Modelling | scikit-learn (`HistGradientBoostingClassifier`, `LogisticRegression`, `CalibratedClassifierCV`) | Native categorical and NaN handling, no extra install surface, trains fast enough at this row count to iterate within the time budget |
| Artifact persistence | joblib, JSON, CSV | joblib for the sklearn pipeline object; plain JSON/CSV for everything else, so artifacts are inspectable without deserializing a pickle |
| Application | Streamlit | Rapid to build against a fixed set of pre-computed artifacts; `@st.cache_resource` / `@st.cache_data` give correct once-per-process loading with no extra infrastructure |
| Explanation generation | Anthropic API (optional) | Bounded, single-purpose text generation task; deterministic fallback keeps the app's core functionality independent of it |

---

## 9. Non-functional requirements

- **Reproducibility.** A single seed constant threads through every stochastic call. Re-running the notebook end-to-end should reproduce the same metrics and the same rows flagged as data-quality issues (cross-checked against `chargebacklens_data_spec.md`).
- **Auditability.** Every feature is tagged with when it becomes knowable; every export is immediately re-read and shape-checked; every dropped or flagged row is logged with a count that can be checked against the data specification document.
- **Latency (app).** The app must never retrain and must never re-read the raw CSVs — its only per-request cost is a `predict_proba` call and, optionally, one LLM call for note generation. This keeps demo interactions in the sub-second range apart from the optional network call.
- **Defense-only scope.** This is a hard boundary, not a preference: the system produces a defensive risk signal and a recommended action. It does not include, and must not be extended to include, any component that tests or documents how to evade the detector — doing so would be offense-capable functionality, which the track explicitly disqualifies.
- **Graceful degradation.** Every component that depends on an external service (only the explanation layer) has a fully offline fallback, so the system's core value — score, queue, economics — never depends on network availability or an API key being present.

---

## 10. Deployment view

This is a demo-scale system, not a production deployment, and the architecture reflects that honestly rather than over-engineering it:

- The notebook runs once, locally, producing artifacts under version control (aside from the raw CSVs and the largest processed files, which are appropriately gitignored with a small committed sample for reproducibility).
- The Streamlit app runs as a single process reading those artifacts from local disk — no database, no message queue, no separate model-serving layer. At this scale, a database would add operational surface without adding capability.
- The only external network dependency, and it is optional, is the Anthropic API call in the explanation layer.

If this were to move toward production, the natural next step in this architecture (not built here, but worth naming) would be replacing the `data/processed/*` artifact directory with a versioned model registry and replacing local CSV reads with a proper transaction event stream — the offline/online split described in §4 would not need to change, only what sits on either side of the seam.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Feature leakage produces an unrealistically strong, untrustworthy model | Explicit knowability tagging (§5.2), forbidden-column assertion at feature-matrix assembly time, temporal split |
| Uncalibrated probabilities make the economics layer's rupee figures meaningless | Calibration is a required step before any cost-function use, not an optional add-on (§5.3, §7) |
| A single global metric or threshold hides where the system does more harm than good | Segment-level economics reporting, explicitly naming segments where deployment isn't justified (§5.5) |
| The submission is read as offense-capable given the subject matter (fraud/dispute detection) | Defense-only scope stated as a hard architectural boundary (§2, §9), not left implicit |
| The app becomes dependent on the LLM being available | Deterministic template fallback in the explanation layer, exercised by default with no API key (§5.6) |
| Notebook and app silently diverge on what a feature means | Shared scoring/feature-formula module imported by both, rather than duplicated logic (per LLD §5.2) |

---

## 12. Out of scope for this iteration

- Multi-merchant configuration or a merchant-facing settings UI.
- Any persistence layer beyond flat files (no database).
- Automated retraining or a model-monitoring/drift-detection pipeline.
- Authentication or access control on the Streamlit app — it is a local demo, not a hosted multi-user product.
- SHAP-based explanations as a hard requirement — feature-importance-based approximations are an acceptable fallback if time runs out (see LLD §4.6).
