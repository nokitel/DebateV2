"use client";

import type { CSSProperties } from "react";
import { useState } from "react";
import { nodeGenerations, regenerateNode } from "@/lib/api";
import type { DebateNode, Generation } from "@/lib/types";

function nodeClass(node: DebateNode): string {
  if (node.node_type === "PRO") return "nodeCard pro";
  if (node.node_type === "CON") return "nodeCard con";
  return "nodeCard root";
}

function nodeLabel(node: DebateNode): string {
  if (node.node_type === "ROOT_CLAIM") return "Root";
  return node.node_type === "PRO" ? "Pro" : "Con";
}

function modelColor(modelId: string): string {
  const palette = ["#1f6f8b", "#7a4d1d", "#6f5d9a", "#168050", "#b43c37", "#8062b5", "#2f6f5f"];
  let hash = 0;
  for (const char of modelId) hash = (hash + char.charCodeAt(0)) % palette.length;
  return palette[hash];
}

type DebateTreeProps = {
  node: DebateNode;
  token: string | null;
  onQueued: () => void;
  onError: (message: string) => void;
  onAuthRejected: () => void;
};

function errorMessage(exc: unknown, fallback: string): string {
  return exc instanceof Error ? exc.message : fallback;
}

function looksAuthRelated(message: string): boolean {
  const lower = message.toLowerCase();
  return lower.includes("401") || lower.includes("403") || lower.includes("invalid user token");
}

export function DebateTree({ node, token, onQueued, onError, onAuthRejected }: DebateTreeProps) {
  const [busyNode, setBusyNode] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<Generation[]>([]);

  async function regenerate(id: string) {
    if (!token) return;
    setBusyNode(id);
    try {
      await regenerateNode(id, token);
      onQueued();
    } catch (exc) {
      const message = errorMessage(exc, "Unable to regenerate node");
      onError(message);
      if (looksAuthRelated(message)) onAuthRejected();
    } finally {
      setBusyNode(null);
    }
  }

  async function toggleHistory() {
    if (!token) return;
    try {
      if (!historyOpen) {
        setHistory(await nodeGenerations(node.id, token));
      }
      setHistoryOpen(!historyOpen);
    } catch (exc) {
      const message = errorMessage(exc, "Unable to load generation history");
      onError(message);
      if (looksAuthRelated(message)) onAuthRejected();
    }
  }

  const generation = node.active_generation;
  const argument = generation?.argument || (node.status === "pending" ? "Queued" : "");
  const workerName = generation?.worker_name || generation?.worker_id;
  const activeModelColor = generation ? modelColor(generation.model_id) : undefined;
  const modelStyle = generation
    ? ({ "--model-color": activeModelColor, "--node-model-color": activeModelColor } as CSSProperties)
    : undefined;
  return (
    <div className="tree">
      <article
        className={nodeClass(node)}
        style={modelStyle}
        data-node-type={node.node_type}
        data-model-id={generation?.model_id}
        data-worker-name={workerName}
        data-model-color={activeModelColor}
      >
        <div className="nodeTop">
          <div>
            <div className="toolbar">
              <span className="badge">{nodeLabel(node)}</span>
              <span className="badge">{node.status}</span>
              {generation ? (
                <span className="badge modelBadge" data-model-id={generation.model_id} data-model-color={activeModelColor}>
                  {generation.model_id}
                </span>
              ) : null}
              {generation ? <span className="badge" data-worker-name={workerName}>{workerName}</span> : null}
              {generation ? <span className="badge">{generation.role}</span> : null}
            </div>
            <h3>{node.claim}</h3>
          </div>
          {token ? (
            <div className="toolbar">
              <button className="secondary" disabled={busyNode === node.id} onClick={() => regenerate(node.id)}>
                Regenerate
              </button>
              <button className="secondary" onClick={toggleHistory}>
                History
              </button>
            </div>
          ) : null}
        </div>
        <div className={node.status === "generating" || node.status === "pending" ? "argument cursor" : "argument"}>
          {argument}
        </div>
        {historyOpen ? (
          <div className="historyPanel">
            {history.length === 0 ? (
              <p className="muted">No generations yet.</p>
            ) : (
              history.map((item) => (
                <section key={item.id}>
                  <div className="toolbar">
                    <span className="badge">{item.is_active ? "Active" : "Archived"}</span>
                    <span className="badge modelBadge" style={{ "--model-color": modelColor(item.model_id) } as CSSProperties}>
                      {item.model_id}
                    </span>
                    <span className="badge">{item.worker_name || item.worker_id}</span>
                    <span className="badge">{item.role}</span>
                  </div>
                  <p>{item.argument}</p>
                </section>
              ))
            )}
          </div>
        ) : null}
      </article>
      {node.children.length ? (
        <div className="children">
          {node.children.map((child) => (
            <DebateTree
              key={child.id}
              node={child}
              token={token}
              onQueued={onQueued}
              onError={onError}
              onAuthRejected={onAuthRejected}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
