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
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const debate = await createDebate(trimmedQuestion, { mode: "single_shot" }, token);
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
          <p className="muted">Ask one question and run a single debate pass.</p>
        </div>
      </div>
      <form className="formPanel" onSubmit={submit}>
        {error ? <div className="error">{error}</div> : null}
        <div className="field">
          <label htmlFor="question">Question</label>
          <textarea
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            required
            disabled={submitting}
          />
        </div>
        <div className="toolbar">
          <button type="submit" disabled={submitting || !question.trim()}>
            {submitting ? "Running..." : "Run Debate"}
          </button>
          {submitting ? <span className="muted">Waiting for the single-shot result...</span> : null}
        </div>
      </form>
    </main>
  );
}
