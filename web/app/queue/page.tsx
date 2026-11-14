import type { Metadata } from "next";

import { QueueScreen } from "@/components/QueueScreen";

export const metadata: Metadata = { title: "Review queue" };

export default function Page() {
  return <QueueScreen />;
}
