# Model Auth TODO For Local Testing

Goal: use personal subscriptions locally without adding paid API keys unless you explicitly decide to.

## Current Status

- Codex CLI works non-interactively.
- Claude Code is installed, but `claude auth status` reports `loggedIn: false`
  and the current non-interactive probe returns `401 Invalid authentication credentials`.
- Gemini CLI is installed and configured to prefer Google-account OAuth
  (`oauth-personal`), but the browser OAuth flow still needs to be completed
  once from a normal Terminal.
- The worker launchd template sets `GOOGLE_GENAI_USE_GCA=true`, so after
  Gemini OAuth succeeds, the service keeps using Google-account auth instead of
  requiring `GEMINI_API_KEY`.
- The local model probes and Gemini worker adapter also set
  `GOOGLE_GENAI_USE_GCA=true` when invoking `gemini`.
- LM Studio is working through the local HTTP server with `google_gemma-4-e4b-it`.

## Claude Code

The guided helper can start this flow:

```sh
make interactive-manual-setup
```

After the login prompts, accept the helper's local model routing refresh so the
worker can advertise any newly working Claude/Gemini model immediately.

Or run this interactively in a terminal:

```sh
claude auth status
claude auth login --claudeai
```

`--claudeai` explicitly uses your Claude subscription login. Do not use
`claude auth login --console` unless you intentionally want Anthropic Console
API billing.

Then verify:

```sh
claude -p --max-turns 1 'Reply with exactly: ok'
```

Expected output includes `ok`. If it still returns `401 Invalid authentication credentials`, run:

```sh
claude setup-token
claude -p --max-turns 1 'Reply with exactly: ok'
```

## Gemini CLI

Use only Google-account auth for this simplified phase. Do not set `GEMINI_API_KEY` unless paid API usage is intended.

This installed Gemini CLI does not expose a `gemini auth` command. Configure it
for Google-account OAuth, then run the interactive CLI once:

```sh
make configure-gemini-google-auth
gemini
```

In the interactive Gemini CLI, choose `Login with Google` if prompted, complete
the browser OAuth flow, then quit Gemini. Run this from a normal Terminal, not
from a sandboxed command runner, because the OAuth flow needs to open/listen on
a local callback port.

Then verify:

```sh
gemini -p 'Reply with exactly: ok'
```

Expected output includes `ok`. The local CLI also accepts
`GOOGLE_GENAI_USE_GCA=true` for Google-account auth, but the project helper uses
the settings file so launchd/non-interactive probes see the same auth method.

Current local status: the auth method has been set to `oauth-personal`, but the
browser OAuth flow still needs to be completed.

## Recheck

After changing auth:

```sh
make refresh-local-models
```

The interactive helper offers to run this refresh for you after the account
login prompts. If you run Claude/Gemini login manually, run the command above
afterward.

To check auth without changing runtime routing:

```sh
make probe-model-auth
```

This writes `/private/tmp/dialectical-model-auth-check.json`. `make
local-next-steps` reads that separate auth report when it exists, so a later
`make local-status` no longer erases the latest detailed Claude/Gemini probe
result.

The broader local status report also records a non-secret Gemini configuration
proof: `~/.gemini/settings.json` is set to `oauth-personal`, the worker launchd
environment contains `GOOGLE_GENAI_USE_GCA=true`, and the worker launchd
environment does not contain `GEMINI_API_KEY`.

To write a combined current-state checklist for the remaining manual work:

```sh
make setup-status
```

`make refresh-local-models` enables only the CLI models that pass a real
non-interactive probe, restarts the main worker, then runs `make local-status`.
Before Claude/Gemini login it keeps the local setup on Codex plus LM Studio;
after login it adds the newly usable CLI model.
