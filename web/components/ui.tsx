"use client";

import { type ReactNode, useId, useState } from "react";

/** Turns `backticked` spans in a sentence into <code>, so copy stays one string. */
export function Prose({ text }: { text: string }) {
  return (
    <>
      {text.split("`").map((part, i) => (i % 2 ? <code key={i}>{part}</code> : part))}
    </>
  );
}

export function Metric({
  label,
  value,
  sub,
  valueClass = "",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  valueClass?: string;
}) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className={`num mt-1 text-[34px] leading-[1.15] font-semibold ${valueClass}`}>{value}</div>
      {sub && <div className="mt-1 text-[13px] text-secondary">{sub}</div>}
    </div>
  );
}

/** A text link that opens and closes the content under it. */
export function Disclosure({ label, children }: { label: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div>
      <button
        type="button"
        className="link-btn"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((value) => !value)}
      >
        {label}
        <span aria-hidden="true" className="ml-2 inline-block no-underline">
          {open ? "−" : "+"}
        </span>
      </button>
      <div id={id} hidden={!open} className="mt-4">
        {children}
      </div>
    </div>
  );
}

export function LoadError({ message }: { message: string }) {
  return (
    <p role="alert" className="mt-10 text-[15px] font-medium text-review">
      {message}
    </p>
  );
}

export function Loading({ what }: { what: string }) {
  return (
    <p role="status" className="mt-10 text-[15px] text-muted">
      Loading {what}…
    </p>
  );
}
