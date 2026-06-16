import type { DebateDetail, DebateSummary, Generation, WorkerStatus } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("dialectical:userToken");
}

export function setStoredToken(token: string): void {
  window.localStorage.setItem("dialectical:userToken", token);
}

export function clearStoredToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem("dialectical:userToken");
}

export async function apiFetch<T>(path: string, init: RequestInit = {}, token?: string | null): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store"
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function listDebates(): Promise<DebateSummary[]> {
  const payload = await apiFetch<{ items: DebateSummary[] }>("/api/debates");
  return payload.items;
}

export async function getDebate(id: string): Promise<DebateDetail> {
  return apiFetch<DebateDetail>(`/api/debates/${id}`);
}

export async function createDebate(topic: string, config: Record<string, unknown>, token: string): Promise<DebateDetail> {
  return apiFetch<DebateDetail>(
    "/api/debates",
    {
      method: "POST",
      body: JSON.stringify({ topic, config })
    },
    token
  );
}

export async function regenerateNode(nodeId: string, token: string, modelId?: string): Promise<{ job_id: string }> {
  return apiFetch<{ job_id: string }>(
    `/api/nodes/${nodeId}/regenerate`,
    {
      method: "POST",
      body: JSON.stringify({ model_id: modelId || null })
    },
    token
  );
}

export async function nodeGenerations(nodeId: string, token: string): Promise<Generation[]> {
  const payload = await apiFetch<{ items: Generation[] }>(`/api/nodes/${nodeId}/generations`, {}, token);
  return payload.items;
}

export async function backendStatus(): Promise<WorkerStatus[]> {
  const payload = await apiFetch<{ workers: WorkerStatus[] }>("/api/backends/status");
  return payload.workers;
}

export async function validateUserToken(token: string): Promise<void> {
  await apiFetch<Record<string, unknown>>("/api/settings", {}, token);
}
