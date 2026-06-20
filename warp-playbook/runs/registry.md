# Warp Run Registry

Append-only log of Warp `oz` agents dispatched by the orchestrator. Source of truth across turns.
Reconcile against `ozj run list` on `/warp` startup.

| Dispatched (local time) | Run ID | Conversation ID | Label | Mode | Model | Status | Notes |
|---|---|---|---|---|---|---|---|
<!-- newest first; e.g.: -->
<!-- | 2026-06-19 14:30 | run_abc123 | conv_xyz | smoke-test | cloud | auto | done | print cwd | -->
