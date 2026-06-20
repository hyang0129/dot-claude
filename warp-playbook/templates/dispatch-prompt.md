# Worker prompt template

Warp `oz` workers run largely autonomously — you steer them only via `--conversation` follow-ups.
So a good dispatch prompt is **complete on its own**. Fill every section:

```
TASK: <one sentence: what to accomplish>

CONTEXT:
- repo / path / branch (and how to reach it — cloud env? self-hosted host?)
- relevant background the worker can't infer

CONSTRAINTS:
- what NOT to touch; style/tooling to follow; time or scope limits
- never commit/push/deploy unless explicitly told

STEPS (if order matters):
1. ...
2. ...

DEFINITION OF DONE:
- concrete, checkable outcome (tests pass / file exists / output format)
- what to report back and in what shape
```

Tips:
- Prefer one well-scoped task per worker; fan out multiple workers rather than one mega-prompt.
- State the expected **output format** so `run get --conversation` is easy to parse/summarize.
- For multi-step work, dispatch step 1, read the result, then continue with `run-cloud --conversation <id>`.
