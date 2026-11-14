import type { Metadata } from "next";

import { EconomicsScreen } from "@/components/EconomicsScreen";

export const metadata: Metadata = { title: "Economics explorer" };

export default function Page() {
  return <EconomicsScreen />;
}
