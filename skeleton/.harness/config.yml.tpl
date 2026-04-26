# Harness configuration for {{PROJECT_NAME}}

verification:
  acceptance:
    # Acceptance verification is criterion-driven and merge-blocking.
    verifier: codex

  code_quality:
    # Code-quality verification is informational. Human review remains the gate.
    mode: {{CODE_QUALITY_MODE}}        # single | dual
    primary: {{CODE_QUALITY_PRIMARY}}  # codex | claude

scheduling:
  default_concurrency: 1
  fix_cycles_cap: 3
  conflict_resolution_cycles_cap: 3

memory:
  reindex_on_push: true
  prune_ritual: quarterly

observability:
  status_issue_update_interval_minutes: 15
  metrics_jsonl_dir: .harness/metrics
