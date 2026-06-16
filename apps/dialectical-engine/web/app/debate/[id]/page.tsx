import DebatePageClient from "./DebatePageClient";
import { getDebateServer } from "@/lib/serverApi";
import type { DebateDetail } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function DebatePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let initialDebate: DebateDetail | null = null;
  let initialError: string | null = null;

  try {
    initialDebate = await getDebateServer(id);
  } catch (exc) {
    initialError = exc instanceof Error ? exc.message : "Unable to load debate";
  }

  return <DebatePageClient id={id} initialDebate={initialDebate} initialError={initialError} />;
}
