import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { rmSync } from "node:fs";
import { join } from "node:path";
import test, { after } from "node:test";

const outDir = join(process.cwd(), ".tmp-debate-tree-utils-test");

function compileHelper() {
  rmSync(outDir, { recursive: true, force: true });
  const pnpmCommand = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
  const tscArgs = [
    "exec",
    "tsc",
    "lib/debateTreeUtils.ts",
    "--target",
    "ES2022",
    "--module",
    "NodeNext",
    "--moduleResolution",
    "NodeNext",
    "--rootDir",
    ".",
    "--outDir",
    outDir,
    "--skipLibCheck",
    "--strict",
  ];

  if (process.platform === "win32") {
    execFileSync("cmd.exe", ["/d", "/s", "/c", pnpmCommand, ...tscArgs], {
      cwd: process.cwd(),
      stdio: "pipe",
    });
    return;
  }

  execFileSync(pnpmCommand, tscArgs, { cwd: process.cwd(), stdio: "pipe" });
}

after(() => {
  rmSync(outDir, { recursive: true, force: true });
});

async function loadHelper() {
  compileHelper();
  const moduleUrl = pathToFileURL(join(outDir, "lib", "debateTreeUtils.js")).href;
  return import(`${moduleUrl}?cacheBust=${Date.now()}`);
}

function node(id, node_type, children = []) {
  return {
    id,
    debate_id: "debate-1",
    parent_id: null,
    node_type,
    depth: 0,
    position: 0,
    claim: id,
    status: "complete",
    materialized_path: id,
    active_generation_id: null,
    active_generation: null,
    children,
  };
}

const tree = node("root", "ROOT_CLAIM", [
  node("first-child", "SCIENTIFIC_POV", [
    node("first-pro", "PRO"),
    node("first-con", "CON"),
    node("second-pro", "PRO"),
  ]),
  node("second-child", "PRACTICAL_POV", [
    node("deep-con", "CON", [node("deep-pro", "PRO")]),
  ]),
]);

test("findNodeById returns the matching node or null", async () => {
  const { findNodeById } = await loadHelper();

  assert.equal(findNodeById(tree, "deep-pro")?.id, "deep-pro");
  assert.equal(findNodeById(tree, "missing"), null);
});

test("findNodePathById returns ancestors from root to selected node or an empty array", async () => {
  const { findNodePathById } = await loadHelper();

  assert.deepEqual(
    findNodePathById(tree, "deep-pro").map((item) => item.id),
    ["root", "second-child", "deep-con", "deep-pro"],
  );
  assert.deepEqual(findNodePathById(tree, "missing"), []);
});

test("partitionArgumentChildren returns direct PRO and CON children in original relative order", async () => {
  const { partitionArgumentChildren } = await loadHelper();

  const { proChildren, conChildren } = partitionArgumentChildren(tree.children[0]);

  assert.deepEqual(
    proChildren.map((item) => item.id),
    ["first-pro", "second-pro"],
  );
  assert.deepEqual(
    conChildren.map((item) => item.id),
    ["first-con"],
  );
});

test("perspectiveChildren returns direct perspective children in original relative order", async () => {
  const { perspectiveChildren } = await loadHelper();

  assert.deepEqual(
    perspectiveChildren(tree).map((item) => item.id),
    ["first-child", "second-child"],
  );
});

test("initialFocusedNodeId starts at the root so all perspectives remain navigable", async () => {
  const { initialFocusedNodeId } = await loadHelper();

  assert.equal(initialFocusedNodeId(tree), "root");
  assert.equal(initialFocusedNodeId(node("solo-root", "ROOT_CLAIM")), "solo-root");
});

test("nearestExistingNodeId keeps a valid selected id or falls back to initial focus", async () => {
  const { nearestExistingNodeId } = await loadHelper();

  assert.equal(nearestExistingNodeId(tree, "deep-con"), "deep-con");
  assert.equal(nearestExistingNodeId(tree, "missing"), "root");
});
