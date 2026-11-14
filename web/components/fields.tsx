"use client";

import { type CSSProperties, useId } from "react";

/** Form controls. Each is a real input with a real label; hints are tied on with aria-describedby. */

interface Base {
  label: string;
  hint?: string;
}

export function NumberField({
  label,
  hint,
  value,
  onChange,
  min,
  max,
  step,
  disabled,
}: Base & {
  value: string;
  onChange: (value: string) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="label mb-1.5 block">
        {label}
      </label>
      <input
        id={id}
        type="number"
        inputMode="decimal"
        className="input"
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {hint && (
        <p id={`${id}-hint`} className="hint mt-1.5">
          {hint}
        </p>
      )}
    </div>
  );
}

export function DateField({
  label,
  value,
  onChange,
}: Base & { value: string; onChange: (value: string) => void }) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="label mb-1.5 block">
        {label}
      </label>
      <input
        id={id}
        type="date"
        className="input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

export function SelectField({
  label,
  value,
  onChange,
  options,
}: Base & { value: string; onChange: (value: string) => void; options: string[] }) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="label mb-1.5 block">
        {label}
      </label>
      <select
        id={id}
        className="input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}

export function SliderField({
  label,
  hint,
  value,
  onChange,
  min,
  max,
  step,
  format = String,
}: Base & {
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step: number;
  format?: (value: number) => string;
}) {
  const id = useId();
  const fill = ((value - min) / (max - min)) * 100;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-4">
        <label htmlFor={id} className="label">
          {label}
        </label>
        <output htmlFor={id} className="num text-[15px] font-semibold">
          {format(value)}
        </output>
      </div>
      <input
        id={id}
        type="range"
        className="slider"
        style={{ "--pct": `${fill}%` } as CSSProperties}
        value={value}
        min={min}
        max={max}
        step={step}
        aria-valuetext={format(value)}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      {hint && (
        <p id={`${id}-hint`} className="hint">
          {hint}
        </p>
      )}
    </div>
  );
}

export function CheckField({
  label,
  checked,
  onChange,
}: Base & { checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className="flex min-h-11 cursor-pointer items-center gap-3 text-[15px]">
      <input
        type="checkbox"
        className="check"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      {label}
    </label>
  );
}

/** An on/off switch. A checkbox underneath, announced as a switch. */
export function SwitchField({
  label,
  hint,
  checked,
  onChange,
}: Base & { checked: boolean; onChange: (checked: boolean) => void }) {
  const id = useId();
  return (
    <div>
      <label className="flex min-h-11 cursor-pointer items-center gap-3 text-[15px] font-medium">
        <span className="relative inline-flex h-7 w-12 flex-none">
          <input
            type="checkbox"
            role="switch"
            className="peer absolute inset-0 h-full w-full cursor-pointer appearance-none rounded-full bg-muted checked:bg-ink"
            checked={checked}
            aria-describedby={hint ? `${id}-hint` : undefined}
            onChange={(event) => onChange(event.target.checked)}
          />
          <span
            aria-hidden="true"
            className="pointer-events-none absolute top-1 left-1 h-5 w-5 rounded-full bg-white peer-checked:translate-x-5"
          />
        </span>
        {label}
        <span className="text-[13px] font-normal text-muted">{checked ? "On" : "Off"}</span>
      </label>
      {hint && (
        <p id={`${id}-hint`} className="hint mt-1">
          {hint}
        </p>
      )}
    </div>
  );
}
