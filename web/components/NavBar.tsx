"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { wakeApi } from "@/lib/api";

const LINKS = [
  { href: "/score", label: "Score a Transaction" },
  { href: "/queue", label: "Review Queue" },
  { href: "/economics", label: "Economics Explorer" },
] as const;

const ITEM =
  "inline-flex min-h-11 items-center rounded-full px-4 text-[14px] font-medium whitespace-nowrap";

export function Logo({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9.25" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="12" cy="12" r="4.25" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12 2.75a9.25 9.25 0 0 1 9.25 9.25" stroke="currentColor" strokeWidth="3" />
    </svg>
  );
}

export function NavBar() {
  const pathname = usePathname();

  // The bar is on every page, so this is the one place that runs on any entry.
  useEffect(wakeApi, []);

  return (
    <div className="on-dark sticky top-[14px] z-50 px-[28px]">
      <nav
        aria-label="Primary"
        className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-[30px] bg-ink py-2 pr-[10px] pl-[22px] shadow-[0_12px_32px_rgba(17,19,24,0.22)]"
      >
        <Link
          href="/"
          className="font-display inline-flex min-h-11 items-center gap-2.5 text-[17px] font-semibold text-white"
        >
          <Logo />
          ChargebackLens
        </Link>

        <div className="flex flex-wrap items-center gap-1">
          {LINKS.map(({ href, label }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`${ITEM} ${active ? "bg-white text-ink" : "text-nav-link hover:text-white"}`}
              >
                {label}
              </Link>
            );
          })}
          {pathname === "/" && (
            <Link href="/score" className={`${ITEM} lift bg-white font-semibold text-ink`}>
              Open the app
            </Link>
          )}
        </div>
      </nav>
    </div>
  );
}
