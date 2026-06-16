"use client";

import type { CSSProperties, KeyboardEvent, MouseEvent } from "react";
import { useState } from "react";
import { nodeGenerations, regenerateNode } from "@/lib/api";
import type { DebateNode, Generation } from "@/lib/types";

function nodeClass(node: DebateNode): string {
  if (node.node_type === "PRO") return "nodeCard pro";
  if (node.node_type === "CON") return "nodeCard con";
  if (
    node.node_type === "SCIENTIFIC_POV" ||
    node.node_type === "STATISTICAL_POV" ||
    node.node_type === "ETHICAL_POV" ||
    node.node_type === "PRACTICAL_POV"
  )
    return "nodeCard root";
  return "nodeCard root";
}

function nodeLabel(node: DebateNode): string {
  if (node.node_type === "ROOT_CLAIM") return "Root";
  if (node.node_type === "SCIENTIFIC_POV") return "Scientific POV";
  if (node.node_type === "STATISTICAL_POV") return "Statistical POV";
  if (node.node_type === "ETHICAL_POV") return "Ethical POV";
  if (node.node_type === "PRACTICAL_POV") return "Practical POV";
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
  onSelectNode?: (nodeId: string) => void;
  selectedNodeId?: string | null;
};

type ArgumentNodeCardProps = {
  node: DebateNode;
  token: string | null;
  onQueued: () => void;
  onError: (message: string) => void;
  onAuthRejected: () => void;
  onSelectNode?: (nodeId: string) => void;
  isSelected?: boolean;
  canToggleChildren?: boolean;
  childrenOpen?: boolean;
  onToggleChildren?: () => void;
  selectionLabel?: string;
};

function errorMessage(exc: unknown, fallback: string): string {
  return exc instanceof Error ? exc.message : fallback;
}

function looksAuthRelated(message: string): boolean {
  const lower = message.toLowerCase();
  return lower.includes("401") || lower.includes("403") || lower.includes("invalid user token");
}

export function ArgumentNodeCard({
  node,
  token,
  onQueued,
  onError,
  onAuthRejected,
  onSelectNode,
  isSelected = false,
  canToggleChildren = false,
  childrenOpen,
  onToggleChildren,
  selectionLabel,
}: ArgumentNodeCardProps) {
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

  function activateCard() {
    onSelectNode?.(node.id);
  }

  function selectFromClick(event: MouseEvent<HTMLElement>) {
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest("button, a, input, textarea, select, .historyPanel")) return;
    activateCard();
  }

  function selectOrToggleFromKeyboard(event: KeyboardEvent<HTMLElement>) {
    if (!isCardInteractive) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    activateCard();
  }

  const generation = node.active_generation;
  const argument = generation?.argument || (node.status === "pending" ? "Queued" : "");
  const workerName = generation?.worker_name || generation?.worker_id;
  const activeModelColor = generation ? modelColor(generation.model_id) : undefined;
  const isCardInteractive = Boolean(onSelectNode);
  const cardLabel = selectionLabel ?? (isCardInteractive ? `Select argument: ${node.claim}` : undefined);
  const modelStyle = generation
    ? ({ "--model-color": activeModelColor, "--node-model-color": activeModelColor } as CSSProperties)
    : undefined;
  return (
    <article
      className={[nodeClass(node), canToggleChildren ? "expandable" : "", isCardInteractive ? "selectable" : "", isSelected ? "selected" : ""]
        .filter(Boolean)
        .join(" ")}
      style={modelStyle}
      data-node-type={node.node_type}
      data-model-id={generation?.model_id}
      data-worker-name={workerName}
      data-model-color={activeModelColor}
      data-children-open={canToggleChildren ? childrenOpen : undefined}
      data-selectable={isCardInteractive ? "true" : undefined}
      aria-current={isSelected ? "true" : undefined}
    >
      <div className="nodeTop">
        <div
          className="nodeSelectionSurface"
          role={isCardInteractive ? "button" : undefined}
          tabIndex={isCardInteractive ? 0 : undefined}
          aria-label={cardLabel}
          aria-current={isSelected ? "true" : undefined}
          data-selected={isSelected ? "true" : undefined}
          onClick={isCardInteractive ? selectFromClick : undefined}
          onKeyDown={isCardInteractive ? selectOrToggleFromKeyboard : undefined}
        >
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
          <div
            className={[
              node.status === "generating" || node.status === "pending" ? "argument cursor" : "argument",
              canToggleChildren ? "argumentToggle" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {argument}
          </div>
        </div>
        {token || canToggleChildren ? (
          <div className="toolbar nodeActionToolbar">
            {canToggleChildren ? (
              <button
                className="secondary"
                type="button"
                aria-expanded={childrenOpen}
                aria-label={`${childrenOpen ? "Collapse" : "Expand"} child arguments for: ${node.claim}`}
                onClick={onToggleChildren}
              >
                {childrenOpen ? "Collapse" : "Expand"}
              </button>
            ) : null}
            {token ? (
              <>
                <button
                  className="secondary"
                  type="button"
                  disabled={busyNode === node.id}
                  aria-label={`Regenerate argument: ${node.claim}`}
                  onClick={() => regenerate(node.id)}
                >
                  Regenerate
                </button>
                <button
                  className="secondary"
                  type="button"
                  aria-label={`${historyOpen ? "Hide" : "Show"} generation history for argument: ${node.claim}`}
                  aria-expanded={historyOpen}
                  onClick={toggleHistory}
                >
                  History
                </button>
              </>
            ) : null}
          </div>
        ) : null}
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
  );
}

export function DebateTree({ node, token, onQueued, onError, onAuthRejected, onSelectNode, selectedNodeId }: DebateTreeProps) {
  const [childrenOpen, setChildrenOpen] = useState(node.node_type === "ROOT_CLAIM");

  const hasChildren = node.children.length > 0;
  const canToggleChildren = hasChildren && node.node_type !== "ROOT_CLAIM";
  const childLayout = node.node_type === "ROOT_CLAIM" ? "root-povs" : "vertical";

  return (
    <div className="tree" data-node-type={node.node_type}>
      <ArgumentNodeCard
        node={node}
        token={token}
        onQueued={onQueued}
        onError={onError}
        onAuthRejected={onAuthRejected}
        onSelectNode={onSelectNode}
        isSelected={selectedNodeId === node.id}
        canToggleChildren={canToggleChildren}
        childrenOpen={childrenOpen}
        onToggleChildren={() => setChildrenOpen((current) => !current)}
      />
      {hasChildren && childrenOpen ? (
        <div
          className={["children", childLayout === "root-povs" ? "rootPovChildren" : ""].filter(Boolean).join(" ")}
          data-child-layout={childLayout}
        >
          {node.children.map((child) => (
            <DebateTree
              key={child.id}
              node={child}
              token={token}
              onQueued={onQueued}
              onError={onError}
              onAuthRejected={onAuthRejected}
              onSelectNode={onSelectNode}
              selectedNodeId={selectedNodeId}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
