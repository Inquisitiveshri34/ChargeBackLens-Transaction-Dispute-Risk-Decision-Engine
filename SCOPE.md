# SCOPE.md — what ChargebackLens is, and what it deliberately is not

**Project:** ChargebackLens — calibrated chargeback-risk scoring and rupee-denominated routing for Indian payment transactions
**Track:** Razorpay AI Buildathon — Track 02, AI Risk Manager
**Companion documents:** `chargebacklens_hld.md` §2 and §9 (where these boundaries were first set), `METRICS.md` (what was measured), `FAILURES.md` (what broke), `README.md` (how to run it)

This document exists so that a reader can tell, without reading code, exactly what this system claims to do, what it refuses to do, and where the line between those two sits. Some of the boundaries below are ordinary product scoping. One of them — §3 — is a hard architectural boundary that governs what may ever be added to this repository.

---

## 1. The problem, stated once

A merchant on a payments platform loses money to a chargeback in three places at once: the disputed amount itself, a fixed dispute fee charged regardless of who wins, and the operational cost of assembling a response. A fraud classifier addresses only the first, and it ignores the other half of the ledger entirely — **stopping a legitimate customer also costs money**, because a customer pushed into an additional verification step has a real probability of simply abandoning the purchase.

ChargebackLens answers the question a merchant actually has:

> Given this transaction, what is the rupee-optimal action — **allow it, step it up, or send it to manual review** — and how much confidence does that recommendation deserve?

That reframing, from "build an accurate classifier" to "convert a probability into a bounded, explainable, economically-justified decision," is what every scope decision below follows from.

---

## 2. In scope

| Capability | What it means concretely |
|---|---|
| **Calibrated dispute probability** | A probability that can be multiplied by a rupee amount and still mean something. Calibration is a required step, not an optional improvement — see §4. |
| **Honest held-out evaluation** | A temporal train/test split, metrics chosen for a 0.9% base rate, and a comparison table containing the models that lost. |
| **A rupee decision layer** | Expected cost under each of the four outcomes, a threshold sweep, two jointly-optimised operating thresholds, and a sensitivity analysis over the cost assumptions. |
| **Segment-level economics** | Per-segment returns under the single policy that would actually ship, including segments where an intervention **loses** money and should not be deployed. |
| **A demo surface** | A three-tab Streamlit app: score a transaction, browse a risk-ranked queue, move the economics assumptions and watch the optimum move. |
| **A narrow LLM use** | One bounded text-generation task — a short reviewer note — with a fully offline deterministic fallback. |

---

## 3. The defense-only boundary — a hard architectural constraint

**This is not a coding guideline. It is a boundary on what may exist in this repository.**

ChargebackLens produces a **defensive** signal: a risk score and a recommended action for the party defending against disputes. It does not contain, and must not be extended to contain, any component whose purpose or effect is to help a bad actor avoid detection.

Concretely, the following are out of scope and will remain out of scope:

- **Evasion testing.** No component that searches for input perturbations which move a transaction from `manual_review` to `allow`.
- **Adversarial example generation.** No component that constructs synthetic transactions optimised to score low.
- **Detection-threshold disclosure framed as attacker guidance.** The two operating thresholds are published in `05_economics_params.csv` because a *merchant* configuring their own queue needs them; they are documented as an operating parameter, never as "the number to stay under."
- **Any inverted use of the explanation layer.** `app/explain.py` explains why a transaction was flagged, to a reviewer. It does not explain how a transaction could have avoided being flagged.

The track's own evaluation bar treats offense-capable functionality as disqualifying. Rather than treat that as a thing to remember at submission time, it was treated as a structural property of the system from the first design document. The practical consequence is that this boundary is easy to audit: there is no module, notebook cell, or app control anywhere in the repository that takes a *desired output* as an input.

---

## 4. Boundaries inherited from the architecture

These are narrower than §3 but they are real constraints, and each one was chosen for a stated reason rather than arrived at by omission.

### 4.1 Decision support, not an authorization gate

This system evaluates historical transactions and recommends actions. It is **not** wired into a live payments flow and does not authorize, decline, or hold anything. There is no real-time integration, no latency budget for an in-line decision, and no failure-mode design for what happens when the scorer is unavailable mid-transaction — because it is never in the transaction path.

### 4.2 The raw data is a read-only input contract

The five source CSVs are pre-generated and external to the system. **No component writes to `data/raw/`.** Data generation is not part of this project.

This constraint had teeth. A specified feature, `ip_billing_state_mismatch`, turned out to be unbuildable because no table in the dataset carries a billing state. Synthesising one would have meant writing to `data/raw/`, so the feature was substituted rather than manufactured (`FAILURES.md` §5, `blockers.md` BLK-002).

### 4.3 The offline/online seam

Everything expensive, stochastic, or requiring a held-out evaluation runs **offline**, once, in a notebook. Everything interactive runs **online**, in the app, against artifacts the notebook already froze.

The app cannot train. The notebooks do not serve requests. The only things that cross the seam are named artifact files. This means "the model" is a fixed, auditable object rather than a moving target that could answer differently depending on when you asked it.

### 4.4 Calibration is upstream of every rupee figure

No economics computation may consume a raw model score. A gradient-boosting score ranks transactions correctly but is not a probability, and multiplying a non-probability by a rupee amount produces a cost estimate with no defensible meaning.

This boundary caught a real defect: the prescribed baseline model, fitted with `class_weight='balanced'`, produced probabilities inflated roughly 50× while ranking perfectly well. Every threshold, sweep, and segment figure would have run without error against those numbers (`FAILURES.md` §2).

### 4.5 The LLM does exactly one thing

The Anthropic API is called in exactly one place, for one task: turning an already-scored transaction and its already-computed top drivers into a two-to-three sentence reviewer note.

The LLM does **not** score transactions, select thresholds, compute features, or make routing decisions. Those have reproducibility, auditability, and latency requirements that an LLM call cannot cleanly satisfy. A deterministic template stands in whenever `ANTHROPIC_API_KEY` is absent, which means the app's entire core — scoring, queue, economics — has zero external dependencies.

### 4.6 No feature may use post-decision information

Every feature carries a knowability tag, written to `03_feature_knowability.csv` **before the first feature was built**, and a permanent assertion checks the assembled matrix against it.

Twelve fields are tagged `forbidden`. The most visible is `delivery_status`: transactions marked `lost` dispute at 2.68% against 0.86% for `delivered`, a 3.1× spread. That signal is real, and it is refused, because it is only knowable weeks after the moment a routing decision has to be made. The EDA chart showing it carries the word FORBIDDEN in its title so that the exclusion reads as a deliberate refusal rather than an oversight.

---

## 5. Explicitly out of scope

| Not built | Why |
|---|---|
| Real-time payment-gateway integration | §4.1 — this is decision support, not an authorization gate |
| Data generation or augmentation | §4.2 — raw CSVs are a read-only contract |
| Automated retraining or drift monitoring | Training is a one-shot, seeded, offline step by design (§4.3) |
| Any persistence layer beyond flat files | At 120K rows a database adds operational surface without adding capability |
| Multi-merchant configuration or a settings UI | Out of scope for one iteration; the economics parameters are exposed as sliders instead |
| Authentication on the Streamlit app | It is a demo surface reading frozen public artifacts, not a multi-user product |
| SHAP explanations as a hard requirement | Shipping a logistic regression made real coefficient-based contributions available, which is better than a SHAP approximation and cheaper than SHAP itself |
| Any offense-capable component | §3 — hard boundary |

---

## 6. Limits on what the results claim

Scope is also about the strength of the claim, not only the size of the feature set. Four limits apply to every number in `METRICS.md`, and they are stated there next to the figures rather than in a footnote.

1. **The data is synthetic.** Several findings are properties of the generator, not of Indian payments — most clearly that `ip_state` is assigned per transaction with no customer-level home state, which makes one engineered feature structurally incapable of carrying signal.

2. **72.2% of the test label is post-snapshot.** 294 of 407 test positives were raised after the 2026-11-01 snapshot date the data spec declares, with the latest at 2027-01-26. Ranking is unaffected — every feature is time-gated — but the rupee figures are scaled to an exposure a real operator standing on the snapshot date could not yet have observed.

3. **The economics are a floor, not an estimate.** The deployed model under-predicts in the top decile by 1.15 percentage points, so every savings figure understates rather than overstates.

4. **The conclusion is robust; the operating point is not.** Net savings stay positive across the full sensitivity range, but one threshold moves by a factor of 3.1 depending on a parameter nobody has measured on real data.

A version of this project that reported the savings figure without those four lines would be reporting a larger number and a smaller result.

---

## 7. Who this is for

Two roles, deliberately separated so that neither has to run the other's half:

- **The analyst** runs the five notebooks, owns the modelling decisions, and produces the artifacts. Everything they need to audit a decision is a CSV that opens in a spreadsheet.
- **The reviewer** uses the Streamlit app to score a transaction, work a risk-ranked queue, or test how the recommendation changes under different cost assumptions. They never train anything.

---

## 8. If this moved toward production

Named here for completeness, not built:

- Replace `data/processed/` with a versioned model registry.
- Replace local CSV reads with a transaction event stream.
- Measure `step_up_abandon_rate` on real traffic rather than assuming it — `METRICS.md` §7 identifies this as the single highest-value measurement a merchant could make.
- Add drift monitoring on the score distribution, since the operating thresholds are quantile-derived and would move with it.

The offline/online seam in §4.3 would not need to change. Only what sits on either side of it would.
