import { ACTION_STYLE } from "@/lib/actions";
import type { Action } from "@/lib/api";
import { cut, pct } from "@/lib/format";

// The track is linear in log-odds between these two probabilities, which
// spreads out the low end where almost every transaction sits.
const P_MIN = 0.0005;
const P_MAX = 0.4;

const logit = (p: number) => Math.log(p / (1 - p));

/** Position along the track, 0-100, clamped at both ends. */
export function trackPosition(p: number): number {
  const t = (logit(p) - logit(P_MIN)) / (logit(P_MAX) - logit(P_MIN));
  return Math.min(1, Math.max(0, t)) * 100;
}

export function BandTrack({
  probability,
  action,
  actionLabel,
  cuts,
}: {
  probability: number;
  action: Action;
  actionLabel: string;
  cuts: { allow_stepup: number; stepup_review: number };
}) {
  return (
    <div
      role="img"
      aria-label={`Dispute probability ${pct(probability)}, in the ${actionLabel} band. Band cuts at ${cut(cuts.allow_stepup)} and ${cut(cuts.stepup_review)}.`}
      className="relative h-5"
      data-testid="band-track"
    >
      <div className="absolute top-1/2 right-0 left-0 h-1 -translate-y-1/2 rounded-full bg-ink/25" />
      {[cuts.allow_stepup, cuts.stepup_review].map((threshold) => (
        <div
          key={threshold}
          data-testid="band-cut"
          className="absolute top-0 h-5 w-0.5 -translate-x-1/2 bg-ink"
          style={{ left: `${trackPosition(threshold)}%` }}
        />
      ))}
      <div
        data-testid="band-dot"
        className={`absolute top-0 h-5 w-5 -translate-x-1/2 rounded-full ring-2 ring-white ${ACTION_STYLE[action].dot}`}
        style={{ left: `${trackPosition(probability)}%` }}
      />
    </div>
  );
}
