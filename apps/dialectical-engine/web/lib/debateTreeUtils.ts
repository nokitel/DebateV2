import type { DebateNode } from "./types";

export function findNodeById(tree: DebateNode, id: string): DebateNode | null {
  if (tree.id === id) {
    return tree;
  }

  for (const child of tree.children) {
    const match = findNodeById(child, id);
    if (match !== null) {
      return match;
    }
  }

  return null;
}

export function findNodePathById(tree: DebateNode, id: string): DebateNode[] {
  if (tree.id === id) {
    return [tree];
  }

  for (const child of tree.children) {
    const childPath = findNodePathById(child, id);
    if (childPath.length > 0) {
      return [tree, ...childPath];
    }
  }

  return [];
}

export function partitionArgumentChildren(node: DebateNode): {
  proChildren: DebateNode[];
  conChildren: DebateNode[];
} {
  const proChildren: DebateNode[] = [];
  const conChildren: DebateNode[] = [];

  for (const child of node.children) {
    if (child.node_type === "PRO") {
      proChildren.push(child);
    } else if (child.node_type === "CON") {
      conChildren.push(child);
    }
  }

  return { proChildren, conChildren };
}

export function perspectiveChildren(node: DebateNode): DebateNode[] {
  return node.children.filter(
    (child) =>
      child.node_type === "SCIENTIFIC_POV" ||
      child.node_type === "STATISTICAL_POV" ||
      child.node_type === "ETHICAL_POV" ||
      child.node_type === "PRACTICAL_POV",
  );
}

export function initialFocusedNodeId(tree: DebateNode): string {
  return tree.id;
}

export function nearestExistingNodeId(
  tree: DebateNode,
  selectedId: string | null | undefined,
): string {
  if (selectedId !== null && selectedId !== undefined && findNodeById(tree, selectedId) !== null) {
    return selectedId;
  }

  return initialFocusedNodeId(tree);
}
