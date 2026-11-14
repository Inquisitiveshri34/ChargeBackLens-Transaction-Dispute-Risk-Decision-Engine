"use client";

import type { SweepPoint } from "@/lib/api";
import { cut, fixed, lakhs, rupees } from "@/lib/format";
import { useWidth } from "@/lib/hooks";

const HEIGHT = 360;
const MARGIN = { top: 14, right: 18, bottom: 30, left: 62 };
const X_STEP = 0.02;
const MAX_Y_TICKS = 7;

/** Smallest 1/2/5 x 10^k step (in rupees) that needs at most MAX_Y_TICKS ticks. */
function yTicks(min: number, max: number): number[] {
  const lo = Math.min(min, 0);
  const hi = Math.max(max, 0);
  for (let magnitude = 1e4; magnitude <= 1e12; magnitude *= 10) {
    for (const base of [1, 2, 5]) {
      const step = base * magnitude;
      const first = Math.floor(lo / step);
      const last = Math.ceil(hi / step);
      if (last - first + 1 <= MAX_Y_TICKS) {
        return Array.from({ length: last - first + 1 }, (_, i) => (first + i) * step);
      }
    }
  }
  return [lo, hi];
}

/**
 * Net savings of a single-threshold policy across the score, with the two
 * optimised cuts drawn over it. Hand-built SVG; drawn at the container's real
 * pixel width so text is never scaled.
 */
export function SweepChart({
  sweep,
  xMax,
  allowCut,
  reviewCut,
}: {
  sweep: SweepPoint[];
  xMax: number;
  allowCut: number;
  reviewCut: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();

  const ticksY = yTicks(
    Math.min(...sweep.map((p) => p.net_savings_inr)),
    Math.max(...sweep.map((p) => p.net_savings_inr)),
  );
  const yLo = ticksY[0];
  const yHi = ticksY[ticksY.length - 1];

  const plotW = Math.max(0, width - MARGIN.left - MARGIN.right);
  const plotH = HEIGHT - MARGIN.top - MARGIN.bottom;
  const x = (t: number) => MARGIN.left + (t / xMax) * plotW;
  const y = (v: number) => MARGIN.top + (1 - (v - yLo) / (yHi - yLo)) * plotH;

  const ticksX: number[] = [];
  for (let i = 0; i * X_STEP <= xMax + 1e-9; i++) ticksX.push(i * X_STEP);
  // On a phone, label every other tick so the labels do not collide.
  const labelEvery = plotW / ticksX.length < 44 ? 2 : 1;

  const line = sweep.map((p) => `${x(p.threshold)},${y(p.net_savings_inr)}`).join(" ");
  const best = sweep.reduce((a, b) => (b.net_savings_inr > a.net_savings_inr ? b : a));

  const cuts = [
    { name: "allow / step-up cut", value: allowCut, colour: "var(--color-stepup)", dash: "7 5" },
    { name: "step-up / review cut", value: reviewCut, colour: "var(--color-review)", dash: "2 4" },
  ];

  return (
    <figure>
      <ul className="flex flex-wrap gap-x-7 gap-y-1 text-[13px] text-secondary" data-testid="chart-legend">
        <li className="flex min-h-7 items-center gap-2">
          <svg width="26" height="8" aria-hidden="true">
            <line x1="0" y1="4" x2="26" y2="4" stroke="var(--color-ink)" strokeWidth="2.5" />
          </svg>
          Net savings (single threshold)
        </li>
        {cuts.map((c) => (
          <li key={c.name} className="flex min-h-7 items-center gap-2">
            <svg width="26" height="8" aria-hidden="true">
              <line x1="0" y1="4" x2="26" y2="4" stroke={c.colour} strokeWidth="2" strokeDasharray={c.dash} />
            </svg>
            <span>
              {c.name} <span className="num">{cut(c.value)}</span>
              {c.value > xMax && " (beyond the chart range)"}
            </span>
          </li>
        ))}
      </ul>

      <div ref={ref} className="mt-3" style={{ height: HEIGHT }}>
        {width > 0 && (
          <svg
            width={width}
            height={HEIGHT}
            role="img"
            data-testid="sweep-chart"
            aria-label={`Net savings of a single-threshold policy by threshold. It peaks at ${rupees(best.net_savings_inr)} at a threshold of ${cut(best.threshold)}. The optimised cuts are ${cut(allowCut)} and ${cut(reviewCut)}.`}
          >
            <defs>
              <clipPath id="sweep-plot">
                <rect x={MARGIN.left} y={MARGIN.top} width={plotW} height={plotH} />
              </clipPath>
            </defs>

            {ticksY.map((value) => (
              <g key={value}>
                <line
                  x1={MARGIN.left}
                  x2={MARGIN.left + plotW}
                  y1={y(value)}
                  y2={y(value)}
                  stroke={value === 0 ? "#b9bdc9" : "var(--color-hairline)"}
                  strokeWidth="1"
                />
                <text
                  x={MARGIN.left - 10}
                  y={y(value)}
                  dy="0.32em"
                  textAnchor="end"
                  fontSize="12"
                  fill="var(--color-muted)"
                  data-testid="y-tick"
                >
                  {lakhs(value)}
                </text>
              </g>
            ))}

            {ticksX.map((value, i) => (
              <g key={value}>
                <line
                  x1={x(value)}
                  x2={x(value)}
                  y1={MARGIN.top + plotH}
                  y2={MARGIN.top + plotH + 5}
                  stroke="#b9bdc9"
                />
                {i % labelEvery === 0 && (
                  <text
                    x={x(value)}
                    y={HEIGHT - 6}
                    textAnchor="middle"
                    fontSize="12"
                    fill="var(--color-muted)"
                    data-testid="x-tick"
                  >
                    {fixed(value, 2)}
                  </text>
                )}
              </g>
            ))}

            <g clipPath="url(#sweep-plot)">
              {cuts
                .filter((c) => c.value <= xMax)
                .map((c) => (
                  <line
                    key={c.name}
                    x1={x(c.value)}
                    x2={x(c.value)}
                    y1={MARGIN.top}
                    y2={MARGIN.top + plotH}
                    stroke={c.colour}
                    strokeWidth="2"
                    strokeDasharray={c.dash}
                    data-testid="cut-line"
                  />
                ))}
              <polyline
                points={line}
                fill="none"
                stroke="var(--color-ink)"
                strokeWidth="2.5"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            </g>
          </svg>
        )}
      </div>

      <figcaption className="mt-2 text-center text-[13px] text-secondary">
        Threshold on calibrated probability (x) · Net savings in ₹ lakh (y)
      </figcaption>
    </figure>
  );
}
