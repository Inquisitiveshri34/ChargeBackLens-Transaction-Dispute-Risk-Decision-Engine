"use client";

import { type FormEvent, useMemo, useState } from "react";

import { BandTrack } from "@/components/BandTrack";
import {
  CheckField,
  DateField,
  NumberField,
  SelectField,
  SliderField,
} from "@/components/fields";
import { Disclosure, LoadError, Loading, Prose } from "@/components/ui";
import { ACTION_STYLE } from "@/lib/actions";
import { ApiError, type Meta, type ScoreResult, scoreTransaction } from "@/lib/api";
import { cut, featureValue, fixed, lift, pct, rupees, signed3 } from "@/lib/format";
import { useMeta } from "@/lib/hooks";

interface FormState {
  amount: string;
  method: string;
  merchant_category: string;
  date: string;
  hour: number;
  retry_count: string;
  checkout_latency_ms: string;
  merchant_avg_ticket_size: string;
  email_domain_type: string;
  phone_verified: boolean;
  account_age_days_at_txn: number;
  is_first_txn_for_device: boolean;
  is_foreign_bin: boolean;
  is_physical_goods: boolean;
  refund_window_days: string;
  delivery_sla_days: string;
  txns_last_24h: number;
  txns_last_7d: number;
  distinct_devices_30d: number;
  prior_disputes_before_this_txn: number;
  has_prior_history: boolean;
  ip_state_changed_from_prev_txn: boolean;
  amount_vs_own_avg: number;
  merchant_dispute_rate_trailing_90d: number;
}

/** What the form calls each API field, for error messages. */
const FIELD_LABEL: Record<string, string> = {
  amount: "Amount (₹)",
  method: "Method",
  merchant_category: "Merchant category",
  created_at: "Date",
  retry_count: "Retry count",
  checkout_latency_ms: "Checkout latency (ms)",
  merchant_avg_ticket_size: "Merchant average ticket size (₹)",
  email_domain_type: "Email domain type",
  account_age_days_at_txn: "Account age at transaction (days)",
  refund_window_days: "Refund window (days)",
  delivery_sla_days: "Delivery SLA (days)",
  txns_last_24h: "Transactions in last 24h",
  txns_last_7d: "Transactions in last 7 days",
  distinct_devices_30d: "Distinct devices in 30 days",
  prior_disputes_before_this_txn: "Prior disputes before this transaction",
  amount_vs_own_avg: "Amount vs own 30-day average",
  merchant_dispute_rate_trailing_90d: "Merchant trailing 90-day dispute rate",
};

function merchantFields(meta: Meta, category: string) {
  const defaults = meta.merchant_defaults[category];
  return {
    merchant_avg_ticket_size: String(defaults.avg_ticket_size),
    refund_window_days: String(defaults.refund_window_days),
    delivery_sla_days: String(defaults.delivery_sla_days),
    is_physical_goods: Boolean(defaults.is_physical_goods),
  };
}

function initialForm(meta: Meta): FormState {
  const levels = meta.categorical_levels;
  const category = levels.merchant_category[0];
  return {
    amount: "8500",
    method: levels.method[0],
    merchant_category: category,
    date: "2026-09-15",
    hour: 22,
    retry_count: "0",
    checkout_latency_ms: "2600",
    email_domain_type: levels.email_domain_type[0],
    phone_verified: true,
    account_age_days_at_txn: 450,
    is_first_txn_for_device: false,
    is_foreign_bin: false,
    ...merchantFields(meta, category),
    txns_last_24h: 0,
    txns_last_7d: 0,
    distinct_devices_30d: 1,
    prior_disputes_before_this_txn: 0,
    has_prior_history: true,
    ip_state_changed_from_prev_txn: true,
    amount_vs_own_avg: 1.0,
    merchant_dispute_rate_trailing_90d: 0.007,
  };
}

/** An empty number box goes to the API as null, which it rejects by name. */
const numberOrNull = (text: string) => (text.trim() === "" ? null : Number(text));

function toRequest(form: FormState) {
  const { date, hour, ...rest } = form;
  return {
    ...rest,
    amount: numberOrNull(form.amount),
    retry_count: numberOrNull(form.retry_count),
    checkout_latency_ms: numberOrNull(form.checkout_latency_ms),
    merchant_avg_ticket_size: numberOrNull(form.merchant_avg_ticket_size),
    refund_window_days: numberOrNull(form.refund_window_days),
    delivery_sla_days: numberOrNull(form.delivery_sla_days),
    created_at: date ? `${date}T${String(hour).padStart(2, "0")}:00:00` : null,
  };
}

function describeError(error: unknown): string {
  if (error instanceof ApiError && error.fields.length) {
    return error.fields
      .map(({ field, message }) => `${FIELD_LABEL[field] ?? field}: ${message}.`)
      .join(" ");
  }
  return error instanceof Error ? error.message : "Scoring failed.";
}

export function ScoreScreen() {
  const { meta, error } = useMeta();
  return (
    <div className="wrap pt-14 pb-28">
      <h1 className="page-title">Score a transaction</h1>
      <p className="caption mt-5">
        The eight trailing features below are <strong>manual-override sliders</strong>. In
        production they are computed from the customer&apos;s and merchant&apos;s prior history
        with <code>closed=&apos;left&apos;</code> windows; the app has no history at form-entry
        time, so they are exposed as inputs. This is a demo path, not the production path.
      </p>
      {error && <LoadError message={error} />}
      {!meta && !error && <Loading what="the form" />}
      {meta && <ScoreForm meta={meta} />}
    </div>
  );
}

function ScoreForm({ meta }: { meta: Meta }) {
  const [form, setForm] = useState<FormState>(() => initialForm(meta));
  const [result, setResult] = useState<ScoreResult | null>(null);
  const [scoredWith, setScoredWith] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const snapshot = useMemo(() => JSON.stringify(form), [form]);
  const stale = result !== null && snapshot !== scoredWith;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      setResult(await scoreTransaction(toRequest(form)));
      setScoredWith(snapshot);
    } catch (reason) {
      setProblem(describeError(reason)); // the previous result stays on screen
    } finally {
      setBusy(false);
    }
  }

  const levels = meta.categorical_levels;

  return (
    <>
      <form onSubmit={submit} noValidate className="mt-12">
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(290px,100%),1fr))] gap-x-14 gap-y-10">
          <fieldset className="grid content-start gap-5">
            <legend className="font-display mb-5 text-[18px] font-semibold">Transaction</legend>
            <NumberField
              label="Amount (₹)"
              value={form.amount}
              min={1}
              max={500000}
              step={100}
              onChange={(value) => set("amount", value)}
            />
            <SelectField
              label="Method"
              value={form.method}
              options={levels.method}
              onChange={(value) => set("method", value)}
            />
            <SelectField
              label="Merchant category"
              value={form.merchant_category}
              options={levels.merchant_category}
              onChange={(value) =>
                setForm((current) => ({
                  ...current,
                  merchant_category: value,
                  ...merchantFields(meta, value),
                }))
              }
            />
            <DateField label="Date" value={form.date} onChange={(value) => set("date", value)} />
            <SliderField
              label="Hour of day"
              value={form.hour}
              min={0}
              max={23}
              step={1}
              onChange={(value) => set("hour", value)}
            />
            <NumberField
              label="Retry count (failed auths before success)"
              value={form.retry_count}
              min={0}
              max={10}
              step={1}
              onChange={(value) => set("retry_count", value)}
            />
            <NumberField
              label="Checkout latency (ms)"
              value={form.checkout_latency_ms}
              min={0}
              max={30000}
              step={100}
              onChange={(value) => set("checkout_latency_ms", value)}
            />
          </fieldset>

          <fieldset className="grid content-start gap-5">
            <legend className="font-display mb-5 text-[18px] font-semibold">
              Customer &amp; merchant
            </legend>
            <NumberField
              label="Merchant average ticket size (₹)"
              hint="Drives amount_vs_merchant_avg_ratio. Defaults are per-category medians."
              value={form.merchant_avg_ticket_size}
              min={1}
              step={50}
              onChange={(value) => set("merchant_avg_ticket_size", value)}
            />
            <SelectField
              label="Email domain type"
              value={form.email_domain_type}
              options={levels.email_domain_type}
              onChange={(value) => set("email_domain_type", value)}
            />
            <CheckField
              label="Phone verified"
              checked={form.phone_verified}
              onChange={(value) => set("phone_verified", value)}
            />
            <SliderField
              label="Account age at transaction (days)"
              value={form.account_age_days_at_txn}
              min={0}
              max={2500}
              step={1}
              onChange={(value) => set("account_age_days_at_txn", value)}
            />
            <CheckField
              label="First transaction on this device"
              checked={form.is_first_txn_for_device}
              onChange={(value) => set("is_first_txn_for_device", value)}
            />
            <CheckField
              label="Foreign card BIN"
              checked={form.is_foreign_bin}
              onChange={(value) => set("is_foreign_bin", value)}
            />
            <CheckField
              label="Physical goods"
              checked={form.is_physical_goods}
              onChange={(value) => set("is_physical_goods", value)}
            />
            <NumberField
              label="Refund window (days)"
              value={form.refund_window_days}
              min={0}
              max={60}
              step={1}
              onChange={(value) => set("refund_window_days", value)}
            />
            <NumberField
              label="Delivery SLA (days)"
              value={form.delivery_sla_days}
              min={0}
              max={30}
              step={1}
              disabled={!form.is_physical_goods}
              onChange={(value) => set("delivery_sla_days", value)}
            />
          </fieldset>

          <fieldset className="grid content-start gap-5">
            <legend className="font-display mb-5 text-[18px] font-semibold">
              Trailing history <span className="font-sans font-normal">(manual override)</span>
            </legend>
            <SliderField
              label="Transactions in last 24h"
              value={form.txns_last_24h}
              min={0}
              max={5}
              step={1}
              onChange={(value) => set("txns_last_24h", value)}
            />
            <SliderField
              label="Transactions in last 7 days"
              value={form.txns_last_7d}
              min={0}
              max={10}
              step={1}
              onChange={(value) => set("txns_last_7d", value)}
            />
            <SliderField
              label="Distinct devices in 30 days"
              value={form.distinct_devices_30d}
              min={0}
              max={6}
              step={1}
              onChange={(value) => set("distinct_devices_30d", value)}
            />
            <SliderField
              label="Prior disputes before this transaction"
              value={form.prior_disputes_before_this_txn}
              min={0}
              max={5}
              step={1}
              onChange={(value) => set("prior_disputes_before_this_txn", value)}
            />
            <CheckField
              label="Has any prior transaction"
              checked={form.has_prior_history}
              onChange={(value) => set("has_prior_history", value)}
            />
            <CheckField
              label="IP state changed since last transaction"
              checked={form.ip_state_changed_from_prev_txn}
              onChange={(value) => set("ip_state_changed_from_prev_txn", value)}
            />
            <SliderField
              label="Amount vs own 30-day average"
              hint="1.0 is also the sentinel for 'no 30-day history to compare against'."
              value={form.amount_vs_own_avg}
              min={0.1}
              max={10}
              step={0.1}
              format={(value) => fixed(value, 1)}
              onChange={(value) => set("amount_vs_own_avg", value)}
            />
            <SliderField
              label="Merchant trailing 90-day dispute rate"
              value={form.merchant_dispute_rate_trailing_90d}
              min={0.001}
              max={0.03}
              step={0.001}
              format={(value) => fixed(value, 3)}
              onChange={(value) => set("merchant_dispute_rate_trailing_90d", value)}
            />
          </fieldset>
        </div>

        <div className="mt-12 flex flex-wrap items-center gap-x-6 gap-y-3">
          <button type="submit" className="pill pill-ink lift" disabled={busy}>
            {busy ? "Scoring…" : "Score transaction"}
          </button>
          <div aria-live="polite" className="text-[15px]">
            {problem ? (
              <p role="alert" className="font-medium text-review">
                {problem}
              </p>
            ) : (
              stale && (
                <p className="font-medium text-caution">
                  Inputs changed since the last score. Score again to refresh the result.
                </p>
              )
            )}
          </div>
        </div>
      </form>

      {result && <ScoreResultView result={result} />}
    </>
  );
}

function ScoreResultView({ result }: { result: ScoreResult }) {
  const style = ACTION_STYLE[result.action];
  const { costs, thresholds } = result;
  const largest = Math.max(...result.drivers.map((d) => Math.abs(d.contribution)), 1e-12);

  return (
    <section aria-label="Scoring result" className="mt-14">
      <div
        className={`panel grid grid-cols-[repeat(auto-fit,minmax(min(250px,100%),1fr))] gap-10 ${style.tint}`}
        data-testid="decision-panel"
        data-action={result.action}
      >
        <div>
          <div className="label">Recommended action</div>
          <div
            className={`num mt-2 text-[clamp(40px,7vw,56px)] leading-[1.02] font-semibold tracking-[-1.5px] ${style.text}`}
            data-testid="action-label"
          >
            {result.action_label}
          </div>
          <p className="mt-3 text-[16px] text-secondary">{style.sentence}</p>
        </div>

        <div>
          <div className="label">Dispute probability</div>
          <div
            className="num mt-2 text-[clamp(40px,7vw,56px)] leading-[1.02] font-semibold tracking-[-1.5px]"
            data-testid="probability"
          >
            {pct(result.probability)}
          </div>
          <p className="mt-3 text-[16px] text-secondary" data-testid="lift">
            {lift(result.lift_vs_base)} base rate
          </p>
        </div>

        <div>
          <BandTrack
            probability={result.probability}
            action={result.action}
            actionLabel={result.action_label}
            cuts={thresholds}
          />
          <p className="mt-5 text-[15px] text-secondary" data-testid="why-this-band">
            <strong className="text-ink">Why this band</strong> · allowing and being wrong costs{" "}
            {rupees(costs.fn_cost)}; a 3DS step-up costs {rupees(costs.fp_cost)} in expected
            abandonment; a human review costs {rupees(costs.tp_cost)}. Band cuts:{" "}
            {cut(thresholds.allow_stepup)} / {cut(thresholds.stepup_review)}.
          </p>
        </div>
      </div>

      <div className="mt-14">
        <h2 className="section-title">Drivers for this transaction</h2>
        <ul className="mt-5 grid gap-1" data-testid="drivers">
          {result.drivers.map((driver) => {
            const raises = driver.contribution >= 0;
            const half = (Math.abs(driver.contribution) / largest) * 50;
            return (
              <li
                key={driver.term}
                className="grid min-h-11 grid-cols-1 items-center gap-x-8 gap-y-1 py-2 sm:grid-cols-[minmax(0,1.3fr)_auto_minmax(0,1fr)]"
              >
                <span className="text-[15px]">{driver.label}</span>
                <span className="text-[14px] text-secondary sm:text-right">
                  <span className="num text-[15px] font-semibold text-ink">
                    {signed3(driver.contribution)}
                  </span>{" "}
                  {driver.direction}
                </span>
                <span className="relative block h-5" aria-hidden="true">
                  <span className="absolute top-0 left-1/2 h-5 w-px bg-ink/40" />
                  <span
                    className={`absolute top-1.5 h-2 rounded-full ${raises ? "bg-review-bar" : "bg-allow-bar"}`}
                    style={raises ? { left: "50%", width: `${half}%` } : { right: "50%", width: `${half}%` }}
                  />
                </span>
              </li>
            );
          })}
        </ul>
        <p className="footnote mt-4">
          Method: {result.drivers_method}. Only features passing the 2σ permutation screen in{" "}
          <code>04_feature_importances.csv</code> are eligible — 18 of 26 fail it and 6 score at or
          below zero, so an unfiltered list would name shuffled noise as a driver.
        </p>
      </div>

      <div className="mt-14">
        <h2 className="section-title">Reviewer note</h2>
        <p className="mt-4 max-w-[70ch] text-[20px] leading-[1.5]" data-testid="reviewer-note">
          {result.reviewer_note}
        </p>
        <p className="footnote mt-3" data-testid="note-source">
          {result.reviewer_note_source === "anthropic-api" ? (
            "Generated by the Anthropic API."
          ) : (
            <Prose text="Deterministic template — `ANTHROPIC_API_KEY` is not set. This is the default path and is exercised on every boot without a key." />
          )}
        </p>
      </div>

      <div className="mt-12">
        <Disclosure label="The exact feature row sent to the model">
          <div className="max-w-[560px] overflow-x-auto">
            <table className="table" data-testid="feature-row">
              <thead>
                <tr>
                  <th scope="col">Feature</th>
                  <th scope="col" className="r">
                    Value
                  </th>
                </tr>
              </thead>
              <tbody>
                {result.feature_row.map(({ name, value }) => (
                  <tr key={name}>
                    <td>
                      <code>{name}</code>
                    </td>
                    <td className="r">{featureValue(value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Disclosure>
      </div>
    </section>
  );
}
