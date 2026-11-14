import type { Meta } from "./api";
import { count, pct } from "./format";

/**
 * The four caveats that travel with every rupee figure. Wording follows
 * app/streamlit_app.py; the censoring numbers come from 05_censoring_audit.csv
 * through /api/meta. Backticks mark names to set in mono.
 */
export function caveats(meta: Meta): { lead: string; body: string }[] {
  const audit = meta.censoring_audit;
  return [
    {
      lead: `${count(audit.raised_after_snapshot)} of ${count(audit.test_positives)} test disputes (${pct(audit.share_after_snapshot, 1)}) were raised after the declared 2026-11-01 snapshot`,
      body: `, the latest on ${audit.max_raised_at.slice(0, 10)}. Ranking is unaffected — every feature is time-gated and notebook 3's tripwire passed — but the label counts three months of future disputes, so absolute rupee figures are scaled to exposure a real operator could not yet have measured.`,
    },
    {
      lead: "Every rupee figure is a floor, not an estimate.",
      body: " The model under-predicts in decile 9 by +1.15pp (3.93% predicted against 5.08% observed), so the expected-cost calculation understates savings exactly where the policy operates. This errs in the safe direction, but it is a property of the number, not a disclaimer.",
    },
    {
      lead: "The conclusion is robust; the operating point is not.",
      body: " Net savings stay positive from ₹10.9L to ₹18.1L across step-up abandon rates 0.10–0.40, but the allow/step-up cut moves 3.1×. `step_up_abandon_rate` is the one parameter a merchant must measure rather than assume.",
    },
    {
      lead: "One band of one segment loses money.",
      body: " Manual review on `method = wallet` nets −₹300 across one review and zero catches, while its step-up band earns ₹9,779. The finding is about routing the queue by ticket size, not about skipping wallet entirely.",
    },
  ];
}
