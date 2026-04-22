# /pr-review-cycle sessions — past 14 days

Generated: 2026-04-22T18:26:58+00:00  
Sessions found: **1**

## Summary

| # | Invoked (UTC) | Args | Sub | In | CacheW | CacheR | Out | Hit% | Cost |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-04-22 18:20:47 | (no args) | 2 | 8,315 | 577,174 | 23,408,785 | 115,751 | 98% | $38.97 |
| **TOT** | | | | 8,315 | 577,174 | 23,408,785 | 115,751 | 98% | **$38.97** |

## Per-session breakdown

### #1 — 2026-04-22 18:20:47 — (no args)

- project: `d--containers-windows-0`
- session: `d2987528-e3d0-49a2-9323-5db767e4fb5b`
- subagents: 2

| Role | Description | Model | In | CacheW | CacheR | Out | Hit% | Cost |
|---|---|---|---|---|---|---|---|---|
| ROOT | (orchestrator) | — | 5,498 | 434,649 | 21,892,880 | 113,180 | 98% | $34.37 |
| | | `opus-4-7` | 5,251 | 217,011 | 14,932,319 | 53,648 | 99% | $30.57 |
| | | `sonnet-4-6` | 247 | 217,638 | 6,960,561 | 59,532 | 97% | $3.80 |
| R-PRE | _(root sub-phase)_ | — | 5,488 | 410,620 | 20,917,091 | 109,048 | 98% | $32.14 |
| | | `opus-4-7` | 5,241 | 192,982 | 13,956,530 | 49,516 | 99% | $28.35 |
| | | `sonnet-4-6` | 247 | 217,638 | 6,960,561 | 59,532 | 97% | $3.80 |
| R-SETUP | _(root sub-phase)_ | — | 8 | 19,821 | 568,387 | 1,643 | 97% | $1.35 |
| | | `opus-4-7` | 8 | 19,821 | 568,387 | 1,643 | 97% | $1.35 |
| R-POST-REV | _(root sub-phase)_ | — | 2 | 4,208 | 407,402 | 2,489 | 99% | $0.88 |
| | | `opus-4-7` | 2 | 4,208 | 407,402 | 2,489 | 99% | $0.88 |
| REV | Cycle 1 Reviewer for PR<br>#886 | — | 2,812 | 112,697 | 1,487,757 | 917 | 93% | $4.46 |
| | | `opus-4-7` | 2,812 | 112,697 | 1,487,757 | 917 | 93% | $4.46 |
| — | Research: auto-detect<br>voice ID drift in Fish<br>Audio TTS blocks | — | 5 | 29,828 | 28,148 | 1,654 | 49% | $0.15 |
| | | `sonnet-4-6` | 5 | 29,828 | 28,148 | 1,654 | 49% | $0.15 |
| **TOTAL** | | | 8,315 | 577,174 | 23,408,785 | 115,751 | 98% | **$38.97** |

## Aggregate by model (all sessions)

| Model | In | CacheW | CacheR | Out | Hit% | Cost |
|---|---|---|---|---|---|---|
| `opus-4-7` | 8,063 | 329,708 | 16,420,076 | 54,565 | 98% | $35.03 |
| `sonnet-4-6` | 252 | 247,466 | 6,988,709 | 61,186 | 97% | $3.94 |

## Aggregate by phase and model (all sessions)

| Phase | Model | In | CacheW | CacheR | Out | Hit% | Cost |
|---|---|---|---|---|---|---|---|
| R-PRE | `opus-4-7` | 5,241 | 192,982 | 13,956,530 | 49,516 | 99% | $28.35 |
|  | `sonnet-4-6` | 247 | 217,638 | 6,960,561 | 59,532 | 97% | $3.80 |
| R-SETUP | `opus-4-7` | 8 | 19,821 | 568,387 | 1,643 | 97% | $1.35 |
| R-POST-REV | `opus-4-7` | 2 | 4,208 | 407,402 | 2,489 | 99% | $0.88 |
| REV | `opus-4-7` | 2,812 | 112,697 | 1,487,757 | 917 | 93% | $4.46 |
| OTHER | `sonnet-4-6` | 5 | 29,828 | 28,148 | 1,654 | 49% | $0.15 |

### Phase totals

| Phase | Cost | % of grand |
|---|---|---|
| R-PRE | $32.14 | 82.5% |
| REV | $4.46 | 11.4% |
| R-SETUP | $1.35 | 3.5% |
| R-POST-REV | $0.88 | 2.2% |
| OTHER | $0.15 | 0.4% |

---
Phases: REV=reviewer, FIX=fixer, INT=intent-validator, EXPL=explore  
ROOT sub-phases: R-PRE, R-SETUP, R-POST-REV (after reviewer returns, orchestrator planning),
R-POST-FIX (after fixer spawn; wait/verify/commit), R-POST-INT (after intent validator spawn).  
Hit% = cache_read / (input + cache_write + cache_read)
