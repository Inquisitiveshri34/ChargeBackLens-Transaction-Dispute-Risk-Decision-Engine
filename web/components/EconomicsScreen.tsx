"use client";

import { useEffect, useState } from "react";

import { SliderField, SwitchField } from "@/components/fields";
import { SweepChart } from "@/components/SweepChart";
import { Disclosure, LoadError, Loading, Metric, Prose } from "@/components/ui";
import {
  type CostParams,
  type EconomicsResult,
  type Meta,
  type Sensitivity,
  getSensitivity,
  runEconomics,
} from "@/lib/api";
import { caveats } from "@/lib/caveats";
import { count, cut, fixed, lift, pct, rupees } from "@/lib/format";
import { useMeta } from "@/lib/hooks";

export function EconomicsScreen() {
  const { meta, error } = useMeta();
  return (
    <div className="wrap pt-14 pb-28">
      <h1 className="page-title">Economics explorer</h1>
      {error && <LoadError message={error} />}
      {!meta && !error && <Loading what="the economics" />}
      {meta && <Economics meta={meta} />}
    </div>
  );
}

function Summary({ meta }: { meta: Meta }) {
  const h = meta.headline;
  return (
    <>
      <div
        className="mt-10 grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-x-10 gap-y-8"
        data-testid="headline"
      >
        <Metric
          label="Net savings at the deployed policy"
          value={rupees(h.net_savings_inr)}
          sub={`${pct(h.share_of_exposure, 1)} of exposure`}
        />
        <Metric
          label="Lift at the top 1% of the queue"
          value={lift(h.lift_at_1pct)}
          sub={`precision ${pct(h.precision_at_1pct, 1)}`}
        />
        <Metric
          label="Manual-review band"
          value={`${count(h.review_band_n)} txns`}
          sub={`${lift(h.review_band_lift)} base rate`}
        />
        <Metric
          label="Test base rate"
          value={pct(h.base_rate, 3)}
          sub={`${count(h.test_positives)} disputes in ${count(h.test_n)}`}
        />
      </div>

      <div className="mt-8">
        <Disclosure label="Four things to read before the rupee figures">
          <ol className="grid max-w-[82ch] list-decimal gap-4 pl-5 text-[15px] text-secondary">
            {caveats(meta).map(({ lead, body }) => (
              <li key={lead}>
                <strong className="text-ink">{lead}</strong>
                <Prose text={body} />
              </li>
            ))}
          </ol>
        </Disclosure>
      </div>
    </>
  );
}

function Economics({ meta }: { meta: Meta }) {
  const defaults = meta.economics_params;
  const [params, setParams] = useState<CostParams>({
    dispute_fee: defaults.dispute_fee,
    ops_review_cost: defaults.ops_review_cost,
    merchant_margin: defaults.merchant_margin,
    step_up_abandon_rate: defaults.step_up_abandon_rate,
  });
  const [live, setLive] = useState(false);
  const [result, setResult] = useState<EconomicsResult | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  // Sliders fire on every pixel of a drag; wait for a short pause before asking.
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      runEconomics(params, live, controller.signal).then(
        (value) => {
          setResult(value);
          setProblem(null);
        },
        (reason: Error) => reason.name !== "AbortError" && setProblem(reason.message),
      );
    }, 150);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [params, live]);

  const set = (key: keyof CostParams) => (value: number) =>
    setParams((current) => ({ ...current, [key]: value }));

  const basis = meta.economics_basis;

  return (
    <>
      <Summary meta={meta} />

      <p className="caption mt-14">
        Recomputed live on <strong>{basis.label}</strong>.
        {!basis.is_exact &&
          " Reweighted to population scale by inverse sampling weights; measured about 11% below the exact figure, so read the curve's shape rather than its level."}
      </p>

      <div className="mt-8 grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-x-10 gap-y-6">
        <SliderField
          label="Dispute fee (₹)"
          value={params.dispute_fee}
          min={500}
          max={3000}
          step={100}
          format={(value) => count(value)}
          onChange={set("dispute_fee")}
        />
        <SliderField
          label="Ops review cost (₹)"
          value={params.ops_review_cost}
          min={100}
          max={800}
          step={50}
          format={(value) => count(value)}
          onChange={set("ops_review_cost")}
        />
        <SliderField
          label="Merchant margin"
          value={params.merchant_margin}
          min={0.05}
          max={0.35}
          step={0.01}
          format={(value) => fixed(value, 2)}
          onChange={set("merchant_margin")}
        />
        <SliderField
          label="Step-up abandon rate"
          hint="The one parameter a merchant must measure rather than assume: the optimal allow/step-up cut moves 3.1× across 0.10–0.40."
          value={params.step_up_abandon_rate}
          min={0.05}
          max={0.5}
          step={0.01}
          format={(value) => fixed(value, 2)}
          onChange={set("step_up_abandon_rate")}
        />
      </div>

      {problem && <LoadError message={problem} />}
      {!result && !problem && <Loading what="the policy" />}
      {result && (
        <Results
          result={result}
          maxProba={meta.headline.max_proba}
          live={live}
          onLiveChange={setLive}
        />
      )}
    </>
  );
}

function Results({
  result,
  maxProba,
  live,
  onLiveChange,
}: {
  result: EconomicsResult;
  maxProba: number;
  live: boolean;
  onLiveChange: (value: boolean) => void;
}) {
  const { bands, single_threshold: single, exported_policy: exported } = result;

  return (
    <>
      <div
        className="mt-12 grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-x-10 gap-y-8"
        data-testid="economics-metrics"
        aria-live="polite"
      >
        <Metric
          label="Net savings (three-band)"
          value={rupees(bands.net_savings_inr)}
          sub={`${pct(bands.share_of_exposure, 1)} of exposure`}
        />
        <Metric
          label="Allow / step-up cut"
          value={cut(bands.threshold_allow_stepup)}
          valueClass="text-stepup"
        />
        <Metric
          label="Step-up / review cut"
          value={cut(bands.threshold_stepup_review)}
          valueClass="text-review"
        />
        <Metric
          label="Interventions"
          value={count(bands.interventions)}
          sub={`${count(bands.n_review)} review · ${count(bands.n_stepup)} step-up`}
        />
      </div>

      <div className="mt-8 grid max-w-[92ch] gap-3 text-[15px]">
        {result.reproduces_export && (
          <p className="font-medium text-allow" data-testid="reproduces-line">
            At default parameters the live optimiser reproduces the exported policy exactly:{" "}
            {rupees(exported.net_savings_inr)} at cuts {cut(exported.threshold_allow_stepup)} /{" "}
            {cut(exported.threshold_stepup_review)}. This tab is a live cross-check of notebook 5,
            not a parallel calculation.
          </p>
        )}
        <p className="text-secondary" data-testid="single-threshold-line">
          A single-threshold policy on the same parameters earns {rupees(single.net_savings_inr)}.
          The second cut is worth {rupees(single.second_cut_value_inr)} — the measured
          justification for two thresholds instead of one.
        </p>
        {result.baseline_shifted && (
          <p className="font-medium text-caution" data-testid="not-comparable-line">
            <code>dispute_fee</code> and <code>ops_review_cost</code> both sit inside{" "}
            <code>fn_cost</code>, so moving either also raises the do-nothing baseline that net
            savings is measured against. Net savings is <strong>not comparable</strong> to the
            default run — compare total cost instead ({rupees(bands.total_cost_inr)} now).
          </p>
        )}
      </div>

      <div className="mt-10">
        <SweepChart
          sweep={result.sweep}
          xMax={result.x_max}
          allowCut={bands.threshold_allow_stepup}
          reviewCut={bands.threshold_stepup_review}
        />
        <p className="footnote mt-4">
          The grid is 101 points drawn from <strong>quantiles of the score</strong>, not{" "}
          <code>linspace(0.01, 0.99)</code>: the model&apos;s maximum test probability is{" "}
          {fixed(maxProba, 3)}, so two-thirds of a linear grid would flag zero rows and the
          apparent optimum would be an artifact of the grid.
        </p>
      </div>

      <div className="mt-16">
        <h2 className="section-title">Where the policy should and should not be deployed</h2>
        <div className="mt-4">
          <SwitchField
            label="Recompute segments at the current sliders"
            hint="Off shows the frozen 05_segment_economics.csv, which is the table every quoted segment number traces back to."
            checked={live}
            onChange={onLiveChange}
          />
        </div>
        <div className="mt-5 overflow-x-auto" tabIndex={0} role="region" aria-label="Segment economics">
          <table
            className="table table-compact min-w-[980px]"
            data-testid="segment-table"
            data-source={result.segments.source}
          >
            <thead>
              <tr>
                <th scope="col">
                  <code>segment_type</code>
                </th>
                <th scope="col">
                  <code>segment_value</code>
                </th>
                <th scope="col" className="r">
                  <code>n</code>
                </th>
                <th scope="col" className="r">
                  Dispute rate
                </th>
                <th scope="col" className="r">
                  Mean amount
                </th>
                <th scope="col" className="r">
                  Net @ global policy
                </th>
                <th scope="col" className="r">
                  Per intervention
                </th>
                <th scope="col" className="r">
                  Review band net
                </th>
                <th scope="col" className="r">
                  <code>n_review</code>
                </th>
                <th scope="col" className="r">
                  Step-up band net
                </th>
                <th scope="col" className="r">
                  <code>n_stepup</code>
                </th>
              </tr>
            </thead>
            <tbody>
              {result.segments.rows.map((row) => (
                <tr key={`${row.segment_type}:${row.segment_value}`}>
                  <td>{row.segment_type}</td>
                  <td>{row.segment_value}</td>
                  <td className="r">{count(row.n)}</td>
                  {/* dispute_rate is a fraction; pct() does the x100 */}
                  <td className="r">{pct(row.dispute_rate, 3)}</td>
                  <td className="r">{rupees(row.mean_amount)}</td>
                  <td className="r">{rupees(row.net_savings_at_global_policy)}</td>
                  <td className="r">{rupees(row.savings_per_intervention)}</td>
                  <td
                    className={`r ${row.review_band_net_inr < 0 ? "font-semibold text-review" : ""}`}
                  >
                    {rupees(row.review_band_net_inr)}
                  </td>
                  <td className="r">{count(row.n_review)}</td>
                  <td className="r">{rupees(row.stepup_band_net_inr)}</td>
                  <td className="r">{count(row.n_stepup)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="footnote mt-4">
          Segments are evaluated at the <strong>global</strong> policy, not optimised within
          themselves — a per-segment optimum is non-negative by construction and so can never
          identify a segment worth skipping. Read the review-band column:{" "}
          <code>method = wallet</code> nets −₹300 across one review and zero catches while its
          step-up band earns ₹9,779, and <code>amount &gt; ₹10,000</code> returns ₹1,434 per
          intervention, 31× wallet&apos;s ₹47. The conclusion is to route the review queue by
          ticket size, not to skip wallet.
        </p>
      </div>

      <div className="mt-12">
        <Disclosure
          label={
            <>
              Frozen sensitivity analysis (<code>05_sensitivity_analysis.csv</code>)
            </>
          }
        >
          <SensitivityTable />
        </Disclosure>
      </div>
    </>
  );
}

const SENSITIVITY_FORMAT: Record<string, (value: number) => string> = {
  optimal_threshold: cut,
  threshold_stepup_review: cut,
  n_review: count,
  n_stepup: count,
  net_savings_inr: rupees,
};

function SensitivityTable() {
  const [data, setData] = useState<Sensitivity | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    getSensitivity().then(
      (value) => current && setData(value),
      (reason: Error) => current && setProblem(reason.message),
    );
    return () => {
      current = false;
    };
  }, []);

  if (problem) return <LoadError message={problem} />;
  if (!data) return <Loading what="the sensitivity table" />;

  return (
    <>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Sensitivity analysis">
        <table className="table min-w-[820px]" data-testid="sensitivity-table">
          <thead>
            <tr>
              {data.columns.map((column, i) => (
                <th key={column} scope="col" className={i > 0 ? "r" : undefined}>
                  <code>{column}</code>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, r) => (
              <tr key={r}>
                {data.columns.map((column, i) => {
                  const value = row[column];
                  const format = SENSITIVITY_FORMAT[column];
                  return (
                    <td key={column} className={i > 0 ? "r" : undefined}>
                      {typeof value === "number" && format ? format(value) : String(value ?? "—")}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="footnote mt-4">
        Rows are comparable on <code>net_savings_inr</code> within <code>merchant_margin</code> and{" "}
        <code>step_up_abandon_rate</code>, and <strong>not</strong> within <code>dispute_fee</code>{" "}
        or <code>ops_review_cost</code> — both of those raise the do-nothing baseline as well as
        the cost, so a larger saving there can hide a worse policy.
      </p>
    </>
  );
}
