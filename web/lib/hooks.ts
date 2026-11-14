"use client";

import { useEffect, useState } from "react";

import { type Meta, getMeta } from "./api";

/** The /api/meta payload, or the reason it could not be loaded. */
export function useMeta(): { meta: Meta | null; error: string | null } {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getMeta().then(
      (value) => live && setMeta(value),
      (reason: Error) => live && setError(reason.message),
    );
    return () => {
      live = false;
    };
  }, []);

  return { meta, error };
}

/** True when the visitor has asked the system for reduced motion. */
export function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Ease a figure from 0 to `target` over 1.5s (ease-out cubic). A 2.5s timer
 * sets the final value regardless, so a throttled tab cannot leave a figure
 * stuck part-way. With reduced motion the final value shows immediately.
 */
export function useCountUp(target: number | null, durationMs = 1500): number | null {
  const [value, setValue] = useState<number | null>(null);

  useEffect(() => {
    if (target === null) return;
    if (prefersReducedMotion()) {
      setValue(target);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      setValue(target * (1 - Math.pow(1 - t, 3)));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    const safety = setTimeout(() => {
      cancelAnimationFrame(frame);
      setValue(target);
    }, 2500);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(safety);
    };
  }, [target, durationMs]);

  return value;
}

/** Width of an element, tracked as it resizes. 0 until first measured. */
export function useWidth<T extends HTMLElement>(): [(node: T | null) => void, number] {
  const [node, setNode] = useState<T | null>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(node);
    return () => observer.disconnect();
  }, [node]);

  return [setNode, width];
}
