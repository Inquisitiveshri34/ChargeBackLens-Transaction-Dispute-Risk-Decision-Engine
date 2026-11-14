/**
 * The API client. Requests go to /api/* on this origin; next.config.ts forwards
 * them to the FastAPI server, so the browser never needs a second origin.
 *
 * No feature list, column order or threshold is defined here. The types
 * describe shapes; the values all come from the responses.
 */

export type Action = "allow" | "step_up" | "manual_review";

export interface MerchantDefaults {
  avg_ticket_size: number;
  refund_window_days: number;
  delivery_sla_days: number;
  is_physical_goods: number;
}

export interface PolicyBand {
  band: Action;
  lower: number;
  upper: number;
  n: number;
  disputes: number;
  share_of_volume: number;
  dispute_rate_in_band: number;
  lift_vs_base: number;
}

export interface Meta {
  model_card: Record<string, string>;
  contract: { n_columns: number; n_features_in: number | null; feature_names_checked: boolean };
  feature_columns: { name: string; role: string; order: number }[];
  economics_params: {
    dispute_fee: number;
    ops_review_cost: number;
    merchant_margin: number;
    step_up_abandon_rate: number;
    threshold_allow_stepup: number;
    threshold_stepup_review: number;
    net_savings_inr_at_policy: number;
    do_nothing_cost_inr: number;
  };
  policy_bands: PolicyBand[];
  censoring_audit: {
    test_positives: number;
    raised_after_snapshot: number;
    share_after_snapshot: number;
    max_raised_at: string;
  };
  headline: {
    net_savings_inr: number;
    do_nothing_cost_inr: number;
    share_of_exposure: number;
    lift_at_1pct: number;
    precision_at_1pct: number;
    caught_at_1pct: number;
    precision_at_5pct: number;
    recall_at_5pct: number;
    review_band_n: number;
    review_band_lift: number;
    base_rate: number;
    test_positives: number;
    test_n: number;
    max_proba: number;
  };
  categorical_levels: Record<"method" | "merchant_category" | "email_domain_type", string[]>;
  merchant_defaults: Record<string, MerchantDefaults>;
  action_labels: Record<Action, string>;
  economics_basis: { label: string; is_exact: boolean };
  queue_sample_size: number;
  reviewer_note_source: NoteSource;
}

export type NoteSource = "template" | "anthropic-api";

export interface Driver {
  feature: string;
  term: string;
  label: string;
  contribution: number;
  direction: "raises risk" | "lowers risk";
}

export interface ScoreResult {
  probability: number;
  base_rate: number;
  lift_vs_base: number;
  action: Action;
  action_label: string;
  thresholds: { allow_stepup: number; stepup_review: number };
  costs: { fn_cost: number; fp_cost: number; tp_cost: number; tn_cost: number };
  drivers: Driver[];
  drivers_method: string;
  reviewer_note: string;
  reviewer_note_source: NoteSource;
  feature_row: { name: string; value: number | string | null }[];
}

export interface QueueRow {
  payment_id: string;
  created_at: string;
  amount: number;
  method: string;
  merchant_category: string;
  proba_calibrated: number;
  risk_percentile: number;
  recommended_action: Action;
  is_disputed: boolean;
  risk_pct: number;
  percentile: number;
}

export interface QueueSlice {
  top_k_pct: number;
  sample_size: number;
  metrics: {
    transactions: number;
    disputes_caught: number;
    precision: number;
    exposure_inr: number;
  };
  rows: QueueRow[];
}

export interface QueueDetail {
  payment_id: string;
  probability: number;
  base_rate: number;
  lift_vs_base: number;
  action: Action;
  action_label: string;
  amount: number;
  reviewer_note: string;
  reviewer_note_source: NoteSource;
}

export interface CostParams {
  dispute_fee: number;
  ops_review_cost: number;
  merchant_margin: number;
  step_up_abandon_rate: number;
}

export interface SegmentRow {
  segment_type: string;
  segment_value: string;
  n: number;
  dispute_rate: number; // a fraction: multiply by 100 to show a percentage
  mean_amount: number;
  net_savings_at_global_policy: number;
  savings_per_intervention: number | null;
  review_band_net_inr: number;
  n_review: number;
  stepup_band_net_inr: number;
  n_stepup: number;
}

export interface SweepPoint {
  threshold: number;
  net_savings_inr: number;
  total_cost_inr: number;
  n_flagged: number;
}

export interface EconomicsResult {
  params: CostParams;
  basis: { label: string; is_exact: boolean };
  at_default: boolean;
  reproduces_export: boolean;
  exported_policy: {
    net_savings_inr: number;
    threshold_allow_stepup: number;
    threshold_stepup_review: number;
  };
  baseline_shifted: boolean;
  bands: {
    threshold_allow_stepup: number;
    threshold_stepup_review: number;
    n_review: number;
    n_stepup: number;
    n_allow: number;
    interventions: number;
    total_cost_inr: number;
    do_nothing_cost_inr: number;
    net_savings_inr: number;
    share_of_exposure: number;
  };
  single_threshold: { threshold: number; net_savings_inr: number; second_cut_value_inr: number };
  sweep: SweepPoint[];
  x_max: number;
  segments: { source: "frozen" | "live"; rows: SegmentRow[] };
}

export interface Sensitivity {
  columns: string[];
  rows: Record<string, number | string | null>[];
}

export interface LaneChip {
  amount: number;
  method: string;
  merchant_category: string;
}

export type LaneExamples = Record<Action, LaneChip[]>;

/** An error the API explained. `fields` names the inputs at fault, if any. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly fields: { field: string; message: string }[] = [],
  ) {
    super(message);
  }
}

// A hosted API on a free plan sleeps when idle and takes up to a minute to
// wake. While it does, the proxy in front of it answers 502, 503 or 504. Those
// three mean "not ready yet", so the request is tried again on this schedule
// (about 75 seconds in all) before the visitor is shown an error. Every
// endpoint is a pure read or a pure calculation, so repeating one is safe.
const NOT_READY = new Set([502, 503, 504]);
const RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 10000, 10000, 10000, 10000, 10000, 10000];

function pause(ms: number, signal?: AbortSignal | null): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", abort);
      resolve();
    }, ms);
    if (signal?.aborted) abort();
    else signal?.addEventListener("abort", abort, { once: true });
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  for (let attempt = 0; ; attempt++) {
    try {
      response = await fetch(path, init);
    } catch (error) {
      if ((error as Error).name === "AbortError") throw error;
      throw new ApiError("The scoring API could not be reached. Check that it is running.", 0);
    }
    if (!NOT_READY.has(response.status) || attempt >= RETRY_DELAYS_MS.length) break;
    await pause(RETRY_DELAYS_MS[attempt], init?.signal);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      body?.message ?? `The scoring API returned an error (${response.status}).`,
      response.status,
      body?.fields ?? [],
    );
  }
  return response.json();
}

const post = <T>(path: string, body: unknown, signal?: AbortSignal) =>
  request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

let woken = false;

/**
 * Called once when the site opens, from any page. A sleeping API starts waking
 * now, so it is ready by the time the visitor asks it for something.
 */
export function wakeApi(): void {
  if (woken) return;
  woken = true;
  fetch("/api/health", { cache: "no-store" }).catch(() => undefined);
}

let metaPromise: Promise<Meta> | null = null;

/** Fetched once per page load; a failed attempt is not cached. */
export function getMeta(): Promise<Meta> {
  if (!metaPromise) {
    metaPromise = request<Meta>("/api/meta").catch((error) => {
      metaPromise = null;
      throw error;
    });
  }
  return metaPromise;
}

export const scoreTransaction = (form: Record<string, unknown>) =>
  post<ScoreResult>("/api/score", form);

export const getQueue = (topKPct: number, signal?: AbortSignal) =>
  request<QueueSlice>(`/api/queue?top_k_pct=${topKPct}`, { signal });

export const getQueueDetail = (paymentId: string, signal?: AbortSignal) =>
  request<QueueDetail>(`/api/queue/${encodeURIComponent(paymentId)}`, { signal });

export const runEconomics = (params: CostParams, liveSegments: boolean, signal?: AbortSignal) =>
  post<EconomicsResult>("/api/economics", { ...params, live_segments: liveSegments }, signal);

export const getSensitivity = () => request<Sensitivity>("/api/sensitivity");

export const getLaneExamples = (perBand: number) =>
  request<LaneExamples>(`/api/lane-examples?per_band=${perBand}`);
