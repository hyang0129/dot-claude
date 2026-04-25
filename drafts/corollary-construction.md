# Proposal — Improving Corollary Construction in `/refine-constitution`

> Draft. Targets [Phase 6 of setup-prompt.md](../commands/refine-constitution/setup-prompt.md#L452), [Step 6 of constitution-guide.md](../guides/constitution-guide.md#L326), and the [Corollaries section of constitution-template.md](../commands/refine-constitution/constitution-template.md#L60).

---

## The failure we are fixing

Previous setup runs produced "corollaries" that were single-law restatements — paraphrases of one law's stance, dressed up as derived consequences. Examples of the failure mode:

- *Law 1: never mislead the consumer about certainty.* → "Corollary: error messages must include the certainty level." That is just Law 1 applied to a surface. It is not a corollary.
- *Law 4: graph update under 1 minute.* → "Corollary: avoid expensive analyses in the hot path." That is just Law 4 in different words.

These pass the "is it true?" check and fail the "did anything new emerge?" check. The Corollaries section becomes a redundancy magnet — and once it is full of redundancies, future readers stop reading it, which destroys the one job the section has (catching mistakes that no single law catches).

The current Phase 6 prompt is too permissive:

> *What must be true for these laws to hold, even if it doesn't follow from any single law? What consequences emerge when the laws interact that are worth stating explicitly?*

The "even if it doesn't follow from any single law" clause is buried mid-sentence and easy to skip. The phrasing also accepts "what must be true" answers, which invites paraphrase. We need a tighter definition and a hard gate.

---

## New definition

A corollary is a **non-obvious decision** that:

1. **Derives from two or more laws acting together.** If a single law is sufficient to motivate it, it is not a corollary — it is the law correctly interpreted, and belongs in the law's anti-pattern or rejected-alternative section.
2. **Takes a stance.** A valid anti-corollary must exist — a coherent person could prefer the opposite resolution of the same law-vs-law tension and argue for it on the constitution's own terms.
3. **Resolves a tension between the cited laws.** The two laws pull in different directions on some concrete decision; the corollary names which side wins for that decision and why.

This makes a corollary structurally identical to a mini constitutional ruling: *given these two principles, in this class of situation, here is the call we make and what we give up to make it.*

### Worked example (the user's)

- **Law 1** — Never mislead the consumer; every edge and every query answer declares its own certainty and completeness.
- **Law 4** — Graph update must not exceed 1 minute for standard PRs.

**Corollary 1+4.1** — When the schema changes, we rebuild the graph from scratch rather than migrate. Migration code is a long-lived source of "looks consistent but isn't" bugs, and rebuild cost is bounded by the corpus, not the schema delta.

**Anti-corollary** — Migrate, because rebuilding will eventually breach the 1-minute budget at corpus scale. We accept the migration code complexity (and the certified-correct migration tests required to keep Law 1) in exchange for staying inside the Law 4 budget.

Both readings are coherent. The corollary picks the Law 1 side, *and* names the cost it accepts (slower at large corpora) so a future agent knows when the call should be revisited.

---

## Required structural changes

### 1. Update the corollary schema in `constitution-template.md`

Replace the current one-line format:

```
**Corollary N.M** — <statement>  ← derived from Law N
```

with:

```
**Corollary N+M.K** — <statement>
- **Derived from:** Law N + Law M (+ Law … if applicable; minimum 2)
- **Tension:** <one sentence — what these laws each pull toward in this situation>
- **Stance:** <which law wins this decision and what concrete behavior follows>
- **Anti-corollary:** <the coherent opposite call, framed positively, naming what it would gain and what it would cost>
```

The anti-corollary field is the key forcing function. It cannot be written if the corollary is a single-law restatement (there is no tension, so no opposite call exists). It cannot be written as a strawman either — it must be argued on the constitution's own terms.

Numbering changes from `N.M` (derived from one law) to `N+M.K` (derived from a pair, K-th corollary of that pair) to make the multi-law derivation visible at a glance.

### 2. Replace Phase 6 of `setup-prompt.md` with a script + subagent flow

Current Phase 6 is one short prompt run inline by ROOT. The user-facing "what must be true" question puts the agent in the hot seat to both *generate* candidates and *judge* them, which is exactly the failure pattern we see in challenger work too — that's why challengers were extracted into adversarial subagents in the first place. Apply the same pattern here, but split out the parts that aren't judgment.

Phase 6 becomes a four-stage flow:

1. **Script** — enumerate law pairs. Pure list-of-tuples; no LLM.
2. **Pair Judge subagents (parallel, one per pair)** — each judges only its assigned pair: is there a concrete contested decision?
3. **Advocate subagents (parallel, one per surviving candidate)** — stress-tests by writing the strongest anti-corollary, or proves none exists.
4. **ROOT walks survivors with the user** — accept/revise/reject, final admission gate.

The single-Cartographer design (which I originally proposed) bundled enumeration with judgment. Splitting them is strictly better: the enumeration is deterministic, and one-judge-per-pair removes the cross-pair anchoring bias a single agent walking all 45 pairs would suffer ("pair 7 is like pair 3, both DISCARD").

#### Phase 6a — Enumerate pairs (script, no LLM)

Deterministically produce all `N choose 2` pairs of admitted laws. For 5 laws → 10 pairs; for 10 laws (the cap) → 45 pairs. Output is just `[(Law1, Law2), (Law1, Law3), …]` plus the law texts themselves so the next phase can dispatch.

This step needs no model. A `Bash` one-liner or a tiny Python snippet does it. ROOT runs it and uses the output to fan out the next phase.

If law count and pair count exceed a threshold (say, >20 pairs), ROOT can ask the user whether to run the full matrix or restrict to user-nominated pairs ("you mentioned Law 1 and Law 4 conflict on schema changes — should I just walk that pair, or run the full matrix?"). Default: full matrix; the cost is parallel and bounded.

#### Phase 6b — Spawn Pair Judge subagents in parallel

For each pair from 6a, spawn one Pair Judge subagent **in parallel from a single ROOT turn**. Each Judge sees only its own pair plus the thesis and research findings — it does not see other pairs' verdicts, which prevents anchoring ("pair 3 was DISCARDED, this looks similar, also DISCARD").

Each Judge receives: the thesis, exactly two laws in full (Law N and Law M), and the research findings. Returns one of:

- **CANDIDATE** — fills in `Derived from / Tension / Stance`. The pair has a concrete contested decision class.
- **DISCARDED** — one-line reason ("no decision class found", "fully covered by Law N's anti-pattern", "redundant with rejected-alternatives").

ROOT collects all verdicts and forwards CANDIDATE pairs to Phase 6c.

See sketch below at [Pair Judge subagent prompt](#pair-judge-subagent-prompt-sketch).

#### Phase 6c — Spawn Anti-corollary Advocates in parallel

For each CANDIDATE from 6b, spawn one Advocate subagent **in parallel from a single ROOT turn** (mirrors the parallel-spawn rule from `challenger-prompts.md` — prevents the Advocates from anchoring on each other and bounds the round-trips).

Each Advocate receives: the thesis, the two laws (full text), and the Judge's `Tension` and `Stance`. It must mount the strongest possible case *for the opposite stance*, on the constitution's own terms, citing the cost of the proposed Stance and what is gained by reversing it.

Each Advocate returns either:
- **CONTESTED** — a coherent anti-corollary, written positively (what the opposite call would gain, what cost it would accept). The candidate survives the gate.
- **NOT CONTESTED** — explicit statement that no coherent opposite exists on the constitution's terms. The candidate fails the gate and is dropped — it was a single-law restatement masquerading as a corollary.

See sketch below at [Advocate subagent prompt](#advocate-subagent-prompt-sketch).

#### Phase 6d — ROOT walks survivors with the user

ROOT presents each surviving candidate to the user with all four fields populated (`Derived from`, `Tension`, `Stance`, `Anti-corollary`). For each, the user does one of:

- **Accept** — write to `CONSTITUTION.md`.
- **Revise** — edit any field. Stance and Anti-corollary edits must keep the gate (still contested, still multi-law).
- **Reject** — drop. ROOT records the reason in the WIP file for the audit trail.

Before writing each accepted corollary, ROOT applies the admission gate as a final check:

- [ ] **Multi-law derivation:** ≥2 laws cited in `Derived from`. If only one, reject — fold the content into that law's anti-pattern or rejected-alternative.
- [ ] **Concrete decision class:** `Tension` names a specific situation, not "in general".
- [ ] **Stance is contested:** the Advocate produced a CONTESTED verdict with a non-strawman anti-corollary.
- [ ] **Net-new content:** not equivalent to anything already in either source law's anti-pattern or rejected-alternative section.

Any corollary failing the gate is dropped, not patched. The Corollaries section is allowed to be empty. An empty section beats a section full of paraphrases.

---

### Pair Judge subagent prompt sketch

```
You are a Corollary Pair Judge for /refine-constitution. You judge ONE pair of
laws: is there a concrete contested decision class where these two laws pull in
different directions?

You receive: the thesis, exactly two laws (Law N and Law M, full text), and
the research findings. You do NOT see other pairs' verdicts — your judgment
must be independent.

Try to identify ONE concrete decision class where the two laws pull toward
different answers. "Concrete" means: a class of decision a contributor will
actually face during a PR — schema migration vs. rebuild, sync vs. async,
eager vs. lazy, fail-loud vs. degrade, etc. Not "in principle these could
conflict."

Return one of:
  (a) CANDIDATE — fill in:
        Derived from: Law N + Law M
        Tension: <one sentence, names the decision class concretely>
        Stance: <which law wins this decision and the concrete behavior that
                 follows; one or two sentences>
  (b) DISCARDED — <one-line reason: "no decision class found", "fully covered
       by Law N's anti-pattern", "redundant with rejected-alternatives", etc.>

Do not draft an anti-corollary. The Advocate subagent handles that — your
job is to find the tension, not to stress-test it.

Failure modes to avoid:
- Single-law candidates (a "tension" that only invokes one law is that law
  being applied — DISCARD with that reason).
- Abstract tensions ("performance vs correctness" without naming the actual
  decision a PR author would face — DISCARD).
- Inventing decision classes the codebase doesn't actually surface — ground
  in the thesis and the research findings.
- Returning CANDIDATE because you feel obligated to. DISCARDED is the right
  answer for most pairs. A constitution where every pair has a tension is
  almost certainly one where the laws are not orthogonal enough.
```

### Advocate subagent prompt sketch

```
You are an Anti-corollary Advocate. Your job is to mount the strongest possible
case for the OPPOSITE of the proposed corollary stance, on the constitution's
own terms.

You receive: the thesis, two laws in full (Law N and Law M), and a candidate
Tension + Stance from the Cartographer. You do NOT receive any draft anti-
corollary — your job is to write one, or prove no coherent one exists.

The proposed Stance picks a side of the tension. Your job is to argue the
other side could also be picked by a coherent author who reads the same two
laws. The opposite call must:
  - Be argued on the constitution's terms (cite which law it is privileging).
  - Name what it gains (what failure mode it avoids that the proposed Stance
    accepts).
  - Name what it costs (what failure mode it accepts that the proposed Stance
    avoids).

Produce one of:
  (a) CONTESTED — write the anti-corollary as one paragraph in the form:
        "<Opposite call>, because Law M's <specific failure> is the heavier
         cost. We accept <named cost on Law N's side> in exchange."
  (b) NOT CONTESTED — state plainly that no coherent opposite exists. The
      proposed Stance is the only call a constitution-respecting author could
      make. This means the "tension" was illusory — both laws actually point
      the same way for this decision class, and what the Cartographer surfaced
      is just one of the laws being correctly applied.

Failure modes to avoid:
- Strawman anti-corollaries ("the opposite is: ignore Law N" — that's not an
  anti-corollary, that's law violation).
- Inventing constraints not present in the laws to make the opposite work.
- Hedging ("could go either way") — pick CONTESTED or NOT CONTESTED.

If you must reach outside the cited laws to motivate the opposite call,
return NOT CONTESTED and say so — that signals the corollary should live as
a clarification under one of the laws, not as a multi-law derivation.
```

### 3. Update the bluffing-detection list in `constitution-guide.md`

Add a new anti-pattern section after [Anti-patterns in constitutions](../guides/constitution-guide.md#L190):

> **Single-law corollaries.** A "corollary" that derives from one law is a paraphrase. Symptoms: the `Derived from` line cites one law; the anti-corollary is a strawman ("the opposite is: don't do Law N"); removing the corollary loses no information. Cure: delete it, or move its substance into the law's anti-pattern section if the original law was missing a concrete violation example.

Also amend [Step 6 of constitution-guide.md](../guides/constitution-guide.md#L326) to point at the new gate instead of the current "ask what must be true" prompt.

### 4. Update amendment-prompt.md cleanup rules

The amendment subskill already prunes corollaries when laws are retired or demoted ([amendment-prompt.md:159–199](../commands/refine-constitution/amendment-prompt.md#L159)). Extend the rule:

- When a law is retired, drop every corollary that cites it (current behavior — keep).
- When a law is added or its stance materially changes, re-run Phase 6a/6b for every new law-pair the change creates. Many existing corollaries will be unaffected; some will need re-justification because the tension shifted.

---

## Why this works

The current process fails because "what must be true for the laws to hold" is a question that always has answers, and most of those answers are paraphrases of individual laws. The new process fails-closed: if there is no concrete contested decision, there is no corollary. That is the right default — an empty Corollaries section is the honest output for a constitution whose laws don't pull against each other in practice.

The anti-corollary requirement is doing the heaviest lifting. It is to corollaries what "rejected alternative" is to laws: the structural element that proves the author actually weighed something, rather than wrote down what they already wanted to do. A constitution element without a coherent opposing position is not a decision — it's a description.

---

## Open questions

1. **Pair Judge fan-out ceiling.** For 10 laws, `N choose 2` = 45 parallel Judges. They are cheap and bounded (single round-trip), but 45 subagents in one turn is a lot. Options: (a) fan out all 45 unconditionally; (b) cap at e.g. 20 and ask the user to nominate which pairs to walk if over the cap; (c) batch — one Judge handles 3-5 pairs each, trading some anchoring risk for fewer agents. Lean (a) for now — fan-out is cheap and the cap is rarely hit (most constitutions live at 4-6 laws).
2. **Triples.** Should we also walk `N choose 3`? Argument for: rare but valuable when a single decision genuinely involves three laws. Argument against: combinatorial blow-up (10 laws → 120 triples) and triples usually decompose into pairs. Probably skip for v1.
3. **One Advocate per candidate vs. multiple.** Following the Challenger pattern strictly would mean ≥2 Advocates per candidate (different angles). For corollaries this is probably overkill — the Advocate's job is binary (contested or not), not multi-dimensional like Challengers (necessity/scope/rejected-alt). One Advocate per candidate seems right; revisit if the gate proves too leaky.
4. **Where does the gate live?** Currently the proposal puts the gate in ROOT (Phase 6d) as a final check after the Advocate verdict. Could instead let the Advocate's CONTESTED/NOT CONTESTED verdict be the gate directly. Keeping a ROOT-side gate is belt-and-braces and lets the user override; remove only if it proves redundant in practice.
5. **Corollary section count cap.** The 10-law cap exists to force prioritization. The same logic could apply here, but corollary inflation is a smaller risk than law inflation because the Advocate gate already kills most candidates.
