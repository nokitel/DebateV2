# Subscription Loop Workers Design

## Goal

Run Claude and Gemini subscription-backed workers as persistent tmux sessions for `dezbatere.ro`, with coordinator routing that assigns jobs specifically to those loops.

## Architecture

The coordinator remains the source of truth for job assignment. Claude and Gemini loops register as normal workers with dedicated model IDs:

- `claude-sonnet-4-6-max-loop`
- `gemini-2.5-flash-google-loop`

Claude and Gemini run in `tmux` loops that wake every 60 seconds, claim one assigned job, generate the answer through the logged-in local CLI, and post completion through the helper. A Claude Code `/loop` instruction and project skill are also checked in for interactive Claude-loop operation, but production defaults to the reliable one-shot CLI loop. Gemini defaults to `gemini-2.5-flash` because the local subscription CLI accepted that model and rejected `gemini-3.5-flash`; the advertised loop model and CLI model remain configurable for a future 3.5 cutover.

## Data Flow

1. The loop helper registers a worker and persists its worker token in a provider-specific worker config.
2. The loop polls `/api/workers/{worker_id}/poll`.
3. The coordinator only returns jobs whose `required_model` matches the loop worker capability.
4. The model output is streamed to `/api/jobs/{job_id}/stream`.
5. The parsed result is posted to `/api/jobs/{job_id}/complete`.
6. Existing orchestrator logic continues the debate tree and publishes UI events.

## Routing

Production routing replaces raw subscription CLI model IDs with the loop IDs. Mock models stay out of `enabled_models` for production. Existing local or API-backed models such as Codex and LM Studio remain available.

## Failure Handling

The helper can mark a claimed job failed with a retryable reason. If a tmux loop stops, the worker becomes stale under existing worker status handling and jobs can be retried when the loop is back.

## Verification

Automated tests cover route replacement, prompt framing, result parsing, Gemini command construction, and Make target exposure. Runtime verification requires starting the tmux loops, checking worker status on `dezbatere.ro`, and creating or regenerating a debate node that uses the loop capabilities.
