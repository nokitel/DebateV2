"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { createDebate } from "@/lib/api";
import { AuthGate } from "@/components/AuthGate";

export default function NewDebatePage() {
  return <AuthGate>{(token) => <NewDebateForm token={token} />}</AuthGate>;
}

function NewDebateForm({ token }: { token: string }) {
  const router = useRouter();
  const [topic, setTopic] = useState("");
  const [depth, setDepth] = useState(2);
  const [branching, setBranching] = useState(2);
  const [maxTokens, setMaxTokens] = useState(800);
  const [roleOverrides, setRoleOverrides] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const config: Record<string, unknown> = { max_depth: depth, branching, max_tokens: maxTokens };
      const cleanedOverrides = roleOverrides.trim();
      if (cleanedOverrides) {
        const parsed = JSON.parse(cleanedOverrides) as unknown;
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("Role overrides must be a JSON object.");
        }
        config.role_overrides = parsed;
      }
      const debate = await createDebate(topic, config, token);
      router.push(`/debate/${debate.id}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to create debate");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page">
      <div className="pageHeader">
        <div>
          <h1>New Debate</h1>
          <p className="muted">Post a topic and let local workers build the Pro/Con debate tree.</p>
        </div>
      </div>
      <form className="formPanel" onSubmit={submit}>
        {error ? <div className="error">{error}</div> : null}
        <div className="field">
          <label htmlFor="topic">Topic</label>
          <textarea id="topic" value={topic} onChange={(event) => setTopic(event.target.value)} required />
        </div>
        <div className="formGrid">
          <div className="field">
            <label htmlFor="depth">Depth</label>
            <input id="depth" type="number" min={1} max={5} value={depth} onChange={(event) => setDepth(Number(event.target.value))} />
          </div>
          <div className="field">
            <label htmlFor="branching">Branching</label>
            <input
              id="branching"
              type="number"
              min={2}
              max={6}
              value={branching}
              onChange={(event) => setBranching(Number(event.target.value))}
            />
          </div>
          <div className="field">
            <label htmlFor="tokens">Max tokens</label>
            <input
              id="tokens"
              type="number"
              min={128}
              max={4000}
              value={maxTokens}
              onChange={(event) => setMaxTokens(Number(event.target.value))}
            />
          </div>
        </div>
        <div className="field">
          <label htmlFor="roleOverrides">Role overrides JSON</label>
          <textarea
            id="roleOverrides"
            value={roleOverrides}
            onChange={(event) => setRoleOverrides(event.target.value)}
            spellCheck={false}
          />
        </div>
        <div className="toolbar">
          <button type="submit" disabled={submitting}>
            Create
          </button>
        </div>
      </form>
    </main>
  );
}
