import type { Metadata } from "next";
import { Inter, Inter_Tight, JetBrains_Mono } from "next/font/google";

import { NavBar } from "@/components/NavBar";

import "./globals.css";

// next/font downloads these at build time and serves them from this origin, so
// the running site makes no request to Google.
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-inter",
  display: "swap",
});

const interTight = Inter_Tight({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-inter-tight",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "ChargebackLens", template: "%s · ChargebackLens" },
  description:
    "A calibrated chargeback-risk scorer that recommends the rupee-optimal action for each transaction: allow, step-up or manual review.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${interTight.variable} ${jetbrainsMono.variable} antialiased`}
    >
      <body className="pt-[14px]">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-7 focus:top-4 focus:z-[60] focus:rounded-full focus:bg-white focus:px-5 focus:py-3"
        >
          Skip to content
        </a>
        <NavBar />
        <main id="main">{children}</main>
      </body>
    </html>
  );
}
