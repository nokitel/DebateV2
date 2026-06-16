import Link from "next/link";
import { listDebatesServer } from "@/lib/serverApi";
import type { DebateSummary } from "@/lib/types";

export default async function HomePage() {
  let debates: DebateSummary[] = [];
  let error: string | null = null;
  try {
    debates = await listDebatesServer();
  } catch (exc) {
    error = exc instanceof Error ? exc.message : "Unable to reach coordinator";
  }

  return (
    <main className="page">
      <div className="pageHeader">
        <div>
          <h1>Debates</h1>
          <p className="muted">Public archive of local multi-model debate trees.</p>
        </div>
        <Link href="/new">
          <button>New Debate</button>
        </Link>
      </div>
      {error ? <div className="error">{error}</div> : null}
      <div className="debateList">
        {debates.length === 0 ? (
          <div className="debateRow">
            <div>
              <h2>No debates yet</h2>
              <p className="muted">Create the first topic from the New page.</p>
            </div>
          </div>
        ) : (
          debates.map((debate) => (
            <Link key={debate.id} className="debateRow" href={`/debate/${debate.id}`}>
              <div>
                <h2>{debate.topic}</h2>
                <p className="muted">{new Date(debate.created_at).toLocaleString()}</p>
                {debate.models.length ? (
                  <div className="toolbar">
                    {debate.models.map((model) => (
                      <span key={model} className="badge">
                        {model}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
              <span className="statusPill">{debate.status}</span>
            </Link>
          ))
        )}
      </div>
    </main>
  );
}
