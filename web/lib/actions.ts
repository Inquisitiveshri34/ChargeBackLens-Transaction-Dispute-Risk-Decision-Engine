import type { Action } from "./api";

/**
 * How each action looks. Colour never carries the meaning alone: every use of
 * these classes sits next to the action's text label.
 */
export const ACTION_STYLE: Record<
  Action,
  { text: string; tint: string; dot: string; onDark: string; sentence: string }
> = {
  allow: {
    text: "text-allow",
    tint: "bg-allow-tint",
    dot: "bg-allow-bar",
    onDark: "text-dark-allow",
    sentence: "Let this payment through.",
  },
  step_up: {
    text: "text-stepup",
    tint: "bg-stepup-tint",
    dot: "bg-stepup",
    onDark: "text-dark-stepup",
    sentence: "Ask the customer for 3DS authentication.",
  },
  manual_review: {
    text: "text-review",
    tint: "bg-review-tint",
    dot: "bg-review-bar",
    onDark: "text-dark-review",
    sentence: "Hold for a human reviewer before capture.",
  },
};
