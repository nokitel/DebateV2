# Repo Handoff TODO

Goal: preserve this local `dialectical-engine` source tree cleanly before it is
imported into a GitHub repository.

## Current Finding

- `/Users/stefannour/Documents/Debate V2/dialectical-engine` is not currently a
  git checkout.
- `/Users/stefannour/Documents/AI-Harness` is a clean checkout of
  `https://github.com/DebateAIRO/debateairo.git`.
- The remaining manual `dezbatere.ro` setup gates are tracked at
  `https://github.com/DebateAIRO/debateairo/issues/5`.
- `AI-Harness/AGENTS.md` says that checkout is the AI Harness skeleton source of
  truth, so the app should not be copied into it casually without choosing an
  explicit destination path or repository strategy.

## Create A Clean Source Snapshot

From the app directory:

```sh
make source-snapshot
```

This writes:

```text
/private/tmp/dialectical-engine-source.tgz
/private/tmp/dialectical-engine-source-snapshot.json
```

The archive excludes:

- Python virtualenvs,
- `web/node_modules`,
- Next.js build output,
- caches,
- `.DS_Store`,
- local development/runtime state.

## Import Options

Choose one:

1. Create a dedicated repository for `dialectical-engine`, then unpack the
   snapshot there and commit it.
2. Add the app under a clearly named subdirectory in `DebateAIRO/debateairo`,
   for example `apps/dialectical-engine/`, then commit that import.
3. Keep `DebateAIRO/debateairo` as the AI Harness skeleton only and publish the
   source snapshot as an artifact until the repository layout is decided.

After importing, run:

```sh
make setup-status
```

from the imported app directory before relying on that checkout.
