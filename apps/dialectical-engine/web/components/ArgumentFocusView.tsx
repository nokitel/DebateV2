"use client";

import type { DebateNode } from "@/lib/types";
import { partitionArgumentChildren, perspectiveChildren } from "@/lib/debateTreeUtils";
import { ArgumentNodeCard } from "@/components/DebateTree";

type ArgumentFocusViewProps = {
  rootNode: DebateNode;
  selectedNode: DebateNode;
  selectedPath: DebateNode[];
  token: string | null;
  onQueued: () => void;
  onError: (message: string) => void;
  onAuthRejected: () => void;
  onSelectNode: (nodeId: string) => void;
};

export function ArgumentFocusView({
  rootNode,
  selectedNode,
  selectedPath,
  token,
  onQueued,
  onError,
  onAuthRejected,
  onSelectNode,
}: ArgumentFocusViewProps) {
  const parentNode = selectedPath.length > 1 ? selectedPath[selectedPath.length - 2] : null;
  const contextNode = parentNode ?? rootNode;
  const isRootFocused = selectedNode.node_type === "ROOT_CLAIM";
  const perspectives = perspectiveChildren(selectedNode);
  const { proChildren, conChildren } = partitionArgumentChildren(selectedNode);

  function renderChildCards(children: DebateNode[], emptyText: string) {
    if (children.length === 0) {
      return <p className="argumentColumnEmpty">{emptyText}</p>;
    }

    return (
      <div className="argumentColumnList">
        {children.map((child) => (
          <ArgumentNodeCard
            key={child.id}
            node={child}
            token={token}
            onQueued={onQueued}
            onError={onError}
            onAuthRejected={onAuthRejected}
            onSelectNode={onSelectNode}
            isSelected={child.id === selectedNode.id}
            selectionLabel={`Focus child argument: ${child.claim}`}
          />
        ))}
      </div>
    );
  }

  return (
    <section className="argumentFocusView" aria-label="Focused argument">
      <header className="argumentFocusHeader">
        <div>
          <span className="argumentFocusEyebrow">Debate topic</span>
          <h2>{rootNode.claim}</h2>
        </div>
      </header>
      <nav className="argumentFocusRail" aria-label="Argument path">
        <div className="argumentPath">
          {selectedPath.map((node, index) => (
            <button
              key={node.id}
              className="argumentPathButton secondary"
              type="button"
              aria-current={node.id === selectedNode.id ? "page" : undefined}
              aria-label={`Select path argument ${index + 1}: ${node.claim}`}
              onClick={() => onSelectNode(node.id)}
            >
              <span className="argumentPathIndex">{index + 1}</span>
              <span className="argumentPathClaim">{node.claim}</span>
            </button>
          ))}
        </div>
        {parentNode ? (
          <button className="secondary" type="button" aria-label={`Move up to parent argument: ${parentNode.claim}`} onClick={() => onSelectNode(parentNode.id)}>
            Up
          </button>
        ) : null}
      </nav>
      <section
        key={`context-${contextNode.id}`}
        className="argumentContextPanel argumentFocusTransition"
        aria-label={parentNode ? "Parent argument context" : "Root claim context"}
      >
        <div className="argumentContextLabel">{parentNode ? "Parent context" : "Root context"}</div>
        <button
          className="argumentContextCard"
          type="button"
          aria-label={`Focus context argument: ${contextNode.claim}`}
          onClick={() => onSelectNode(contextNode.id)}
        >
          <span className="badge">{parentNode ? "Parent" : "Root"}</span>
          <span>{contextNode.claim}</span>
        </button>
      </section>
      <div key={`focus-${selectedNode.id}`} className="argumentFocusCard argumentFocusTransition">
        <ArgumentNodeCard
          node={selectedNode}
          token={token}
          onQueued={onQueued}
          onError={onError}
          onAuthRejected={onAuthRejected}
          onSelectNode={onSelectNode}
          isSelected
          selectionLabel={`Selected argument: ${selectedNode.claim}`}
        />
      </div>
      {isRootFocused ? (
        <section
          key={`perspectives-${selectedNode.id}`}
          className="argumentPerspectivesFocus argumentFocusTransition"
          aria-labelledby="focused-perspectives-heading"
        >
          <div className="argumentColumnHeading">
            <h3 id="focused-perspectives-heading">Perspectives</h3>
            <span aria-label={`${perspectives.length} ${perspectives.length === 1 ? "perspective" : "perspectives"}`}>
              {perspectives.length}
            </span>
          </div>
          {perspectives.length > 0 ? (
            <div className="argumentPerspectiveGrid">
              {perspectives.map((child) => (
                <ArgumentNodeCard
                  key={child.id}
                  node={child}
                  token={token}
                  onQueued={onQueued}
                  onError={onError}
                  onAuthRejected={onAuthRejected}
                  onSelectNode={onSelectNode}
                  selectionLabel={`Focus perspective: ${child.claim}`}
                />
              ))}
            </div>
          ) : (
            <p className="argumentColumnEmpty">No perspectives yet.</p>
          )}
        </section>
      ) : (
        <div key={`columns-${selectedNode.id}`} className="argumentColumnsFocus argumentFocusTransition" aria-label="Direct child arguments">
          <section className="argumentColumn" aria-labelledby="focused-pros-heading">
            <div className="argumentColumnHeading">
              <h3 id="focused-pros-heading">Pros</h3>
              <span aria-label={`${proChildren.length} pro ${proChildren.length === 1 ? "argument" : "arguments"}`}>
                {proChildren.length}
              </span>
            </div>
            {renderChildCards(proChildren, "No pros yet.")}
          </section>
          <section className="argumentColumn" aria-labelledby="focused-cons-heading">
            <div className="argumentColumnHeading">
              <h3 id="focused-cons-heading">Cons</h3>
              <span aria-label={`${conChildren.length} con ${conChildren.length === 1 ? "argument" : "arguments"}`}>
                {conChildren.length}
              </span>
            </div>
            {renderChildCards(conChildren, "No cons yet.")}
          </section>
        </div>
      )}
    </section>
  );
}
