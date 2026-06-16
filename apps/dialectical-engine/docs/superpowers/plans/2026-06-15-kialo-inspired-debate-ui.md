# Kialo-Inspired Debate UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a focused argument detail experience with visible path context, pro/con columns, and local-root navigation while preserving the existing argument card styling and affordances.

**Architecture:** Keep `DebatePageClient` responsible for debate fetch/stream/auth state and add only focused navigation state there. Move pure tree lookup and partitioning into `web/lib/debateTreeUtils.ts` so behavior can be tested without a browser. Keep existing card rendering in `DebateTree.tsx`, extracting just enough structure to reuse card affordances inside focused views without redesigning the card visuals.

**Tech Stack:** Next.js 15 app router, React 19 client components, TypeScript strict mode, existing global CSS, no new runtime dependencies.

---

## Refreshed PRD-Lite

**Features**
- Keep the global debate topic and stream/model status visible.
- Selecting an argument opens a focused detail area for that argument.
- Show the selected argument's ancestor path and make each ancestor navigable.
- Promote a selected child with children into the current local root for focused exploration.
- Provide explicit up/back navigation through the selected argument path.
- Organize direct children into balanced Pro and Con columns.
- Preserve current node card visual styling, badges, regenerate button, history button, child toggling affordance, model color stripe, and pending/generating text behavior.
- Add only lightweight CSS motion using opacity/transform/stable layout dimensions.

**Non-Features**
- Do not clone Kialo exactly.
- Do not redesign or restyle argument cards beyond small structural hooks required for focus/navigation.
- Do not change backend schemas, API contracts, route/query navigation, or generation logic.
- Do not add voting, commenting, or heavy animation libraries.

**Acceptance Criteria**
- Global debate topic remains visible.
- Selected argument is shown in a focused detail area.
- Selected argument path/ancestors are visible and navigable.
- Child pro/con selection can promote that child into the local root.
- Back/up navigation works through the argument path.
- Pros and cons render in two balanced columns.
- Existing regenerate/history/action-token behavior is preserved.
- Pending/generating nodes preserve layout and avoid obvious jank.
- Desktop and mobile layouts are usable and accessible.

**Definition of Done**
- `pnpm.cmd build` passes in `web`.
- Pure tree helper checks pass before and after implementation.
- Browser smoke test covers desktop and mobile widths.
- Diff contains no unrelated churn, debug leftovers, hardcoded sample trees, or card visual redesign.

## Architecture Sketch

**Files**
- Create `web/lib/debateTreeUtils.ts`: pure helpers for `findNodeById`, `findNodePathById`, `partitionArgumentChildren`, `initialFocusedNodeId`, and `nearestExistingNodeId`.
- Create `web/lib/debateTreeUtils.test.mjs`: Node test runner checks that compile the helper module to temporary JS, import it, and verify real behavior.
- Modify `web/components/DebateTree.tsx`: keep current card markup and classes, add optional `selectedNodeId`, `onSelectNode`, `showChildren`, and `selectionMode` props only if needed. Export a reusable card component if doing so avoids duplicated action/history logic.
- Create `web/components/ArgumentFocusView.tsx`: focused view layout, path, current local root, pro/con columns, and up navigation.
- Modify `web/app/debate/[id]/DebatePageClient.tsx`: hold `selectedNodeId`, derive selected path and local root with memoized helpers, render focus view above or in place of the existing tree viewport.
- Modify `web/app/globals.css`: add layout styles for the focus shell, path rail, pro/con columns, selected states, mobile stacking, and lightweight transitions. Do not alter `.nodeCard.pro`, `.nodeCard.con`, `.nodeCard.root`, badge styling, or existing card affordance styles except for necessary selected/focus hooks.

**Data Boundaries**
- Use existing `DebateDetail.tree` and `DebateNode.children`.
- Store selected node id in local React state only.
- No backend or API changes.

**Testing Strategy**
- There is no existing frontend test harness. Use Node's built-in test runner plus a temporary TypeScript compile for pure helpers.
- Use `pnpm.cmd exec tsc web/lib/debateTreeUtils.ts --target ES2022 --module NodeNext --moduleResolution NodeNext --outDir .tree-utils-test --skipLibCheck --strict` from `web`.
- Use `node --test web/lib/debateTreeUtils.test.mjs` from `web`.
- Use `pnpm.cmd build` for full type/build verification.
- Use the in-app browser for desktop and mobile smoke testing after UI changes.

## Vertical Slices and Kanban

- `done`: Slice 1: inspected existing debate UI/data model and established isolated worktree baseline.
- `done`: Slice 2: pure tree helpers and tests for path, selection, and pro/con partitioning.
- `done`: Slice 3: reusable card boundary/selection hooks without visual restyling.
- `done`: Slice 4: focused argument detail view with topic/context and path navigation.
- `done`: Slice 5: local-root navigation when selecting nested pros/cons.
- `done`: Slice 6: lightweight transitions/loading-state layout stability.
- `done`: Slice 7: responsive/mobile polish and accessibility pass.
- `done`: Slice 8: build, browser smoke checks, and acceptance validation.

## Task 1: Tree Helper Behavior

**Mini-Spec**
- `findNodeById(tree, id)` returns the matching node or `null`.
- `findNodePathById(tree, id)` returns ancestors from root to selected node or an empty array.
- `partitionArgumentChildren(node)` returns direct `PRO` and `CON` children in original relative order.
- `initialFocusedNodeId(tree)` prefers the first non-root child when present and falls back to the root id.
- `nearestExistingNodeId(tree, selectedId)` keeps a valid selected id or falls back to `initialFocusedNodeId`.

**Files**
- Create: `web/lib/debateTreeUtils.ts`
- Create: `web/lib/debateTreeUtils.test.mjs`

- [ ] **Step 1: Write the failing helper test**

Create `web/lib/debateTreeUtils.test.mjs` with a compile-and-run Node test that imports `findNodeById`, `findNodePathById`, `partitionArgumentChildren`, `initialFocusedNodeId`, and `nearestExistingNodeId`. Use a small nested debate tree with a root, two POV children, one Pro grandchild, one Con grandchild, and one nested Pro. Assert all helper behaviors above.

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test web/lib/debateTreeUtils.test.mjs` from `web`.
Expected: FAIL because `web/lib/debateTreeUtils.ts` does not exist.

- [ ] **Step 3: Implement the helpers**

Create `web/lib/debateTreeUtils.ts` with pure recursive helpers. Do not import React. Do not mutate tree nodes.

- [ ] **Step 4: Run helper test to verify it passes**

Run: `node --test web/lib/debateTreeUtils.test.mjs` from `web`.
Expected: PASS.

- [ ] **Step 5: Run build**

Run: `pnpm.cmd build` from `web`.
Expected: PASS, aside from the existing multiple-lockfile workspace-root warning.

## Task 2: Reusable Card Boundary and Selection Hooks

**Mini-Spec**
- Preserve the existing card visual classes and action/history behavior.
- Allow a card to report selection through `onSelectNode(node.id)`.
- Do not toggle children or select when clicking buttons/history controls.
- Allow parent views to render a card without recursive children.
- Mark the selected card with accessible state (`aria-current` or equivalent) and a small structural class, without changing the base pro/con/root card styling.

**Files**
- Modify: `web/components/DebateTree.tsx`
- Modify: `web/app/globals.css`

- [ ] **Step 1: Identify the check first**

There is no React test harness. The check for this ticket is `pnpm.cmd build` plus later browser smoke validation. Document this in the task notes before editing.

- [ ] **Step 2: Extract the card boundary**

Extract existing article rendering and its local busy/history state into an exported component such as `ArgumentNodeCard`. Keep the same `nodeCard`, `nodeTop`, `toolbar`, `badge`, `argument`, `historyPanel`, and action button markup.

- [ ] **Step 3: Wire selection safely**

Add optional props for `onSelectNode`, `isSelected`, and `selectionLabel`. Ensure clicks on buttons/history still do not select or toggle children by reusing the existing `closest("button, a, input, textarea, select, .historyPanel")` guard.

- [ ] **Step 4: Preserve recursive tree behavior**

Have `DebateTree` render `ArgumentNodeCard` and continue rendering children exactly as before unless a parent passes new selection props.

- [ ] **Step 5: Run build**

Run: `pnpm.cmd build` from `web`.
Expected: PASS.

## Task 3: Focused Argument Detail and Path

**Mini-Spec**
- The debate topic remains visible in the page header.
- A focused section renders the selected argument card.
- A path rail/breadcrumb shows root-to-selected claims and lets users select ancestors.
- An Up button selects the selected node's parent when one exists.
- If the tree refresh removes the selected node, selection falls back to the nearest initial node.

**Files**
- Create: `web/components/ArgumentFocusView.tsx`
- Modify: `web/app/debate/[id]/DebatePageClient.tsx`
- Modify: `web/app/globals.css`

- [ ] **Step 1: Write/extend helper tests first**

Extend `web/lib/debateTreeUtils.test.mjs` if fallback path behavior is missing for this task. Run it and verify failure before production changes if a new helper behavior is needed.

- [ ] **Step 2: Implement focused component shell**

Create `ArgumentFocusView` with props for `rootNode`, `selectedNode`, `selectedPath`, token/action callbacks, and `onSelectNode`. Use `ArgumentNodeCard` for the focused card.

- [ ] **Step 3: Wire page state**

In `DebatePageClient`, add `selectedNodeId` state, derive `selectedPath` and `selectedNode` with helper functions, and keep selection valid after stream refreshes.

- [ ] **Step 4: Add CSS layout**

Add styles for `.argumentFocusShell`, `.argumentPath`, `.argumentPathButton`, `.focusedArgument`, and responsive stacking. Do not alter base card colors or gradients.

- [ ] **Step 5: Run checks**

Run helper test if changed, then `pnpm.cmd build`.

## Task 4: Pro/Con Columns and Local-Root Navigation

**Mini-Spec**
- Direct children of the selected local root render in two columns: Pros and Cons.
- Each child card remains compact and uses current card styling.
- Selecting a child updates the selected/local-root id.
- A child with children becomes the local root because its children populate the next pro/con columns.
- Empty columns show calm empty text without shifting the whole layout.

**Files**
- Modify: `web/components/ArgumentFocusView.tsx`
- Modify: `web/app/globals.css`

- [ ] **Step 1: Confirm helper test covers partitioning**

Run: `node --test web/lib/debateTreeUtils.test.mjs`.
Expected: PASS before UI edits.

- [ ] **Step 2: Render columns**

Use `partitionArgumentChildren(selectedNode)` in `ArgumentFocusView`. Render two column sections with headings and child `ArgumentNodeCard` instances.

- [ ] **Step 3: Wire local-root selection**

Pass `onSelectNode(child.id)` from each child card. The selected child becomes the focused card and the columns update from that child.

- [ ] **Step 4: Add stable layout CSS**

Add `.argumentColumnsFocus`, `.argumentColumn`, and empty-state styles with stable gaps and mobile single-column behavior.

- [ ] **Step 5: Run build**

Run: `pnpm.cmd build`.
Expected: PASS.

## Task 5: Motion, Loading Stability, Mobile, and Accessibility

**Mini-Spec**
- Pending/generating focused cards keep stable dimensions and visible cursor behavior.
- Path and columns remain usable at desktop and mobile widths.
- Interactive path and card-selection controls have discernible labels and keyboard-accessible buttons where needed.
- Motion is light and based on opacity/transform only.

**Files**
- Modify: `web/components/ArgumentFocusView.tsx`
- Modify: `web/components/DebateTree.tsx`
- Modify: `web/app/globals.css`

- [ ] **Step 1: Identify checks first**

Checks are `pnpm.cmd build`, desktop browser smoke, and mobile browser smoke. No new production code before noting the expected manual checks.

- [ ] **Step 2: Add accessibility labels**

Ensure path controls and up navigation have clear button text or `aria-label`. Ensure selected state is exposed.

- [ ] **Step 3: Add layout stability and transition CSS**

Add `min-height`, stable column/card containers, and short `opacity`/`transform` transitions to focus sections only.

- [ ] **Step 4: Run build**

Run: `pnpm.cmd build`.
Expected: PASS.

## Task 6: Final Verification and Smoke

**Mini-Spec**
- All acceptance criteria are checked against the implemented UI.
- Browser smoke covers an actual debate page at desktop and mobile sizes when local services are available.
- Existing node action affordances are present and clickable after the redesign.

**Files**
- No production file changes unless verification finds issues.

- [ ] **Step 1: Run automated checks**

Run: `node --test web/lib/debateTreeUtils.test.mjs` from `web`.
Run: `pnpm.cmd build` from `web`.

- [ ] **Step 2: Start local app**

Run the existing dev server path for this repo. If services are already running, reuse them. If coordinator data is unavailable, use the most representative available debate route and record the limitation.

- [ ] **Step 3: Browser smoke desktop**

Use the in-app browser at desktop width. Confirm global topic, focused selected argument, path navigation, pro/con columns, card action buttons, and no obvious overlap.

- [ ] **Step 4: Browser smoke mobile**

Use the in-app browser at mobile width. Confirm path wraps, columns stack, cards remain readable, and buttons do not overlap text.

- [ ] **Step 5: Review diff**

Run `git diff --stat` and inspect touched files for unrelated churn, card visual redesign, debug leftovers, hardcoded sample data, or swallowed errors.
