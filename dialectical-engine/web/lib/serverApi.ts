import type { DebateDetail, DebateSummary } from "./types";

function serverApiBase(): string {
  return process.env.DIALECTICAL_COORDINATOR_URL || process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
}

async function serverFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${serverApiBase()}${path}`, { cache: "no-store" });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function listDebatesServer(): Promise<DebateSummary[]> {
  const payload = await serverFetch<{ items: DebateSummary[] }>("/api/debates");
  return payload.items;
}

export async function getDebateServer(id: string): Promise<DebateDetail> {
  return serverFetch<DebateDetail>(`/api/debates/${id}`);
}
