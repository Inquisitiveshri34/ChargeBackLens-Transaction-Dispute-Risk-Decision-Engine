/**
 * Display formatting. Every number arrives from the API unrounded; the rules
 * here are the only place rounding happens in the front end.
 *
 * Python formats with round-half-to-even on the exact binary value. JavaScript's
 * toFixed breaks exact ties upward, so `fixed` corrects that one case to keep
 * the two UIs showing the same digits (382.5 is ₹382 in both).
 */

const MINUS = "−";
const DASH = "—";

/** Same digits as Python's format(x, ".Nf"). ASCII minus; callers swap it. */
export function fixed(x: number, decimals: number): string {
  if (!Number.isFinite(x)) return DASH;
  const naive = x.toFixed(decimals);
  // A double's decimal expansion is finite, so a tie shows up as the digit 5
  // followed by nothing but zeros.
  const exact = Math.abs(x).toFixed(100);
  const cut = exact.indexOf(".") + 1 + decimals;
  if (!/^50*$/.test(exact.slice(cut))) return naive;
  const kept = exact.slice(0, cut).replace(/\.$/, "");
  const lastDigit = Number(kept[kept.length - 1]);
  if (lastDigit % 2 === 1) return naive; // rounding up lands on the even digit
  return (x < 0 ? "-" : "") + kept;
}

const trueMinus = (text: string) => text.replace("-", MINUS);

function groupIndian(digits: string): string {
  if (digits.length <= 3) return digits;
  const tail = digits.slice(-3);
  let head = digits.slice(0, -3);
  const groups: string[] = [];
  while (head.length > 2) {
    groups.unshift(head.slice(-2));
    head = head.slice(0, -2);
  }
  if (head) groups.unshift(head);
  return [...groups, tail].join(",");
}

/** ₹11,99,620 — Indian grouping, whole rupees, true minus sign. */
export function rupees(x: number | null | undefined): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return DASH;
  return `${x < 0 ? MINUS : ""}₹${groupIndian(fixed(Math.abs(x), 0))}`;
}

/** A fraction as a percentage: pct(0.0046) is "0.46%". */
export function pct(fraction: number | null | undefined, decimals = 2): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return DASH;
  return `${trueMinus(fixed(fraction * 100, decimals))}%`;
}

/** A threshold on the calibrated probability: 0.0244. */
export function cut(threshold: number): string {
  return fixed(threshold, 4);
}

/** 16.2× */
export function lift(x: number): string {
  return `${fixed(x, 1)}×`;
}

/** +1.872 / −1.410 */
export function signed3(x: number): string {
  return `${x < 0 ? MINUS : "+"}${fixed(Math.abs(x), 3)}`;
}

/** 45,246 — counts use ordinary thousands grouping, as the Python f"{n:,}" does. */
export function count(x: number | null | undefined): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return DASH;
  return Math.round(x).toLocaleString("en-US");
}

/** Chart axis label in lakhs: ₹5L, −₹10L, 0. */
export function lakhs(x: number): string {
  if (x === 0) return "0";
  const value = Math.abs(x) / 1e5;
  return `${x < 0 ? MINUS : ""}₹${Number(value.toFixed(2))}L`;
}

/** 2026-08-10T19:15:25 -> 2026-08-10 19:15 */
export function minute(iso: string): string {
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)}`;
}

/** A model input as the feature table shows it: integers plain, floats to 6 places. */
export function featureValue(value: number | string | null): string {
  if (value === null) return DASH;
  if (typeof value === "string") return value;
  if (Number.isInteger(value)) return String(value);
  return String(Number(value.toFixed(6)));
}
