"use client";

import { useEffect, useState } from "react";

import { SliderField } from "@/components/fields";
import { LoadError, Loading, Metric } from "@/components/ui";
import { ACTION_STYLE } from "@/lib/actions";
import {
  type Meta,
  type QueueDetail,
  type QueueRow,
  type QueueSlice,
  getQueue,
  getQueueDetail,
} from "@/lib/api";
import { count, fixed, lift, minute, pct, rupees } from "@/lib/format";
import { useMeta } from "@/lib/hooks";

export function QueueScreen() {
  const { meta, error } = useMeta();
  return (
    <div className="wrap pt-14 pb-28">
      <h1 className="page-title">Review queue</h1>
      {error && <LoadError message={error} />}
      {!meta && !error && <Loading what="the queue" />}
      {meta && <Queue meta={meta} />}
    </div>
  );
}

function Queue({ meta }: { meta: Meta }) {
  const [topK, setTopK] = useState(5);
  const [slice, setSlice] = useState<QueueSlice | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      getQueue(topK, controller.signal).then(
        (value) => {
          setSlice(value);
          setProblem(null);
        },
        (reason: Error) => reason.name !== "AbortError" && setProblem(reason.message),
      );
    }, 120);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [topK]);

  const headline = meta.headline;
  const picked = slice?.rows.find((row) => row.payment_id === selected) ?? null;

  return (
    <>
      <p className="caption mt-5">
        Pre-scored, no live inference.{" "}
        <strong>
          This {count(meta.queue_sample_size)}-row sample is stratified, not random
        </strong>
        : all {count(headline.review_band_n)} manual-review rows were kept and the rest drawn from
        everything else, so its dispute rate is <em>not</em> the population rate and is never
        quoted as one. <code>risk_percentile</code> is a rank within the full{" "}
        {count(headline.test_n)}-row test set.
      </p>

      <div className="mt-10 max-w-[520px]">
        <SliderField
          label="Work down the top k% of the queue"
          value={topK}
          min={0.5}
          max={25}
          step={0.5}
          format={(value) => fixed(value, 2)}
          onChange={(value) => {
            setTopK(value);
            setSelected(null); // a new slice is a new list; nothing stays selected
          }}
        />
      </div>

      {problem && <LoadError message={problem} />}
      {!slice && !problem && <Loading what="the queue" />}

      {slice && (
        <>
          <div
            className="mt-10 grid grid-cols-[repeat(auto-fit,minmax(min(200px,100%),1fr))] gap-x-10 gap-y-8"
            data-testid="queue-metrics"
          >
            <Metric label="Transactions in slice" value={count(slice.metrics.transactions)} />
            <Metric label="Disputes caught" value={count(slice.metrics.disputes_caught)} />
            <Metric label="Precision within slice" value={pct(slice.metrics.precision)} />
            <Metric label="Exposure in slice" value={rupees(slice.metrics.exposure_inr)} />
          </div>
          <p className="footnote mt-6">
            Precision is computed within the stratified sample, so it is an ordering diagnostic —
            the population figures are precision@1% = {pct(headline.precision_at_1pct, 1)} (
            {lift(headline.lift_at_1pct)} lift) and precision@5% ={" "}
            {pct(headline.precision_at_5pct)} (recall {pct(headline.recall_at_5pct, 1)}), both from{" "}
            <code>05_model_comparison.csv</code>.
          </p>

          <div aria-live="polite">{picked && <DetailPanel row={picked} />}</div>

          <div
            className="mt-10 max-h-[620px] overflow-auto"
            tabIndex={0}
            role="region"
            aria-label="Queue rows"
          >
            <table className="table min-w-[940px]" data-testid="queue-table">
              <thead>
                <tr>
                  <th scope="col">
                    <code>payment_id</code>
                  </th>
                  <th scope="col">Created</th>
                  <th scope="col" className="r">
                    Amount
                  </th>
                  <th scope="col">
                    <code>method</code>
                  </th>
                  <th scope="col">
                    <code>merchant_category</code>
                  </th>
                  <th scope="col" className="r">
                    Risk %
                  </th>
                  <th scope="col" className="r">
                    Percentile
                  </th>
                  <th scope="col">
                    <code>recommended_action</code>
                  </th>
                  <th scope="col">Disputed (label)</th>
                </tr>
              </thead>
              <tbody>
                {slice.rows.map((row) => {
                  const isSelected = row.payment_id === selected;
                  return (
                    <tr
                      key={row.payment_id}
                      className={isSelected ? "bg-fill" : undefined}
                      aria-selected={isSelected}
                    >
                      <td>
                        <button
                          type="button"
                          className="min-h-11 cursor-pointer font-mono text-[13px] underline underline-offset-4"
                          aria-expanded={isSelected}
                          onClick={() => setSelected(isSelected ? null : row.payment_id)}
                        >
                          {row.payment_id}
                        </button>
                      </td>
                      <td>{minute(row.created_at)}</td>
                      <td className="r">{rupees(row.amount)}</td>
                      <td>{row.method}</td>
                      <td>{row.merchant_category}</td>
                      <td className="r">{fixed(row.risk_pct, 2)}%</td>
                      <td className="r">{fixed(row.percentile, 2)}</td>
                      <td>
                        <span className="inline-flex items-center gap-2">
                          <span
                            aria-hidden="true"
                            className={`h-2.5 w-2.5 rounded-full ${ACTION_STYLE[row.recommended_action].dot}`}
                          />
                          {row.recommended_action}
                        </span>
                      </td>
                      <td>
                        {row.is_disputed ? (
                          <strong className="font-semibold text-review">Disputed</strong>
                        ) : (
                          <span className="text-muted">No</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

function DetailPanel({ row }: { row: QueueRow }) {
  const [detail, setDetail] = useState<QueueDetail | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setDetail(null);
    setProblem(null);
    getQueueDetail(row.payment_id, controller.signal).then(
      setDetail,
      (reason: Error) => reason.name !== "AbortError" && setProblem(reason.message),
    );
    return () => controller.abort();
  }, [row.payment_id]);

  // The panel is tinted from the row straight away; the API's own figures
  // replace the row's as soon as they arrive (they are the same numbers).
  const action = detail?.action ?? row.recommended_action;
  const style = ACTION_STYLE[action];
  const probability = detail?.probability ?? row.proba_calibrated;
  const big = "num mt-1 text-[clamp(30px,5vw,40px)] leading-[1.1] font-semibold tracking-[-1px]";

  return (
    <section
      className={`panel mt-10 ${style.tint}`}
      aria-label={`Detail for ${row.payment_id}`}
      data-testid="queue-detail"
      data-action={action}
    >
      <div className="font-mono text-[15px] font-medium" data-testid="detail-payment-id">
        {row.payment_id}
      </div>
      <div className="mt-6 grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-x-10 gap-y-7">
        <div>
          <div className="label">Recommended action</div>
          <div className={`${big} ${style.text}`} data-testid="detail-action">
            {detail?.action_label ?? "…"}
          </div>
        </div>
        <div>
          <div className="label">Dispute probability</div>
          <div className={big} data-testid="detail-probability">
            {pct(probability)}
          </div>
          <div className="mt-1 text-[14px] text-secondary">
            {detail ? `${lift(detail.lift_vs_base)} base rate` : " "}
          </div>
        </div>
        <div>
          <div className="label">Amount</div>
          <div className={big} data-testid="detail-amount">
            {rupees(detail?.amount ?? row.amount)}
          </div>
        </div>
      </div>

      {problem ? (
        <p role="alert" className="mt-7 text-[15px] font-medium text-review">
          {problem}
        </p>
      ) : (
        <>
          <p className="mt-7 max-w-[70ch] text-[18px] leading-[1.5]" data-testid="detail-note">
            {detail ? detail.reviewer_note : "Loading the reviewer note…"}
          </p>
          {detail && (
            <p className="mt-3 text-[13px] text-secondary">
              Same note generator as Tab 1 — one code path, not a duplicate.{" "}
              {detail.reviewer_note_source === "anthropic-api"
                ? "Anthropic API."
                : "Template fallback."}
            </p>
          )}
        </>
      )}
    </section>
  );
}
