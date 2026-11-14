"use client";

import Link from "next/link";
import { type CSSProperties, useEffect, useState } from "react";

import { LoadError, Prose } from "@/components/ui";
import { ACTION_STYLE } from "@/lib/actions";
import { type Action, type LaneExamples, type Meta, getLaneExamples } from "@/lib/api";
import { caveats } from "@/lib/caveats";
import { count, cut, fixed, lift, pct, rupees } from "@/lib/format";
import { useCountUp, useMeta } from "@/lib/hooks";

/** Chips per lane and how long one crossing takes. Busier lanes move faster. */
const LANES: { action: Action; chips: number; seconds: number }[] = [
  { action: "allow", chips: 5, seconds: 9 },
  { action: "step_up", chips: 3, seconds: 14 },
  { action: "manual_review", chips: 2, seconds: 20 },
];

const BAR: Record<Action, string> = {
  allow: "bg-allow-bar",
  step_up: "bg-stepup",
  manual_review: "bg-review-bar",
};

const delay = (ms: number) => ({ "--delay": `${ms}ms` }) as CSSProperties;

export function LandingScreen() {
  const { meta, error } = useMeta();

  return (
    <div className="wrap pb-28">
      <Hero meta={meta} />
      {error && <LoadError message={error} />}
      <div className="rise mt-16" style={delay(380)}>
        <RoutingPanel meta={meta} />
      </div>
      <Figures meta={meta} />
      {meta && (
        <>
          <Lanes meta={meta} />
          <Steps meta={meta} />
          <Limits meta={meta} />
        </>
      )}
      <Closing />
    </div>
  );
}

function Hero({ meta }: { meta: Meta | null }) {
  return (
    <header className="pt-20 sm:pt-28">
      <p
        className="rise inline-flex min-h-9 items-center gap-3 rounded-full bg-fill px-4 text-[13px] font-medium text-secondary"
        style={delay(0)}
      >
        <span className="relative inline-flex h-2 w-2" aria-hidden="true">
          <span className="pulse-ring absolute inset-0 rounded-full bg-allow-bar" />
          <span className="relative h-2 w-2 rounded-full bg-allow-bar" />
        </span>
        Measured on {meta ? count(meta.headline.test_n) : "…"} held-out transactions
      </p>
      <h1
        className="rise font-display mt-7 max-w-[15ch] text-[clamp(44px,9vw,72px)] leading-[1.02] font-semibold tracking-[-2.6px] max-sm:tracking-[-1.6px]"
        style={delay(90)}
      >
        Chargeback risk, answered in rupees.
      </h1>
      <p className="rise mt-7 max-w-[60ch] text-[19px] leading-[1.55] text-secondary" style={delay(180)}>
        ChargebackLens gives each transaction a calibrated dispute probability, then recommends
        the rupee-optimal action: allow it, step it up to 3DS, or hold it for manual review.
      </p>
      <div className="rise mt-9 flex flex-wrap gap-3" style={delay(270)}>
        <Link href="/score" className="pill pill-ink lift">
          Open the app
        </Link>
        <Link href="/economics" className="pill pill-quiet lift">
          Explore the economics
        </Link>
      </div>
    </header>
  );
}

function RoutingPanel({ meta }: { meta: Meta | null }) {
  const [examples, setExamples] = useState<LaneExamples | null>(null);

  useEffect(() => {
    let current = true;
    getLaneExamples(Math.max(...LANES.map((lane) => lane.chips))).then(
      (value) => current && setExamples(value),
      () => undefined, // the panel still reads without chips
    );
    return () => {
      current = false;
    };
  }, []);

  return (
    <section
      className="on-dark panel bg-ink text-white"
      aria-label="How the deployed policy routes transactions"
      data-testid="routing-panel"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-1">
        <h2 className="font-display text-[22px] font-semibold tracking-[-0.3px]">
          Three lanes, one decision per payment
        </h2>
        <p className="text-[13px] text-dark-muted">
          Chips are real rows from <code>05_scored_test_sample.csv</code>
        </p>
      </div>

      <div className="mt-8 grid gap-5">
        {LANES.map(({ action, chips, seconds }) => {
          const band = meta?.policy_bands.find((b) => b.band === action);
          const rows = examples?.[action].slice(0, chips) ?? [];
          return (
            <div key={action} className="grid items-center gap-x-8 gap-y-2 sm:grid-cols-[190px_1fr]">
              <div>
                <div className={`text-[16px] font-semibold ${ACTION_STYLE[action].onDark}`}>
                  {meta?.action_labels[action] ?? " "}
                </div>
                <div className="text-[13px] text-dark-muted">
                  {band ? `${pct(band.share_of_volume, 1)} of volume` : " "}
                </div>
              </div>
              <div className="flow-track relative h-11 overflow-hidden" aria-hidden="true">
                <div className="flow-line absolute top-1/2 right-0 left-0 h-px bg-white/15" />
                {rows.map((row, i) => (
                  <span
                    key={i}
                    className="flow-chip inline-flex h-8 items-center rounded-full bg-[#262a33] px-3.5 text-[13px] whitespace-nowrap text-white"
                    style={
                      {
                        "--duration": `${seconds}s`,
                        "--offset": `${-(seconds / chips) * i}s`,
                      } as CSSProperties
                    }
                    data-testid="lane-chip"
                  >
                    <span className="num font-semibold">{rupees(row.amount)}</span>
                    <span className="ml-1.5 text-dark-muted max-sm:hidden">
                      · {row.method} · {row.merchant_category}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Figure({
  label,
  target,
  format,
  sub,
}: {
  label: string;
  target: number | null;
  format: (value: number) => string;
  sub: string;
}) {
  const value = useCountUp(target);
  return (
    <div>
      <div className="label">{label}</div>
      <div
        className="num mt-1 text-[34px] leading-[1.15] font-semibold"
        data-testid="count-figure"
        data-final={target === null ? undefined : format(target)}
      >
        {value === null ? "—" : format(value)}
      </div>
      <div className="mt-1 text-[13px] text-secondary">{sub}</div>
    </div>
  );
}

function Figures({ meta }: { meta: Meta | null }) {
  const h = meta?.headline;
  return (
    <section
      aria-label="Headline figures"
      className="mt-16 grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-x-10 gap-y-9"
    >
      <Figure
        label="Net savings at the deployed policy"
        target={h?.net_savings_inr ?? null}
        format={rupees}
        sub={h ? `${pct(h.share_of_exposure, 1)} of a ${rupees(h.do_nothing_cost_inr)} exposure` : " "}
      />
      <Figure
        label="Lift at the top 1% of the queue"
        target={h?.lift_at_1pct ?? null}
        format={lift}
        sub={h ? `${count(h.caught_at_1pct)} disputes caught, precision ${pct(h.precision_at_1pct, 1)}` : " "}
      />
      <Figure
        label="Recall at the top 5%"
        target={h?.recall_at_5pct ?? null}
        format={(value) => pct(value, 1)}
        sub={h ? `precision ${pct(h.precision_at_5pct)} within that slice` : " "}
      />
      <Figure
        label="Held-out test transactions"
        target={h?.test_n ?? null}
        format={count}
        sub={h ? `${count(h.test_positives)} disputes, a ${pct(h.base_rate, 3)} base rate` : " "}
      />
    </section>
  );
}

const SECTION = "mt-[120px]";
const H2 =
  "reveal font-display max-w-[20ch] text-[clamp(32px,6vw,44px)] leading-[1.08] font-semibold tracking-[-1.2px]";

function Lanes({ meta }: { meta: Meta }) {
  const p = meta.economics_params;
  const friction = p.merchant_margin * p.step_up_abandon_rate;
  const maxRate = Math.max(...meta.policy_bands.map((b) => b.dispute_rate_in_band));

  const range: Record<Action, string> = {
    allow: `Score below ${cut(p.threshold_allow_stepup)}`,
    step_up: `Score from ${cut(p.threshold_allow_stepup)} to ${cut(p.threshold_stepup_review)}`,
    manual_review: `Score of ${cut(p.threshold_stepup_review)} or more`,
  };
  const price: Record<Action, string> = {
    allow: `If the payment is disputed, the merchant loses the amount, a ${rupees(p.dispute_fee)} dispute fee and ${rupees(p.ops_review_cost)} of operations time.`,
    step_up: `A customer sent to 3DS abandons ${pct(p.step_up_abandon_rate, 0)} of the time. At a ${pct(p.merchant_margin, 0)} margin that costs ${pct(friction, 1)} of the ticket.`,
    manual_review: `A human review costs ${rupees(p.ops_review_cost)} per transaction, whatever it finds.`,
  };

  return (
    <section className={SECTION} aria-labelledby="lanes-title">
      <h2 id="lanes-title" className={H2}>
        Three lanes, each priced in rupees
      </h2>
      <p className="reveal mt-5 max-w-[62ch] text-[17px] text-secondary">
        The policy is three bands, not two, and both cut points are optimised together against
        what each outcome costs.
      </p>
      <div className="mt-12 grid grid-cols-[repeat(auto-fit,minmax(min(290px,100%),1fr))] gap-x-14 gap-y-12">
        {meta.policy_bands.map((band) => (
          <div key={band.band} className="reveal" data-testid="lane">
            <h3 className={`font-display text-[26px] font-semibold tracking-[-0.5px] ${ACTION_STYLE[band.band].text}`}>
              {meta.action_labels[band.band]}
            </h3>
            <p className="num mt-1 text-[14px] text-muted">{range[band.band]}</p>
            <div className="mt-5 h-2 rounded-full bg-fill" aria-hidden="true">
              <div
                className={`grow-bar h-2 rounded-full ${BAR[band.band]}`}
                style={{ width: `${Math.max(2, (band.dispute_rate_in_band / maxRate) * 100)}%` }}
              />
            </div>
            <p className="mt-3 text-[15px]">
              <span className="num font-semibold">{pct(band.dispute_rate_in_band)}</span> dispute
              rate in band, <span className="num font-semibold">{lift(band.lift_vs_base)}</span>{" "}
              the base rate
            </p>
            <p className="text-[15px] text-secondary">
              {pct(band.share_of_volume, 1)} of volume · {count(band.n)} transactions
            </p>
            <p className="mt-4 text-[15px] text-secondary">{price[band.band]}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Steps({ meta }: { meta: Meta }) {
  const p = meta.economics_params;
  const card = meta.model_card;
  const steps = [
    {
      title: "Build the feature row",
      body: `${meta.contract.n_columns} features from the transaction, the customer and the merchant. Anything that is only knowable after the decision is left out.`,
    },
    {
      title: "Score it",
      body: `The deployed model (\`${card.selected_model}\` with ${card.calibration_method} calibration) returns a dispute probability that can be read as a rate.`,
    },
    {
      title: "Pick the lane",
      body: `Two cuts, at ${cut(p.threshold_allow_stepup)} and ${cut(p.threshold_stepup_review)}, split the score into allow, step-up and manual review.`,
    },
    {
      title: "Explain it",
      body: "The top drivers are exact log-odds contributions, and a short reviewer note names them in plain language.",
    },
  ];

  return (
    <section className={SECTION} aria-labelledby="steps-title">
      <h2 id="steps-title" className={H2}>
        How a decision is made
      </h2>
      <ol className="mt-12 grid grid-cols-[repeat(auto-fit,minmax(min(230px,100%),1fr))] gap-x-12 gap-y-10">
        {steps.map((step, i) => (
          <li key={step.title} className="reveal">
            <div className="num text-[15px] font-semibold text-muted">{fixed(i + 1, 0).padStart(2, "0")}</div>
            <h3 className="font-display mt-2 text-[20px] font-semibold tracking-[-0.3px]">{step.title}</h3>
            <p className="mt-2 text-[15px] text-secondary">
              <Prose text={step.body} />
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Limits({ meta }: { meta: Meta }) {
  return (
    <section className={SECTION} aria-labelledby="limits-title">
      <h2 id="limits-title" className={H2}>
        Four limits, stated up front
      </h2>
      <ol className="mt-12 grid grid-cols-[repeat(auto-fit,minmax(min(380px,100%),1fr))] gap-x-14 gap-y-10">
        {caveats(meta).map(({ lead, body }, i) => (
          <li key={lead} className="reveal" data-testid="limit">
            <div className="num text-[15px] font-semibold text-muted">{fixed(i + 1, 0).padStart(2, "0")}</div>
            <h3 className="font-display mt-2 text-[20px] leading-[1.3] font-semibold tracking-[-0.3px]">
              {lead.replace(/\.$/, "")}
            </h3>
            <p className="mt-2 text-[15px] text-secondary">
              <Prose text={body.replace(/^, the latest on/, "The latest was raised on").trim()} />
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Closing() {
  return (
    <section className={`${SECTION} reveal`} aria-labelledby="closing-title">
      <h2
        id="closing-title"
        className="font-display max-w-[18ch] text-[clamp(32px,6vw,44px)] leading-[1.08] font-semibold tracking-[-1.2px]"
      >
        Score a transaction and read the reasoning.
      </h2>
      <div className="mt-8 flex flex-wrap gap-3">
        <Link href="/score" className="pill pill-ink lift">
          Open the app
        </Link>
        <Link href="/queue" className="pill pill-quiet lift">
          See the review queue
        </Link>
      </div>
    </section>
  );
}
