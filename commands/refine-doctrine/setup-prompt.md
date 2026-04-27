# Setup Subskill — First-Draft Doctrine Interview

## Step −1 — Model check (before anything else)

Check the model you are currently running on. You know this from your system context
(`You are powered by the model named ...`).

- If the model is **Opus** (any version): proceed normally.
- If the model is **not Opus**: stop and warn the user before proceeding:

  > **Warning: this skill is running on [model name], not Opus.**
  >
  > The setup process is a multi-phase, judgment-heavy interview. It requires sustained
  > coherence across phases, strong contestedness detection, and the ability to reject
  > vague tech assumptions and unfalsifiable sunset triggers without letting the user
  > slip past with plausible-sounding answers. Smaller models reliably admit non-observable
  > assumptions and produce triggers phrased as "when X matures" rather than concrete
  > measurable conditions.
  >
  > **Recommended:** switch to Opus before continuing (`/model` in Claude Code, or
  > select Opus in the model picker). Running setup on a non-Opus model will likely
  > produce a doctrine that looks complete but contains hollow assumptions no one will
  > check.
  >
  > Type `proceed anyway` to continue on [model name], or switch models and re-run
  > `/refine-doctrine`.

  Wait for the user's response. If they type `proceed anyway`, continue with a note
  in `DOCTRINE.wip.md` recording which model was used. Otherwise stop.

---

This subskill runs when no doctrine exists. It produces the first draft of
`DOCTRINE.md` by interviewing the author. The interview cannot be automated: a
fully-automated pass produces non-observable tech assumptions and "when X matures"
sunset triggers every time. You are forcing articulation of constraints that exist
in the author's head but have not been made falsifiable.

Doctrine is not a catch-all for "things we've decided." Doctrine is specifically
the set of rules that current technology forces on a project that anchors to a
constitutional law. Every order must pass the contestedness filter before being
admitted.

---

## Resume logic (when STATE=WIP)

If the entry point passed `STATE=WIP`, a prior session was interrupted. Read
`DOCTRINE.wip.md` and determine `Phase completed: N`.

- **Phase 0** → anchor map is saved; skip Phase 0. Load the anchor map and
  constitution law list. Resume at Phase 1.
- **Phase 1** → pressure list is saved; skip Phases 0–1. Load anchor map and
  pressure list. Resume at Phase 2.
- **Phase 2** → filtered pressure list is saved; skip Phases 0–2. Resume at Phase 3.
- **Phase 3** → post-challenger pressure list is saved; skip Phases 0–3. Resume at Phase 4.
- **Phase 4 (order N of M)** → `DOCTRINE.md` contains the orders drafted so far; read
  them and resume order drafting from order N+1. The WIP file lists remaining pressures.
- **Phase 5** → Orders are in `DOCTRINE.md`; skip to Phase 6.

When resuming, tell the user: "Resuming from Phase N. Here is what was captured so
far: [brief summary of anchor map + N pressures]. We continue from [next phase]."

Do not re-ask questions from completed phases.

---

## Phase 0 — Anchor map construction

Goal: identify which constitutional laws are currently putting technological pressure
on the project — forcing operational decisions that would not be needed if technology
were better.

You have `CONSTITUTION_LAWS` from the entry point. Present the list to the user:

```
The constitution has these laws:

  Law 1: <stance summary>
  Law 2: <stance summary>
  ...

For each law, I'll ask: does this law currently force you to make calls you wouldn't
need to make if the technology were perfect?
```

For each law, ask:

```
Law N — <stance>:
Does this law currently force you to make operational decisions that wouldn't be
necessary if the technology were better? For example: if context windows were
unlimited, or if distributed consensus were instantaneous, or if the specific tool
you use had feature X — would this law's guidance become easier to follow without
requiring a separate rule?
```

**Rules:**

- A "no" is a valid answer. Not every law generates doctrine.
- A "yes" requires a concrete example: "which calls are you being forced to make?"
- Vague yes answers ("yes, it's complicated by tech") do not qualify. Push: "Name
  the specific call you're making that you wouldn't need to make with better tech."
- Collect yes answers as candidate pressure points into `ANCHOR_MAP`:

  ```
  Law N → [list of concrete calls forced by current tech]
  ```

Carry `ANCHOR_MAP` into Phase 1.

### WIP checkpoint

Before moving to Phase 1, write `DOCTRINE.wip.md` at the repo root:

```markdown
# Doctrine WIP — Setup in Progress

## Phase completed: 0

## Anchor map
Law N: [pressure notes]
Law M: [pressure notes]

## Constitution laws
Law 1: <stance>
...
```

Tell the user: "Anchor map saved to `DOCTRINE.wip.md` — progress is now recoverable."

---

## Phase 1 — Pressure surfacing

For each entry in `ANCHOR_MAP` (laws that generated pressure), surface the concrete
decision class this pressure forces.

For each pressured law, ask:

```
Law N forces you to [concrete call you named]. What decision class is this?
That is: what rule do you currently follow in code that exists specifically because
of that limitation — a rule another team, working from the same constitution but
with different tech constraints, might not follow?
```

Capture each answer as a candidate pressure point:

```
Pressure N: [one-sentence rule] — anchored to Law M — because [tech constraint]
```

Push-back rules:

- **Rule echoes law stance verbatim.** The rule must add something the law doesn't.
  If the rule is just "do what Law N says" — that is not doctrine, that is the law.
  Push: "That restates the law. What specific operational call does the tech constraint
  force that the law alone wouldn't require?"

- **Multiple laws blamed for one rule.** If the user says "well, it's Laws N and M
  together" — that is fine; capture both anchors. But require the user to name the
  specific intersection: which call does the combination force?

- **No actual limitation named.** "We decided to do it this way" without a tech
  constraint is convention. Push: "What limitation makes this rule necessary? If
  the limitation were gone, would a competent team on the same constitution still
  need this rule?"

### Exit condition

You have 2–10 candidate pressure points. More than 10 is a signal that the user is
conflating conventions with doctrine — Phase 2 will cut heavily.

### WIP checkpoint

Update `DOCTRINE.wip.md`: set `Phase completed: 1` and append:

```markdown
## Candidate pressures (pre-filter)
Pressure 1: [rule] — anchor: Law N — because: [tech constraint]
Pressure 2: ...
```

---

## Phase 2 — Contestedness filter

For each pressure from Phase 1, apply the doctrine key filter:

> "Given current technology, is there a credible counter-rule another competent
> team would adopt — anchored to the **same** constitutional law — that reaches
> the opposite operational conclusion?"

### Procedure per pressure

1. State the pressure's rule and its anchor.
2. Ask: "Would another competent team, working from the same constitution but weighing
   the tech constraints differently — or using a different stack — adopt a counter-rule
   that reaches the opposite conclusion? Name the team or scenario."
3. If the user names a plausible counter-scenario: the pressure **passes**. Capture the
   counter-scenario.
4. If the user cannot name one — the pressure **fails**. It is a default or convention.

**Dispositions:**

- **Passes →** keep on the pressure list; proceeds to Phase 3.
- **Fails →** drop from the doctrine-candidate list. Record in a `CLAUDE.md candidates`
  list. Tell the user: "This one is a convention — it belongs in `CLAUDE.md`, not the
  doctrine. I'll surface it at the end."

Do not let a pressure survive with a hedge. "Probably another team might do it
differently" is not a counter-scenario. If the user cannot name a concrete alternative
stack or weighting, it fails.

**Constitutional candidates from Step 1.5** are pre-filtered — they passed Challenger 4
(Perfect Technology) during constitution work. Treat them as already passing Phase 2 and
move them directly to Phase 3 with the observable condition from their `CONSTITUTION.md`
entry as the starting point for Phase 4's Tech Assumption. Still confirm with the user
that the condition still holds.

### Exit condition

You have a filtered pressure list where each surviving entry has a defensible
counter-scenario. Ideally 2–6 entries for a first-draft doctrine.

### WIP checkpoint

Update `DOCTRINE.wip.md`: set `Phase completed: 2`, replace the pressures section
with the filtered list (mark dropped pressures as `[→ CLAUDE.md]`), and note the
counter-scenario for each surviving pressure.

---

## Phase 3 — Challenger pass

Invoke the three challenger subagents per `commands/refine-doctrine/challenger-prompts.md`.

### Inputs to each challenger

- The full filtered pressure list from Phase 2 (rule + anchor + counter-scenario).
- The `CONSTITUTION_LAWS` list.
- **Do NOT pass the user's tech reasoning.** Challengers must reason from the stated
  rule and anchor only. Passing the user's reasoning causes them to argue inside the
  author's frame, which defeats the point.

### Presentation to user

Present all three challenger outputs together. For each challenge, the user rebuts
in writing. Capture rebuttals verbatim — they feed Phase 4's drafting.

A rebuttal that concedes a point revises the pressure list:

- **Concession that a pressure is not contested →** move to `CLAUDE.md` candidates.
- **Concession that the tech assumption is not observable →** narrow the assumption
  before Phase 4 begins.
- **Concession that the sunset trigger is not falsifiable →** sharpen the trigger
  condition before Phase 4 begins.

### Exit condition

Pressure list is final. Each surviving pressure has: rule, anchor, counter-scenario,
starting tech assumption (possibly sharpened), and challenger rebuttal captured.

### WIP checkpoint

Update `DOCTRINE.wip.md`: set `Phase completed: 3` and append:

```markdown
## Post-challenger pressure list (final inputs to order drafting)
Pressure 1: [rule] — anchor: Law N — assumption draft: [...] — rebuttal: [...]
Pressure 2: ...

## CLAUDE.md candidates so far
- [pressure] — reason: [why demoted]
```

---

## Phase 4 — Order drafting

For each surviving pressure, walk the full order anatomy. One order at a time.
Do not batch.

### Per-order walk

**Rule.** Rewrite the pressure's rule line as an imperative, specific, one-sentence
order. Present tense. Reject "avoid X" or "prefer X" phrasings — the order must be
specific enough to apply in a PR review. The reviewer must be able to look at a diff
and determine whether the order is violated.

**Anchor.** Reference the constitutional law by number and one-phrase stance summary.
If two laws together force this order, list both. If the Anchor cannot be tied to a
specific law from `CONSTITUTION_LAWS`, do not invent one — admit with `[NEEDS ANCHOR]`.

**Tech Assumption.** Ask:

```
What observable technological condition makes this rule necessary right now? Name
a condition a reader could check by inspecting the current state of the technology.
Not "AI is still limited" — what specific, measurable condition?
```

Force observable language. Apply assumption-check rules:

- *"When X is limited"* without naming what limited means. Push: "How would a reader
  check whether X is currently limited enough to require this rule? Name the
  measurable threshold."
- *Refers to your team's implementation rather than the technology itself.* "Because
  we haven't built a better abstraction yet" — that is an implementation choice, not a
  tech assumption. Push: "What external technological condition forces this? If you
  built the abstraction tomorrow, would the rule still apply?"
- *Unfalsifiable maturity claim.* "LLMs are still maturing." Push: "At what specific
  measurable point do LLMs cease to be maturing for this purpose?"

If after one probe the user cannot produce an observable condition, admit with
`[NEEDS ASSUMPTION]` and `[DRAFT]` prefix. Do not invent a plausible-sounding
assumption.

**Sunset Trigger.** Ask:

```
What observable condition retires this order? Name a specific, checkable event —
not "when things improve" but the exact condition whose presence means this rule
is no longer needed.
```

Force falsifiable language. Apply trigger-check rules:

- *"When X improves" without a measurable threshold.* Push: "Improves to what level?
  Name the threshold a reader could check."
- *Vague adoption target.* "When the industry adopts a standard." Push: "Which
  standard, and what adoption level — what percentage of projects, or which specific
  projects, constitute adoption for this purpose?"
- *Team-internal trigger.* "When we build X." Push: "Building X is a project
  decision, not a sunset trigger. What external condition makes building X necessary
  in the first place? If that condition changes, the order retires whether or not
  you've built X."
- *"Never" or "always."* If the user says this rule will never sunset — challenge:
  "If this rule has no sunset trigger, it may be eternal and belong in the
  constitution, not doctrine. Is there truly no technology change that would make
  this rule unnecessary?" If they confirm no sunset exists: propose elevating to
  the constitution (see Phase 5 on the promote path). Do not force a hollow trigger.

If after one probe the user cannot produce a falsifiable trigger, admit with
`[NEEDS SUNSET]` and `[DRAFT]` prefix.

**Anti-pattern.** Ask:

```
Give me the specific thing the code would do if this order were violated. Not
"bad X" — the concrete shape of the violation. One file? One function call?
One import? One data structure?
```

If the user can only produce vague anti-patterns, the *order* is not specific
enough — go back and sharpen the Rule. If after sharpening the user still cannot
produce a concrete violation, admit with `[NEEDS ANTI-PATTERN]` and `[DRAFT]`.

**Scope.** Optional. Ask: "Is this codebase-wide, or does it govern a specific
subsystem or boundary?" Omit the field entirely if truly codebase-wide with no
carve-outs. Do not invent a scope to fill a blank.

**Detector.** Optional. If the anti-pattern maps cleanly to a grep pattern or file
glob, capture it. If not, omit — an order without a detector is still valid.

### Marker grammar (apply exactly)

- `[DRAFT]` — prefix on the Order heading when any element is a marker.
- `[NEEDS ANCHOR]`, `[NEEDS ASSUMPTION]`, `[NEEDS SUNSET]`, `[NEEDS ANTI-PATTERN]` —
  replace the missing element's field value.
- `[UNCHALLENGED]` — suffix on the heading when the challenger pass did not cover
  this order. Should not occur after Phase 3 in normal setup flow; defined here for
  safety if an order is added after Phase 3.

### Promote path (when no sunset trigger exists)

If the user genuinely cannot name a sunset trigger and confirms this rule would hold
under perfect technology — it is not doctrine, it is a law candidate. Do not draft it
as an order. Tell the user:

> "This rule appears to be eternal — it holds regardless of technological conditions.
> It belongs in the constitution, not the doctrine. We will not draft it as a
> Standing Order. Run `/refine-constitution --force-amendment` Subpath A after this
> session to add it as a law."

Record it in a `CONSTITUTION.md candidates` list alongside the `CLAUDE.md candidates`
list. Surface both at Phase 6.

### Per-order WIP save

After completing each order (admitted or deferred), **immediately write the current
state of all drafted orders to `DOCTRINE.md`**. Use the schema from
`commands/refine-doctrine/doctrine-template.md` but leave sections not yet reached
(Retired Orders, Promoted-to-Law Log) empty. This means `DOCTRINE.md` is a valid-but-
incomplete draft after every order, and the refinement subskill can resume from it if
the session ends.

Also update `DOCTRINE.wip.md`: set `Phase completed: 4 (order N of M)`.

Do not wait until all orders are drafted to write `DOCTRINE.md` for the first time.
Write it after order 1. Overwrite it after each subsequent order.

### Exit condition

Every surviving pressure has been walked. Each produced either an admitted order (with
or without markers) or was moved to `CLAUDE.md` / `CONSTITUTION.md` candidates.

---

## Phase 5 — Precedence review

Review the drafted orders for conflicts. Ask:

```
If two of these orders pull in different directions on the same decision — which
wins? Is there a natural precedence among them, or are they truly orthogonal?
```

Orders do not have the same hard precedence structure as constitutional laws — they
govern different tech constraints. But if two orders cover overlapping terrain, the
user should state which takes priority. Renumber if a priority ordering emerges.

This phase is short: most doctrine sets are orthogonal. If the user confirms no
conflicts, record that and move on.

---

## Phase 6 — Emit

Write three things:

### 1. `DOCTRINE.md`

Follow the schema in `commands/refine-doctrine/doctrine-template.md`. Write the
Preamble, Standing Orders, and empty Retired Orders and Promoted-to-Law Log sections.
After writing, delete `DOCTRINE.wip.md` — the session is no longer interrupted.

### 2. `DOCTRINE.mini.md` (conditional)

After writing `DOCTRINE.md`, check whether it is complete (zero markers, Preamble
present, ≥1 order each with all four required fields).

- **If complete:** generate `DOCTRINE.mini.md` per the mini schema in
  `commands/refine-doctrine/doctrine-template.md`.
- **If not complete (markers remain):** skip mini generation. Do not write or update
  `DOCTRINE.mini.md`. If an existing mini file is present from a prior run, delete it
  to prevent stale state.

### 3. Session summary (printed to user, not written to file)

```
Orders admitted:            <count> (of which <draft-count> carry [DRAFT] markers)
CLAUDE.md candidates:       <count> — surfaced below for you to add to CLAUDE.md
CONSTITUTION.md candidates: <count> — surfaced below; run /refine-constitution --force-amendment
Markers remaining:          <list of marker types still present>
Next run will enter:        refinement mode (markers present) | amendment mode (no markers)
```

Then list the `CLAUDE.md candidates` and `CONSTITUTION.md candidates` with one-line
rationales, so the user can act on them in separate passes.

---

## Closing rules

- Do not announce completion if any order has no marker identifying the missing element
  but its fields are empty. The refinement subskill relies on the marker grammar being
  machine-parseable.
- Do not admit an order with a non-observable Tech Assumption. It defeats the purpose
  of doctrine's self-expiring design.
- Do not admit an order with an unfalsifiable Sunset Trigger. An order with no real
  trigger will never retire and will calcify into convention.
- Do not offer to "fill in the details later." If the user cannot produce an observable
  assumption or falsifiable trigger today, admit the marker and let refinement handle it
  when they can.
