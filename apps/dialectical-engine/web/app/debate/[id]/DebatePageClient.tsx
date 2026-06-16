"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE, clearStoredToken, getDebate, getStoredToken, setStoredToken, validateUserToken } from "@/lib/api";
import type { DebateDetail, DebateNode, SingleShotResult } from "@/lib/types";
import { DebateTree } from "@/components/DebateTree";
import { ArgumentFocusView } from "@/components/ArgumentFocusView";
import { findNodeById, findNodePathById, initialFocusedNodeId, nearestExistingNodeId } from "@/lib/debateTreeUtils";

type SynthesisDraft = {
  model_id?: string;
  worker_id?: string;
  raw: string;
};

type StreamState = {
  status: "connecting" | "live" | "reconnecting";
  retryInMs?: number;
};

function parseEventData(event: Event): Record<string, unknown> | null {
  const data = (event as MessageEvent).data;
  if (typeof data !== "string" || !data) return null;
  try {
    const payload = JSON.parse(data);
    return payload && typeof payload === "object" ? (payload as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function payloadString(payload: Record<string, unknown> | null, key: string): string | undefined {
  const value = payload?.[key];
  return typeof value === "string" ? value : undefined;
}

function decodeJsonSnippet(value: string): string {
  try {
    return JSON.parse(`"${value}"`) as string;
  } catch {
    return value.replace(/\\"/g, '"').replace(/\\\\/g, "\\");
  }
}

function partialJsonField(raw: string, key: string): string {
  const keyIndex = raw.indexOf(`"${key}"`);
  if (keyIndex < 0) return "";
  const colonIndex = raw.indexOf(":", keyIndex);
  if (colonIndex < 0) return "";
  const quoteIndex = raw.indexOf('"', colonIndex);
  if (quoteIndex < 0) return "";
  let escaped = false;
  let value = "";
  for (let index = quoteIndex + 1; index < raw.length; index += 1) {
    const char = raw[index];
    if (escaped) {
      value += `\\${char}`;
      escaped = false;
      continue;
    }
    if (char === "\\") {
      escaped = true;
      continue;
    }
    if (char === '"') return decodeJsonSnippet(value);
    value += char;
  }
  return decodeJsonSnippet(value);
}

function activeSynthesisDraft(debate: DebateDetail | null): SynthesisDraft | null {
  if (!debate?.active_synthesis || debate.synthesis) return null;
  return {
    model_id: debate.active_synthesis.model_id,
    worker_id: debate.active_synthesis.worker_id,
    raw: debate.active_synthesis.raw || ""
  };
}

function provenanceLabel(provenance: Record<string, unknown>): string {
  const model = typeof provenance.model_id === "string" ? provenance.model_id : "";
  const worker = typeof provenance.worker_id === "string" ? provenance.worker_id : "";
  const prompt = typeof provenance.prompt_id === "string" ? provenance.prompt_id : "";
  return [model, worker, prompt].filter(Boolean).join(" - ");
}

function isSingleShotResult(value: unknown): value is SingleShotResult {
  if (!value || typeof value !== "object") return false;
  const result = value as Partial<SingleShotResult>;
  return (
    Array.isArray(result.pros) &&
    result.pros.every((item) => typeof item === "string") &&
    Array.isArray(result.cons) &&
    result.cons.every((item) => typeof item === "string") &&
    typeof result.strongest_pro === "string" &&
    typeof result.strongest_con === "string" &&
    Boolean(result.global_winner) &&
    typeof result.global_winner === "object" &&
    ["pro", "con", "balanced"].includes((result.global_winner as { side?: string }).side || "") &&
    typeof (result.global_winner as { reason?: unknown }).reason === "string" &&
    typeof result.final_text === "string" &&
    typeof result.model_id === "string" &&
    typeof result.tokens_in === "number" &&
    typeof result.tokens_out === "number" &&
    typeof result.created_at === "string"
  );
}

function appendToken(node: DebateNode, nodeId: string, delta: string): DebateNode {
  if (node.id === nodeId) {
    const generation = node.active_generation || {
      id: "streaming",
      model_id: "streaming",
      role: "streaming",
      argument: "",
      worker_id: "",
      created_at: new Date().toISOString()
    };
    return {
      ...node,
      status: "generating",
      active_generation: { ...generation, argument: `${generation.argument}${delta}` }
    };
  }
  return { ...node, children: node.children.map((child) => appendToken(child, nodeId, delta)) };
}

function beginNodeStream(
  node: DebateNode,
  payload: { node_id?: string; model_id?: string; worker_id?: string; role?: string }
): DebateNode {
  if (node.id === payload.node_id) {
    return {
      ...node,
      status: "generating",
      active_generation: {
        id: "streaming",
        model_id: payload.model_id || "streaming",
        role: payload.role || "streaming",
        argument: "",
        worker_id: payload.worker_id || "",
        created_at: new Date().toISOString()
      }
    };
  }
  return { ...node, children: node.children.map((child) => beginNodeStream(child, payload)) };
}

export default function DebatePageClient({
  id,
  initialDebate,
  initialError = null
}: {
  id: string;
  initialDebate: DebateDetail | null;
  initialError?: string | null;
}) {
  const [debate, setDebate] = useState<DebateDetail | null>(initialDebate);
  const [synthesisDraft, setSynthesisDraft] = useState<SynthesisDraft | null>(() =>
    activeSynthesisDraft(initialDebate)
  );
  const [error, setError] = useState<string | null>(initialError);
  const [streamState, setStreamState] = useState<StreamState>({ status: "connecting" });
  const [actionToken, setActionToken] = useState<string | null>(null);
  const [tokenDraft, setTokenDraft] = useState("");
  const [tokenBusy, setTokenBusy] = useState(false);
  const [fullTreeOpen, setFullTreeOpen] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(() =>
    initialDebate?.tree ? initialFocusedNodeId(initialDebate.tree) : null
  );

  const refresh = useCallback(async () => {
    try {
      const latest = await getDebate(id);
      setDebate(latest);
      const draft = activeSynthesisDraft(latest);
      if (draft) {
        setSynthesisDraft(draft);
      } else if (latest.synthesis) {
        setSynthesisDraft(null);
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load debate");
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    setSelectedNodeId((current) => (debate?.tree ? nearestExistingNodeId(debate.tree, current) : null));
  }, [debate?.tree]);

  useEffect(() => {
    let active = true;
    async function validateStoredToken() {
      const stored = getStoredToken();
      if (!stored) return;
      try {
        await validateUserToken(stored);
        if (active) setActionToken(stored);
      } catch {
        clearStoredToken();
        if (active) setActionToken(null);
      }
    }
    validateStoredToken();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let events: EventSource | null = null;
    let timer: number | null = null;
    let stopped = false;
    let attempt = 0;

    function scheduleReconnect() {
      if (stopped || timer) return;
      const delay = Math.min(30000, 1000 * 2 ** attempt);
      attempt += 1;
      setStreamState({ status: "reconnecting", retryInMs: delay });
      timer = window.setTimeout(connect, delay);
    }

    function connect() {
      timer = null;
      events?.close();
      setStreamState({ status: "connecting" });
      events = new EventSource(`${API_BASE}/api/debates/${id}/events`);
      events.onopen = () => {
        attempt = 0;
        setStreamState({ status: "live" });
        refresh();
      };
      events.addEventListener("tree_ready", () => refresh());
      events.addEventListener("node_started", (event) => {
        const payload = parseEventData(event);
        const nodeId = payloadString(payload, "node_id");
        const modelId = payloadString(payload, "model_id");
        const workerId = payloadString(payload, "worker_id");
        const role = payloadString(payload, "role");
        setDebate((current) =>
          current?.tree && nodeId
            ? {
                ...current,
                tree: beginNodeStream(current.tree, {
                  node_id: nodeId,
                  model_id: modelId,
                  worker_id: workerId,
                  role
                })
              }
            : current
        );
      });
      events.addEventListener("node_token", (event) => {
        const payload = parseEventData(event);
        const nodeId = payloadString(payload, "node_id");
        const delta = payloadString(payload, "delta");
        setDebate((current) =>
          current?.tree && nodeId && delta ? { ...current, tree: appendToken(current.tree, nodeId, delta) } : current
        );
      });
      events.addEventListener("node_complete", () => refresh());
      events.addEventListener("node_failed", (event) => {
        const payload = parseEventData(event);
        setError(payloadString(payload, "reason") || "Node generation failed");
      });
      events.addEventListener("synthesis_started", (event) => {
        const payload = parseEventData(event);
        setSynthesisDraft({
          model_id: payloadString(payload, "model_id"),
          worker_id: payloadString(payload, "worker_id"),
          raw: ""
        });
      });
      events.addEventListener("synthesis_token", (event) => {
        const payload = parseEventData(event);
        const delta = payloadString(payload, "delta") || "";
        setSynthesisDraft((current) => ({
          model_id: current?.model_id,
          worker_id: current?.worker_id,
          raw: `${current?.raw || ""}${delta}`
        }));
      });
      events.addEventListener("synthesis_complete", () => {
        setSynthesisDraft(null);
        refresh();
      });
      events.addEventListener("debate_complete", () => {
        setSynthesisDraft(null);
        refresh();
      });
      events.addEventListener("error", (event) => {
        const payload = parseEventData(event);
        if (payload) setError(payloadString(payload, "message") || "Debate stream error");
      });
      events.onerror = () => {
        events?.close();
        refresh();
        scheduleReconnect();
      };
    }

    connect();
    return () => {
      stopped = true;
      events?.close();
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [id, refresh]);

  const exportUrl = useMemo(() => `${API_BASE}/api/debates/${id}/export.md`, [id]);
  const selectedPath = useMemo(
    () => (debate?.tree && selectedNodeId ? findNodePathById(debate.tree, selectedNodeId) : []),
    [debate?.tree, selectedNodeId]
  );
  const selectedNode = useMemo(
    () => (debate?.tree && selectedNodeId ? findNodeById(debate.tree, selectedNodeId) : null),
    [debate?.tree, selectedNodeId]
  );
  const strongestPro =
    debate?.synthesis?.strongest_pro || partialJsonField(synthesisDraft?.raw || "", "strongest_pro") || "Pending";
  const strongestCon =
    debate?.synthesis?.strongest_con || partialJsonField(synthesisDraft?.raw || "", "strongest_con") || "Pending";
  const verdict = debate?.synthesis?.verdict || partialJsonField(synthesisDraft?.raw || "", "verdict") || "Pending";
  const synthesisStreaming = Boolean(synthesisDraft && !debate?.synthesis);
  const singleShotResult = isSingleShotResult(debate?.config?.single_shot_result)
    ? debate.config.single_shot_result
    : null;
  const singleShotCreatedAt = singleShotResult ? new Date(singleShotResult.created_at) : null;
  const singleShotCreatedLabel =
    singleShotCreatedAt && !Number.isNaN(singleShotCreatedAt.getTime())
      ? singleShotCreatedAt.toLocaleString()
      : singleShotResult?.created_at;
  const streamLabel =
    streamState.status === "live"
      ? "Live stream connected"
      : streamState.status === "reconnecting"
        ? `Reconnecting in ${Math.ceil((streamState.retryInMs || 0) / 1000)}s`
        : "Connecting stream";

  async function unlockActions(event: FormEvent) {
    event.preventDefault();
    const value = tokenDraft.trim();
    if (!value) return;
    setTokenBusy(true);
    setError(null);
    try {
      await validateUserToken(value);
      setStoredToken(value);
      setActionToken(value);
      setTokenDraft("");
    } catch {
      clearStoredToken();
      setActionToken(null);
      setError("Token was rejected by the coordinator.");
    } finally {
      setTokenBusy(false);
    }
  }

  function lockActions() {
    clearStoredToken();
    setActionToken(null);
    setTokenDraft("");
  }

  function rejectActionToken() {
    clearStoredToken();
    setActionToken(null);
  }

  if (error && !debate) {
    return (
      <main className="page">
        <div className="error">{error}</div>
      </main>
    );
  }
  if (!debate) {
    return (
      <main className="page">
        <p className="muted">Loading...</p>
      </main>
    );
  }

  return (
    <main className="page">
      <div className="pageHeader">
        <div>
          <h1>{debate.topic}</h1>
          <div className="toolbar">
            <span className="statusPill">{debate.status}</span>
            <span className="statusPill">{debate.node_count} nodes</span>
            <span className={`statusPill ${streamState.status === "live" ? "statusOnline" : "statusDegraded"}`}>
              {streamLabel}
            </span>
            {debate.models.map((model) => (
              <span key={model} className="badge">
                {model}
              </span>
            ))}
          </div>
        </div>
        <a className="secondaryButton" href={exportUrl}>
          Export Markdown
        </a>
      </div>
      <div className="actionAuthBar">
        {actionToken ? (
          <button className="secondary" type="button" onClick={lockActions}>
            Lock Actions
          </button>
        ) : (
          <form className="inlineAuthForm" onSubmit={unlockActions}>
            <label className="srOnly" htmlFor="debate-action-token">
              User token
            </label>
            <input
              id="debate-action-token"
              value={tokenDraft}
              onChange={(event) => setTokenDraft(event.target.value)}
              type="password"
              autoComplete="off"
              placeholder="User token"
            />
            <button className="secondary" type="submit" disabled={tokenBusy}>
              {tokenBusy ? "Checking..." : "Unlock Actions"}
            </button>
          </form>
        )}
      </div>
      {error ? <div className="error">{error}</div> : null}
      {singleShotResult ? (
        <div className="singleShotPanel" aria-label="Single-shot result">
          <section className="singleShotFinal">
            <div className="singleShotHeader">
              <h2>Single-Shot Result</h2>
              <span className="statusPill">Winner: {singleShotResult.global_winner.side}</span>
            </div>
            <p>{singleShotResult.final_text}</p>
            <p className="muted">{singleShotResult.global_winner.reason}</p>
            <div className="singleShotStrongest">
              <div>
                <h3>Strongest Pro</h3>
                <blockquote>{singleShotResult.strongest_pro}</blockquote>
              </div>
              <div>
                <h3>Strongest Con</h3>
                <blockquote>{singleShotResult.strongest_con}</blockquote>
              </div>
            </div>
            <div className="singleShotMeta" aria-label="Single-shot metadata">
              <span>{singleShotResult.model_id}</span>
              <span>{singleShotResult.tokens_in} tokens in</span>
              <span>{singleShotResult.tokens_out} tokens out</span>
              <span>{singleShotCreatedLabel}</span>
            </div>
          </section>
          <section>
            <h2>Pros ({singleShotResult.pros.length})</h2>
            <ul className="singleShotList">
              {singleShotResult.pros.map((argument, index) => (
                <li key={`${index}-${argument}`}>{argument}</li>
              ))}
            </ul>
          </section>
          <section>
            <h2>Cons ({singleShotResult.cons.length})</h2>
            <ul className="singleShotList">
              {singleShotResult.cons.map((argument, index) => (
                <li key={`${index}-${argument}`}>{argument}</li>
              ))}
            </ul>
          </section>
        </div>
      ) : null}
      {debate.analyzer_runs.length ||
      debate.selected_skills.length ||
      debate.selected_agents.length ||
      debate.agent_runs.length ? (
        <div className="singleShotPanel" aria-label="Dialectical workspace artifacts">
          <section>
            <h2>Analyzers</h2>
            <div className="artifactGrid">
              {debate.analyzer_runs.map((run) => (
                <article key={run.id} className="artifactItem">
                  <div className="artifactHeader">
                    <h3>{run.analyzer_type}</h3>
                    <span className="statusPill">{run.status}</span>
                  </div>
                  <p>{run.output.findings?.[0] || "No finding recorded."}</p>
                  <p className="muted">{provenanceLabel(run.provenance)}</p>
                </article>
              ))}
            </div>
          </section>
          <section>
            <h2>Agent Breakdown</h2>
            {debate.agent_runs.map((run) => (
              <article key={run.id} className="artifactItem agentOutputPanel">
                <div className="artifactHeader">
                  <h3>{run.agent_name || run.role || run.id}</h3>
                  <span className="statusPill">{run.status}</span>
                </div>
                <p>{run.summary || run.agent.description || "No summary recorded."}</p>
                {run.skills_used.length ? (
                  <p className="muted">
                    Skills: {run.skills_used.map((skill) => skill.name || skill.id).join(", ")}
                  </p>
                ) : null}
                <div className="argumentColumns">
                  <div>
                    <h4>Pros ({run.pros.length})</h4>
                    <ol>
                      {run.pros.map((argument) => (
                        <li key={argument}>{argument}</li>
                      ))}
                    </ol>
                  </div>
                  <div>
                    <h4>Cons ({run.cons.length})</h4>
                    <ol>
                      {run.cons.map((argument) => (
                        <li key={argument}>{argument}</li>
                      ))}
                    </ol>
                  </div>
                </div>
                <p className="muted">{provenanceLabel(run.provenance)}</p>
              </article>
            ))}
          </section>
        </div>
      ) : null}
      {debate.tree && selectedNode && selectedPath.length > 0 ? (
        <ArgumentFocusView
          rootNode={debate.tree}
          selectedNode={selectedNode}
          selectedPath={selectedPath}
          token={actionToken}
          onQueued={refresh}
          onError={setError}
          onAuthRejected={rejectActionToken}
          onSelectNode={setSelectedNodeId}
        />
      ) : null}
      {debate.tree ? (
        <section className="fullTreePanel" aria-label="Full recursive debate tree">
          <button
            className="secondary fullTreeToggle"
            type="button"
            aria-expanded={fullTreeOpen}
            onClick={() => setFullTreeOpen((current) => !current)}
          >
            {fullTreeOpen ? "Hide full tree" : "Show full tree"}
          </button>
          {fullTreeOpen ? (
            <div className="treeViewport treeViewportSubordinate">
              <DebateTree
                node={debate.tree}
                token={actionToken}
                onQueued={refresh}
                onError={setError}
                onAuthRejected={rejectActionToken}
                onSelectNode={setSelectedNodeId}
                selectedNodeId={selectedNodeId}
              />
            </div>
          ) : null}
        </section>
      ) : null}
      <div className="synthesisPanel">
        <section className="synthesisVerdict">
          <h2>Verdict</h2>
          <p className={synthesisStreaming ? "cursor" : undefined}>{verdict}</p>
          {synthesisDraft?.model_id ? (
            <div className="synthesisMeta">
              {synthesisDraft.model_id}
              {synthesisDraft.worker_id ? ` - ${synthesisDraft.worker_id}` : ""}
            </div>
          ) : null}
        </section>
        <section className="synthesisSupport synthesisSupportPro">
          <h2>Strongest Pro</h2>
          <p className={synthesisStreaming ? "cursor" : undefined}>{strongestPro}</p>
        </section>
        <section className="synthesisSupport synthesisSupportCon">
          <h2>Strongest Con</h2>
          <p className={synthesisStreaming ? "cursor" : undefined}>{strongestCon}</p>
        </section>
      </div>
    </main>
  );
}
