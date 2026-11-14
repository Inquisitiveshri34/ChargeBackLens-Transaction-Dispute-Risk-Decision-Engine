import type { Metadata } from "next";

import { ScoreScreen } from "@/components/ScoreScreen";

export const metadata: Metadata = { title: "Score a transaction" };

export default function Page() {
  return <ScoreScreen />;
}
