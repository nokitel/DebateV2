"use client";

import { FormEvent, useEffect, useState } from "react";
import { clearStoredToken, getStoredToken, setStoredToken, validateUserToken } from "@/lib/api";

export function AuthGate({ children }: { children: (token: string) => React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [checking, setChecking] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function loadStoredToken() {
      const stored = getStoredToken();
      if (!stored) {
        return;
      }
      if (active) setChecking(true);
      try {
        await validateUserToken(stored);
        if (active) setToken(stored);
      } catch {
        clearStoredToken();
        if (active) setError("Saved token is no longer valid.");
      } finally {
        if (active) setChecking(false);
      }
    }
    loadStoredToken();
    return () => {
      active = false;
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const value = draft.trim();
    if (!value) return;
    setSubmitting(true);
    setError(null);
    try {
      await validateUserToken(value);
      setStoredToken(value);
      setToken(value);
    } catch {
      clearStoredToken();
      setError("Token was rejected by the coordinator.");
    } finally {
      setSubmitting(false);
    }
  }

  if (checking) {
    return (
      <main className="page">
        <p className="muted">Checking token...</p>
      </main>
    );
  }

  if (!token) {
    return (
      <main className="page">
        <div className="pageHeader">
          <div>
            <h1>Bearer Token</h1>
            <p className="muted">Enter the user token printed by the coordinator on first boot.</p>
          </div>
        </div>
        <form className="formPanel" onSubmit={submit}>
          {error ? <div className="error">{error}</div> : null}
          <div className="field">
            <label htmlFor="token">User token</label>
            <input
              id="token"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              type="password"
              autoComplete="off"
              autoFocus
            />
          </div>
          <div className="toolbar">
            <button type="submit" disabled={submitting}>
              {submitting ? "Checking..." : "Unlock"}
            </button>
          </div>
        </form>
      </main>
    );
  }

  return <>{children(token)}</>;
}
