# Manual Setup TODO

Generated from local reports. Re-run with:

```sh
make setup-status
```

Generated at: `2026-05-28T01:13:35.497065+00:00`
Tracking issue: https://github.com/DebateAIRO/debateairo/issues/5

## Current Proof

- [x] Coordinator is reachable at `http://127.0.0.1:8000`.
- [x] Web app is reachable at `http://127.0.0.1:3000` with static assets.
- [x] At least one local worker is online.
- [x] `codex-gpt-5` is enabled on the local worker.
- [x] `lmstudio:google_gemma-4-e4b-it` is enabled and loaded.
- [x] `make local-single-machine-acceptance` passes.
- [x] Temporary Cloudflare quick tunnel currently works.

## Remaining Account/Auth Work

- [ ] Claude personal auth works. Current detail: current probe returns 401.
- [x] Gemini CLI is configured for Google-account OAuth and the worker has no `GEMINI_API_KEY`.
- [ ] Gemini Google-account auth works. Current detail: waiting for Google OAuth.

Commands after completing Claude/Gemini login:

```sh
make interactive-manual-setup
make probe-model-auth
make refresh-local-models
make local-status
```

## Remaining Domain/Hosting Work

- [ ] `dezbatere.ro` delegates to Cloudflare nameservers.
- [ ] `cloudflared tunnel login` has created `~/.cloudflared/cert.pem`.
- [ ] Named Cloudflare tunnel config and credentials are ready.
- [ ] Named Cloudflare tunnel launchd service is loaded.
- [ ] `https://dezbatere.ro/api/backends/status` serves the local app.
- [ ] `https://dezbatere.ro/` serves the web UI and static assets.

Current registry nameservers: `ns1.romarg.com., ns2.romarg.com., ns3.romarg.com., ns4.romarg.com.`
Hosting next action: Add dezbatere.ro to Cloudflare, run `make prepare-romarg-nameservers` with the assigned nameservers, update Romarg, then run `make wait-dezbatere-dns`.

Manual order:

1. In a normal Terminal, run `make interactive-manual-setup` if you want guided Claude/Gemini/Cloudflare login prompts.
2. Complete `Cloudfare_TODO.md` step 1 in Cloudflare and copy the assigned nameservers.
3. Run `CLOUDFLARE_NAMESERVERS="first.ns.cloudflare.com second.ns.cloudflare.com" make prepare-romarg-nameservers` with the real Cloudflare values.
4. Complete `Romarg_TODO.md` by replacing Romarg nameservers with only the validated Cloudflare nameservers.
5. Run `make wait-dezbatere-dns`.
6. Run `make hosting-status`.
7. Run `cloudflared tunnel login` if `make interactive-manual-setup` did not already complete it.
8. Run `make resume-dezbatere-hosting`.
9. After manual HTTPS verification, run `INSTALL_SERVICE=1 STOP_QUICK_TUNNEL=1 make resume-dezbatere-hosting`.

## Reference Files

- `Romarg_TODO.md`
- `Romarg_Nameservers_To_Set.md`
- `Cloudfare_TODO.md`
- `Cloudflare_TODO.md`
- `ModelAuth_TODO.md`
- `deploy/local-single-computer-dezbatere.md`
- GitHub tracking issue: https://github.com/DebateAIRO/debateairo/issues/5
