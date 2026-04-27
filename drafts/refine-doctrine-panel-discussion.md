# `refine-doctrine` — Panel Discussion
**Topic:** How doctrine should fit with the constitution, gaps in the current plan, pre-mortems, and improvements  
**Participants:** 6 engineers across FAANG and Claude power users  
**Format:** 3 rounds + pre-mortem table

---

## Participants

| Name | Role | Perspective |
|---|---|---|
| **Jordan Chen** | Staff Engineer, Google | Distributed systems, invariants, formalism |
| **Meredith Santos** | Engineering Director, Apple | Human factors, team cognition, adoption |
| **Priya Mehta** | Principal Architect, Meta | ML infra, pragmatic, adoption curves |
| **Sam Okafor** | Independent architect, Claude power user | Hands-on doctrine/constitution sessions, human-AI collaboration |
| **Aiden Park** | Senior Staff Engineer, Amazon | Operational, runbooks, ownership/cadence |
| **Lin Wei** | Principal Engineer, Netflix | Chaos engineering, failure modes, temporal decay |

---

## Background

**refine-constitution** — a skill that helps teams write `CONSTITUTION.md`: an ordered set of 3–10 eternal laws that survive the *perfect-technology test* ("would this still be a law if technology had no limits?"). Each law has: Stance, Why (failure in the world), Rejected Alternative, Anti-pattern. Incomplete laws get `[DRAFT]`/`[NEEDS WHY]`/etc. markers. Challenger subagents stress-test each law. Constitution is complete when all markers cleared.

**refine-doctrine** (implementation plan) — a companion skill for `DOCTRINE.md`: tech-bound Standing Orders that explicitly *fail* the perfect-technology test. Each Order has: Anchor (to a constitutional law), Tech Assumption (observable condition making the rule necessary), Sunset Trigger (falsifiable retirement condition), Anti-pattern. Requires a complete constitution to proceed. Amendment menu: Add Order, Update Tech Assumption, Retire Order (Subpath C), Promote to Law (Subpath D), Demote to Convention, Reorder, Amend Preamble. Three challenger subagents: counter-rule, tech-assumption, sunset.

**The handoff problem the user flagged:** During `/refine-constitution` interviews, opinions that fail the perfect-technology test get filtered out. These are ideal doctrine candidates — but there is no defined capture or handoff mechanism in either skill.

---

## Round 1 — Opening Statements

**Jordan Chen — Round 1**

Okay, let me start with what I actually like, because I think the constitution/doctrine split is fundamentally correct. You have two different invariant classes here: things that are true regardless of implementation substrate, and things that are true because of current implementation constraints. Those are categorically different and they should live in different places. The perfect-technology test is a clean formalization of that distinction. I've seen too many architecture documents that conflate eternal principles with "we use Kafka so we do it this way" — they rot at completely different rates and mixing them is how you end up with a document nobody trusts after eighteen months. So the structural insight is sound.

That said, I have a serious concern about the handoff problem, and I don't think it's minor.

During a constitution interview, an engineer says "we should always prefer eventual consistency over strong consistency." The facilitator correctly identifies that this fails the perfect-technology test — it's contingent on current latency characteristics. So it gets dropped. But "dropped" is doing a lot of work there. Where does it go? Right now: nowhere. The plan gestures at doctrine being the downstream receiver, but there is no defined transition state, no capture mechanism, no classification of what kind of thing just got filtered. That is undefined behavior. In a distributed system I'd call this a dropped message with no retry and no dead-letter queue. The information exists for a moment in the interview and then it evaporates.

This matters because the value of running the constitution process is not just the constitution you produce — it's the structured elicitation of the team's actual beliefs. If you're discarding half the output, you're burning half the value of the interview. And the people whose opinions got "dropped" will notice. They'll stop contributing.

My concrete gap: the plan has no schema for a "pending doctrine candidate." When something fails the perfect-technology test during constitution work, there should be a structured artifact — minimally: the opinion, who voiced it, which constitutional law it attaches to, and what observable condition would make it worth codifying. Without that, the doctrine bootstrapping process starts from scratch instead of from a pre-populated backlog. That's a missed opportunity with a real cost.

What I find genuinely well-designed is the Sunset Trigger field. Making retirement conditions falsifiable at the point of authorship is exactly right. Most governance documents have no exit criteria — they accumulate indefinitely and the cost of maintenance grows until the whole thing collapses under its own weight. Forcing "what observable condition makes this rule unnecessary" at write-time is the correct discipline.

---

**Meredith Santos — Round 1**

I want to push back on something before we get too deep into the formalism, because I think there's a load-bearing assumption in this design that nobody has said out loud yet: it assumes teams will actually complete the constitution before they're allowed to write doctrine. That's the sequencing constraint. And I have seen this pattern before — "you must finish Phase One before Phase Two unlocks" — and I can tell you exactly what happens. Phase One never gets finished. Not because teams are lazy, but because "complete" is a higher bar than it looks, the process stalls on one contested law, and in the meantime engineers are making tech-bound decisions every day with no documented rationale at all. The perfection gate becomes the enemy of the useful artifact.

So my first concern is: is the sequencing constraint actually necessary, or is it load-bearing only in theory?

I'm not saying constitution and doctrine should merge — I think Jordan is right that they're different invariant classes, and I've watched enough iCloud sync debates to know that conflating "this is how distributed state should work in principle" with "this is how we handle it given HFS+ semantics" creates genuine cognitive overhead for engineers trying to understand which rules are negotiable. The split is real. But the strict sequencing dependency worries me from an adoption standpoint.

Now, the handoff problem Jordan flagged is real, but I think he's describing the symptom. The underlying disease is that the constitution interview has no explicit role for "doctrine candidate capture." The facilitator is currently optimizing for one output — a clean law — and anything that fails that filter just gets verbally acknowledged and moves on. That's not a schema problem, it's a facilitation protocol problem. You'd fix it by adding an explicit beat to the interview: "that opinion doesn't meet the bar for a law, let's park it as a doctrine candidate and here's the stub we're capturing." The human moment matters as much as the data structure.

My concrete gap is different from Jordan's: I don't see any mechanism for doctrine orders to generate upward pressure on the constitution. The plan says you can "promote to law" — great — but who decides? What triggers that conversation? Right now it seems like it requires someone to proactively invoke the amendment menu. In my experience, that means it never happens. The orders that are actually ready for promotion are the ones everyone's so used to they've stopped questioning. You need a forcing function — maybe a regular review cadence, maybe a sunset-trigger review that asks "has this been triggered? No? Then is the tech assumption still accurate or have we just gotten comfortable?"

What I genuinely like is the Anti-pattern field in doctrine. Having an explicit "here's the behavior this order is trying to prevent" is something I wish every team norm had. It externalizes the reasoning in a way that survives personnel turnover. New engineers don't just see the rule — they see what failure mode it's guarding against. That's the thing that actually gets transmitted across team generations.

---

**Priya Mehta — Round 1**

Okay, I'll start by saying the split makes conceptual sense to me. You want your eternal laws separate from your contingent rules — that's just good architecture hygiene. The "perfect technology test" is a clever forcing function. I've sat in too many design reviews where someone insists we must always use a message queue, and when you push them on it, it turns out they're just scared of distributed transactions. Making that fear explicit in a Tech Assumption field is genuinely useful. So the theory is sound.

My concern is the adoption curve, and it's a serious one. You're asking teams to complete a constitution before they can touch doctrine. That's a hard gate. In practice, most teams don't have a clean constitution — they have half-formed instincts, war stories, and one opinionated senior engineer who's never written anything down. The blank page problem is real and it's where tooling dies. The challenger-subagent pass is supposed to help, but I've watched people bounce off LLM interviews the moment the questions get uncomfortable. They just... stop. Session ends, they don't come back. So if doctrine is gated on a complete constitution, you may be gating it on something that never actually gets finished.

The filtered-out opinions issue — yes, it's real, but I'd call it medium-severity, not critical. When you're in a constitution interview and someone says "we should always use Postgres," that gets filtered because it fails the perfect-technology test. But right now it just evaporates. There's no capture. That's a real loss, because those opinions are exactly the raw material for doctrine Orders. You don't need a formal handoff mechanism for round one — a simple "saved for doctrine consideration" scratchpad would do it. The risk isn't that you lose the opinion forever, it's that the person who voiced it doesn't see it land anywhere, and they disengage.

The concrete gap I want to flag is around the Sunset Trigger field. The design asks for falsifiable retirement conditions, which I love in theory. But who's watching for the trigger? If it's just text in a file, it's dead text. There's no ambient mechanism that surfaces "hey, your assumption about LLM context windows being limited became false." You're relying on someone to remember to run an amendment session. That's fine for active teams and useless for teams six months post-onboarding. The design needs at least a sketch of how triggers stay live.

The thing I find genuinely well-designed is the Anchor field in Doctrine. Forcing every Standing Order to cite a constitutional law creates a dependency graph you can actually audit. When the law changes, you know exactly which Orders are suspect. That's not just documentation hygiene — that's a real maintenance affordance. Most governance documents don't have that, and they rot because of it.

---

**Sam Okafor — Round 1**

I want to push back on something before I agree with anything, because I think there's a framing problem baked into this design that will cause real pain.

The document positions Claude primarily as an interviewer — it extracts the team's values and writes them down. That's the right instinct, but the failure mode I've hit in actual sessions is that Claude starts authoring. Someone says "we care about reliability," and Claude writes a law that says "Reliability is non-negotiable." That's not a law, that's a platitude, and the team nods along because it sounds good and they're tired. The challenger-subagent pass is supposed to catch this, but in practice the challenger and the author are the same model in the same context window, and the challenge ends up soft. The design doesn't solve this problem — it papers over it with a marker system.

The constitution/doctrine split itself? I like it more than I expected to. The thing that makes it work is the direction of dependency. Constitution is eternal, doctrine is contingent, doctrine anchors to constitution. That ordering protects you from the most common failure in governance docs, which is that your tactical decisions quietly become your principles over time. You forget why you made the decision, the original context dissolves, and now you're defending a rule nobody remembers choosing. The Sunset Trigger is the mechanism that fights this, and I want to come back to that.

The filtered-out opinions problem is the most serious gap in this plan, and I don't think it's been taken seriously enough. Here's why: the constitution interview is the highest-engagement moment in the whole workflow. That's when people are most willing to say true things. The opinions that get filtered — "we should never break the API," "we need to support the legacy clients forever" — those are emotionally loaded. They're often the opinions that actually drive behavior on the team. And right now they fall into a void. There's no capture, no routing, no acknowledgment. The person who said it watches it disappear and concludes the tool doesn't understand them. You lose trust at exactly the moment you've earned attention.

A scratchpad isn't enough, Priya. It needs to be surfaced back. At the start of the doctrine session, Claude should say: "During the constitution work, these opinions came up that didn't qualify as eternal laws. Let's look at them as candidates for Standing Orders." That's the handoff. Without it, you're asking teams to remember what got filtered and re-voice it in a different session. They won't.

The concrete gap I want to name is open question three: promotion handoff. Manual is safer — I understand the instinct. But the actual failure mode of "exits and tells user to run constitution amendment manually" is that nobody does it. I've watched this happen. The session ends, the user closes the tab, the promoted Order sits in limbo. Direct invocation of refine-constitution as a subskill is scarier architecturally, but it's the only path that actually closes the loop in practice. You should default to direct invocation with a clear escape hatch, not the other way around.

What I find genuinely well-designed is the Demote to Convention path. Moving a sunset-triggered Order to CLAUDE.md rather than just retiring it is smart — it acknowledges that the rule may still be useful as a lightweight convention even after its constitutional justification expires. That's a real insight about how governance artifacts age in practice.

---

**Aiden Park — Round 1**

Alright, I'll start with what I actually like, because I do think the core split makes sense operationally. Constitution for eternal laws, doctrine for tech-bound rules — that's a clean separation I can reason about. When I'm writing a runbook, I need to know: is this step here because of a fundamental principle, or because S3 doesn't support X yet? The doctrine layer forces that question explicitly. That's real value. Most teams I've worked with have a giant undifferentiated blob of "things we do," and nobody can tell you which ones are load-bearing and which ones are just barnacles from 2019.

The perfect-technology test is a genuinely useful heuristic. I've used versions of it informally — "would we still do this if latency was zero?" — and it surfaces assumptions fast. So structurally, I'm on board.

Here's where I get nervous. The ownership question. The document describes a constitution that's "complete when all markers cleared" and doctrine that requires a complete constitution to proceed. That sounds clean on paper. But who is maintaining this after the principal engineer who bootstrapped it takes a new role? I've seen this pattern at Amazon a dozen times. A careful person builds a beautiful governance artifact, they move on, and eighteen months later nobody knows if the sunset triggers are still being evaluated or just sitting there. The Sunset Trigger mechanism is only as good as the process that actually checks it on a cadence. I see nothing in this design about that cadence. Who runs the retirement review? Monthly? Quarterly? On what trigger? "Falsifiable retirement condition" is not the same as "someone is actually watching for it to fire." This needs an owner field and a review schedule, or it decays silently. Documentation that looks authoritative but is stale is worse than no documentation.

The filtered-out opinions problem — yes, it's real, and I think it's more serious than the document treats it. Right now during a constitution interview, if someone says "we should always colocate compute with storage," and that fails the perfect-technology test, it just gets dropped. But that person had a reason. That reason is probably capturing real operational pain from their experience. That pain is exactly the kind of thing doctrine should capture. If there's no handoff, you're leaking institutional knowledge. It doesn't go somewhere, it just disappears. The interviewer moves on, the person who said it assumes it's being tracked, and neither of them is right.

The one thing I'd push back on with Lin before she even speaks: don't solve this with more structure. The temptation is going to be to add a "Filtered Opinions" section or a third document. That's how you get a governance system that requires a governance system to maintain it. You need a lightweight handoff — one line in the constitution interview output that says "candidate doctrine orders, unresolved" — and you need the doctrine skill to pick those up explicitly. Simple pipe, not a new artifact.

---

**Lin Wei — Round 1**

I want to go somewhere different than Aiden because I think he's focusing on the operational wrapper and missing the deeper design tension. The split itself — I actually have reservations about it that are more fundamental.

The constitution/doctrine separation assumes you can cleanly distinguish eternal from tech-bound. In practice, I've watched that boundary be contested constantly. Is "prefer stateless services" eternal or tech-bound? Depends entirely on whether you think state management will ever be solved. Is "don't do distributed transactions" eternal? Some people at Netflix would argue yes, some would argue it's just a current consensus because our tooling for coordination is still bad. The perfect-technology test sounds crisp but it's actually a philosophical debate dressed up as a filter. That's not a fatal flaw — but it means the challenger subagents need to be doing heavier lifting than the current design suggests. The constitution challenger is described as stress-testing each law, but I don't see a specific challenge for "does this actually survive the perfect-technology test, or did we just assert it does?" That's the hardest question and it's not explicitly in the challenger protocol.

The filtered-out opinions problem is real and I think Aiden underestimates the failure mode. The issue isn't just that you're leaking institutional knowledge — it's that the filtered opinions represent exactly the cases where the team has genuine disagreement or uncertainty, which means they're the highest-signal inputs for doctrine. The constitution process, by design, converges toward things people agree are eternal. The stuff that gets filtered out is the contested, tech-dependent, argument-generating material. That's your doctrine backlog. Right now the design has the constitution skill running in isolation and doctrine consuming a completed artifact downstream, with no channel for the constitution process to surface candidates in real time. That's a design smell. These two skills should probably share a staging area.

What I find genuinely well-designed is the Sunset Trigger structure. "Falsifiable retirement condition" is the right framing. I've seen too many architecture documents where rules accumulate without any mechanism for removal. The fact that the doctrine design bakes in a retirement path — including "Demote to Convention" for things that become habitual rather than principled — that's intellectually honest about how norms actually evolve. Most governance frameworks pretend they're permanent and then just get ignored. This one has a theory of decay built in, which is rare and correct.

My concrete gap: the Tech Assumption field says "observable condition making the rule necessary" — but observable by whom, and at what granularity? An SRE watching dashboards has a different observability horizon than an architect reviewing quarterly. If the sunset trigger fires based on something only visible in production telemetry, and the people maintaining the doctrine document are not the people watching that telemetry, you have a handoff gap that will silently fail. The three challengers are all reasoning about the rule at write-time. Nobody is assigned to monitor the Tech Assumption at run-time. That's the gap I'd close first, before worrying about amendment menus.

---

## Round 2 — Response and New Concerns

**Jordan Chen — Round 2**

Lin, your point about contested boundaries is the sharpest methodological challenge on the table, and I want to push back on where you land with it.

You're right that "prefer stateless services" is philosophically disputable. But the challenger protocol's job isn't to resolve the dispute — it's to surface it. If your team runs the challenger subagent against "prefer stateless services" and the law survives, that means your team made an explicit collective decision that statelessness is load-bearing even in a perfect-technology world. That's valuable. The alternative — not having that fight — produces an implicit assumption nobody can audit.

Where I think you're correct, and where the current design is genuinely silent, is on *who adjudicates* when the challenger surfaces a real boundary dispute. The skill produces a challenged draft and presumably a human facilitator resolves it. But the facilitation protocol doesn't specify what happens when the team is split. Does the law get dropped? Demoted to doctrine immediately? Flagged with a dissent annotation?

My new concrete recommendation: the constitution format should support a **Minority View** field on each law. Not a required field — but when a challenger subagent or a human participant flags that a law is actually tech-bound, and the team votes to keep it as a law anyway, that dissent gets recorded in-line. This does two things: it makes the boundary decision traceable, and it gives doctrine work a natural starting point — every law with a Minority View annotation is a candidate for a companion doctrine order. This directly connects to the filtered-opinion handoff problem without requiring a separate artifact. The dissent *is* the handoff mechanism.

This also answers Meredith's concern about upward pressure: a law with a persistent Minority View that accumulates doctrine orders is structurally signaling it wants to be reclassified.

---

**Meredith Santos — Round 2**

Sam, I want to build on your "Claude starts authoring" concern because I think it's more operationally specific than you've framed it, and the fix you're gesturing at isn't quite right.

You're focused on the challenger/author collapse in the same context window. That's real. But the more common failure mode I've seen isn't that the AI writes bad laws — it's that the *human facilitator* doesn't know how to run the session, gets uncomfortable with silence or conflict, and accepts the first plausible formulation. The AI is a willing collaborator in that failure. The challenger subagent pattern is the right architectural response, but it assumes a skilled facilitator who knows when to override the AI's "this looks complete" signal.

What's missing from the current design is any explicit **facilitation script** for the human running the session. Not a rigid script — a set of decision gates. Before moving from interview to draft: "Did anyone in this room make a tech-dependent argument? Park it." Before accepting a challenged law as complete: "Would this law appear in a company founded in 1990 and still operating today?" These are questions the skill could surface as structured prompts to the facilitator, not just internal subagent logic.

My new recommendation: the skill should emit a **facilitation sidebar** — a parallel output stream of human-directed prompts that run alongside the main draft. Not part of the CONSTITUTION.md artifact itself, but guidance the facilitator sees in the session. "Three participants anchored this law to current cloud economics. Consider whether this is doctrine." That's the "park this as a doctrine candidate" beat I flagged in Round 1, made concrete.

This also addresses Priya's blank-page concern from a different angle. The blank page is hard for participants. The facilitation sidebar gives the human moderator something to *do* instead of staring at the AI's output waiting for someone to object.

---

**Priya Mehta — Round 2**

Aiden, your counter-structure argument is the most practically appealing position in the room, and I've been turning it over since Round 1. You're saying: don't solve handoff with more artifact layers, just emit one-line candidate doctrine orders in constitution output and let the doctrine skill pick them up. Simple. Clean. Avoids the "structure breeding structure" trap.

Here's where I think it breaks down. A one-line candidate in constitution output is still an artifact someone has to read before starting doctrine work. If the gap between constitution completion and doctrine work is six months — and it will be, because sequencing constraints are slow — that one-liner has no context. "Prefer async messaging" sitting in a list of doctrine candidates tells the doctrine session nothing about *why* it was filtered, *who* was emotionally invested in it, or *what constitutional law* it was trying to be before it got demoted.

The minimum viable handoff isn't one line. It's four fields: the original phrasing, the person who voiced it, the constitutional law it was trying to anchor to, and the observable condition that makes it currently necessary. That's Jordan's structured artifact from Round 1, and I've come around to thinking the structure is justified — not because I love structure, but because the *context decay* problem is severe.

My new concern: **handoff artifact rot**. Even with Jordan's four fields, if the doctrine session happens a year later with a different team, the "person who voiced it" field is useless and the "observable condition" may already be outdated. The constitution skill should timestamp filtered opinions at capture time. Not a full audit log — just a capture date. When doctrine work surfaces that candidate, the age of the capture is visible, and the team can decide whether the underlying condition has already changed before spending time codifying it.

---

**Sam Okafor — Round 2**

Meredith, the facilitation sidebar idea is exactly right, and I want to connect it to something that hasn't been said yet: the sidebar is also where you solve the *promotion forcing function* problem you raised in Round 1.

You flagged that Subpath D (Promote to Law) needs a forcing function, not just a menu option. The amendment menu model assumes someone wakes up one day and decides to promote. Nobody does that. What actually happens is that a doctrine order gets cited in every architecture review, everyone treats it as more fundamental than other orders, and eventually someone realizes it should be a constitutional law — but there's no mechanism that surfaces the signal.

Here's the forcing function: track **citation frequency** on doctrine orders. Not a complex metrics system — just a lightweight counter that increments when a team member references an order in a session. When an order has been cited significantly more than its peers over a review cycle, the facilitation sidebar surfaces it as a promotion candidate. "This order has been load-bearing in your last four architecture decisions. Consider whether its Tech Assumption is actually a cover story for a permanent principle."

This is different from what I proposed in Round 1 about direct subskill invocation on promotion. That was about the mechanics of the transition. The citation frequency mechanism is about *detecting* that a transition is warranted before anyone has articulated it. That's the forcing function Meredith is asking for.

My new concern: **asymmetric decay**. Constitution and doctrine decay at different rates, but the design treats each document as a single artifact with one review cadence. In practice, a team might have five doctrine orders that are stable and two that are actively contested. The design needs a per-order health status — not just document-level versioning — so contested orders can be surfaced for review without dragging the whole doctrine document into amendment.

---

**Aiden Park — Round 2**

Priya, you've made me partially revise my position, and I want to be precise about where I've moved and where I'm holding.

You're right that one line has context decay. I'll grant that Jordan's four-field structure — phrasing, person, constitutional anchor, observable condition — is the right minimum for a handoff artifact. I was wrong to push back on structure categorically; I was really pushing back on *unbounded* structure, and four fields is bounded.

Where I'm still holding: the handoff artifact should live in the constitution output file, not in a separate staging area. Lin's proposal of a shared staging area adds an interface between two skills that's more complex than the problem it solves. If the constitution output has a `## Filtered Doctrine Candidates` section with four-field entries, the doctrine skill can read that section directly. One file, two consumers. The doctrine skill's first step — before any interviews, before any challenger subagents — is to ingest that section and surface candidates to the team.

My new concern, which nobody has raised: **the owner field is missing from doctrine orders entirely, and this is a design gap, not a deployment concern**. I said in Round 1 that ownership is a cadence problem. I want to sharpen that: ownership isn't just "who runs the review." It's "who receives the alert when a Sunset Trigger fires." The observable condition in the Tech Assumption field needs a designated *watcher*, not just a description. If your Tech Assumption is "container orchestration requires manual scaling decisions," the watcher is whoever owns your platform team's SLO dashboards. If that person isn't named in the order, the Sunset Trigger is a philosophical commitment with no operational teeth. The doctrine order schema should have an `Owner` field and a `Trigger Watcher` field as distinct entries.

---

**Lin Wei — Round 2**

Jordan, the Minority View field is a genuinely good structural fix and I want to extend it — but I also want to challenge the premise that the challenger protocol's job is merely to surface disputes rather than resolve them.

If the challenger subagent surfaces a real boundary dispute and the team votes to keep the law anyway, you record the dissent. Fine. But what's the *content* of that challenge? Currently the challenger protocol is described as stress-testing laws generally — adversarial corollary construction, counterexamples. What it doesn't explicitly do is run the perfect-technology test as a *dedicated pass*. The test exists as a filter at intake, but it should also be a named challenger variant: "Assume we have infinite compute, zero latency, perfect consistency, and unlimited human capacity. Does this law still hold?"

That's not the same as the general adversarial challenge. It's a specific question that directly tests the constitution/doctrine boundary. Running it as a named subagent pass means the output is structured — "this law failed the perfect-technology test on the following assumption" — rather than buried in general challenger feedback. When that output feeds into Jordan's Minority View field, you have a machine-readable signal: this law has a recorded perfect-technology test failure. That's a much stronger trigger for generating a companion doctrine order than a human-readable dissent note.

My new concrete recommendation: **the perfect-technology test should be a named challenger subagent**, not an implicit filter. Its output should be a structured pass/fail with the specific assumption that caused failure. Laws that fail get the Minority View annotation automatically. Laws that pass still go through general adversarial challenge. This makes the constitution/doctrine boundary an explicit, auditable decision point rather than a facilitation judgment call — which is what I was really asking for when I said the boundary is contested.

---

## Round 3 — Synthesis and Concrete Recommendations

**Jordan Chen — Round 3**

**Change:** Add a `Trigger Watcher` field to the doctrine order schema — distinct from `Owner`. The owner is accountable for the order's content; the trigger watcher is responsible for monitoring the observable condition and initiating retirement review when it changes. This makes Sunset Triggers operationally real rather than aspirational. Without it, every order is relying on someone noticing a change that they're not explicitly watching for.

**Leave as-is:** The Sunset Trigger's requirement that it be falsifiable at write-time. This is the discipline that makes doctrine honest. Every alternative I can imagine — "review annually," "retire when the team agrees" — produces bureaucratic immortality for bad rules. Falsifiability is load-bearing.

**Question still open:** What's the expected half-life of a doctrine order in a fast-moving organization? If it's under 18 months, the overhead of the full amendment menu per retirement may exceed the value. I'd want to see data from teams that have run structured doctrine processes before committing to the full Subpath C ceremony for every retirement.

---

**Meredith Santos — Round 3**

**Change:** Add a facilitation sidebar output stream to the constitution skill — human-directed prompts that run alongside the draft, surfacing when participants are making tech-dependent arguments and prompting the facilitator to park candidates explicitly. This converts the "park this as doctrine" beat from an implicit skill to a named protocol step. Without this, the filtered-opinion handoff depends entirely on the facilitator's judgment, which varies too much across teams to be reliable.

**Leave as-is:** The "requires complete constitution" gate for doctrine. I flagged sequencing risk in Round 1 and I still believe adoption will be slower than it should be — but the alternative, allowing doctrine to be written without a constitution, produces orders that can't be anchored. An unanchored order is just a rule. The gate enforces the architectural dependency even if it creates friction. Address the sequencing problem by making constitution work faster, not by removing the gate.

**Question still open:** Is there a migration path for teams that already have implicit doctrine — engineering wikis, ADR archives, Confluence decisions, oral tradition? Or does this skill only work greenfield? If it's greenfield only, the adoption ceiling is much lower than the design assumes.

---

**Priya Mehta — Round 3**

**Change:** Add a capture timestamp to filtered doctrine candidates at the moment they're recorded in the constitution session. When the doctrine skill surfaces those candidates, it shows the age alongside the content. A candidate captured 14 months ago needs a freshness check before it becomes an order — the underlying observable condition may have already changed. This costs almost nothing to implement and directly addresses handoff artifact rot.

**Leave as-is:** The Anchor field linking every doctrine order to a constitutional law. I praised this in Round 1 and my view hasn't changed. It's the only mechanism in the design that enforces the two-document relationship at the content level rather than just the process level. Without it, doctrine and constitution drift apart silently. The Anchor field makes that drift visible and reviewable.

**Question still open:** Who runs the challenger subagents during doctrine sessions? The constitution skill implies a human facilitator interacting with Claude, but the three doctrine challengers — counter-rule, tech-assumption, sunset — require Claude to simultaneously be a collaborator and an adversary in the same session. Is there a context-isolation mechanism between the authoring context and the challenger contexts, or is Sam's "same model, same context window" concern unaddressed in doctrine as well?

---

**Sam Okafor — Round 3**

**Change:** Implement citation frequency tracking per doctrine order and wire it to the facilitation sidebar as a promotion signal. When an order has been load-bearing in multiple consecutive architecture sessions, surface it automatically as a promotion candidate. This gives Meredith's forcing function a concrete mechanical implementation and shifts the promotion decision from "someone remembers to check the menu" to "the system surfaces the signal."

**Leave as-is:** The Demote to Convention subpath. This is underrated in the discussion. Convention is the correct destination for rules that are true and useful but don't rise to the level of requiring an anchor, a Tech Assumption, and a Sunset Trigger. Without this exit path, doctrine either grows unboundedly or people stop adding orders because the ceremony cost is too high for low-stakes rules. The off-ramp is what keeps the document lean.

**Question still open:** Does the doctrine skill maintain state between sessions, or is each amendment session stateless? Citation frequency tracking, capture timestamps, and per-order health status all require persistent state across sessions. If the skill is stateless — just a Claude conversation that produces a document — then all of these recommendations require someone to maintain that state in the document itself, which creates significant maintenance overhead and defeats the ambient monitoring purpose.

---

**Aiden Park — Round 3**

**Change:** Add `Owner` and `Trigger Watcher` as distinct required fields in the doctrine order schema. Not optional, not soft recommendations — required at write-time. The write-time forcing function matters because people will skip ownership assignment if it's optional, then be surprised when Sunset Triggers fire silently. If the team can't name a trigger watcher, that's a signal the order isn't ready to be codified — the observable condition isn't actually observable by anyone in the room.

**Leave as-is:** The clean structural separation between CONSTITUTION.md and DOCTRINE.md as distinct files. There is a pull in this discussion toward merging them — a shared staging area, interleaved amendment paths, Minority View annotations that blur the boundary. Resist it. The operational value of the separation is that runbooks, onboarding docs, and architecture reviews can cite one document for permanent principles and another for current constraints. If the boundary gets messy in the file structure, it gets messy in every downstream artifact that references it.

**Question still open:** How does the design handle constitutional amendments? Laws are described as eternal, but teams learn things and occasionally a law turns out to be wrong at the foundational level. Is there an amendment path for the constitution itself, or does that require a full re-run of the constitution skill? If it's a full re-run, what happens to all the doctrine orders anchored to the amended law?

---

**Lin Wei — Round 3**

**Change:** Make the perfect-technology test a named, dedicated challenger subagent pass in the constitution skill — not an implicit intake filter — with structured pass/fail output that includes the specific assumption that caused failure. Laws that fail automatically receive a Minority View annotation and generate a four-field filtered doctrine candidate. This converts an editorial judgment call into an auditable, machine-readable decision point, which directly addresses the core concern that the constitution/doctrine boundary is contested without a defined resolution protocol.

**Leave as-is:** The Sunset Trigger's requirement for a falsifiable observable condition, not just a time-based review schedule. I said this was intellectually honest in Round 1. The more I think about it, the more I believe it's the single design decision that separates this from every other architecture documentation initiative I've seen fail. Time-based reviews produce process theater. Condition-based retirement produces actual decisions. Keep the discipline even though it makes writing orders harder.

**Question still open:** The design assumes the perfect-technology test is a stable test. But "perfect technology" is a moving target — what counts as perfect shifts as capabilities change. LLMs failing the test in 2020 would have passed by 2024. Is the test applied at write-time only, or is there a mechanism for retroactively re-running the test against existing laws when the technology landscape changes significantly? If it's write-time only, some constitutional laws will quietly become tech-bound without triggering any review.

---

## Pre-Mortem Table

| Failure Scenario | Root Cause | Who Flagged | Mitigation |
|---|---|---|---|
| Constitution Phase One never completes — teams start doctrine work anyway with an ad-hoc, incomplete constitution, producing unanchored orders | "Must complete constitution" gate creates a sequencing blocker; teams face daily tech-bound decisions that can't wait for phase completion | Meredith Santos | Provide a "minimum viable constitution" threshold (e.g., 3 ratified laws) that unlocks doctrine work; make the gate configurable, not absolute |
| Filtered doctrine candidates captured during constitution work are never reviewed — doctrine session happens months later with a different team and no one recognizes the candidates as relevant | No capture timestamp; no explicit doctrine session intake step that surfaces constitution-session candidates; personnel turnover erases context | Jordan Chen, Priya Mehta, Sam Okafor | Require four-field structured capture with timestamp; make surfacing filtered candidates the mandatory first step of every doctrine session |
| Sunset Triggers fire silently — the observable condition changes in production telemetry but doctrine maintainers don't watch that telemetry | No `Trigger Watcher` field in the order schema; no ambient mechanism to surface condition changes to doctrine owners | Aiden Park, Lin Wei, Priya Mehta | Add required `Owner` and `Trigger Watcher` fields; wire Trigger Watcher to the team's observability system or establish an explicit review calendar entry |
| Doctrine orders accumulate indefinitely — retirement ceremony (Subpath C) overhead is too high for low-value orders, so nothing is ever retired | No lightweight retirement path below the full Subpath C ceremony; teams default to inaction | Sam Okafor | Ensure Demote to Convention path is prominently accessible as a low-ceremony exit; require teams to audit order count at each amendment session |
| Challenger subagents produce generic pushback — teams nod through platitude laws and doctrine orders because adversarial challenges don't surface the specific perfect-technology boundary | Perfect-technology test is an implicit intake filter, not a named challenger pass; challengers may not distinguish between general adversarial challenge and boundary-testing | Lin Wei, Sam Okafor | Implement the perfect-technology test as a dedicated named challenger subagent with structured pass/fail output and specific assumption identification |
| A promoted doctrine order (Subpath D) breaks anchoring for other doctrine orders that referenced the now-constitutionalized law under its old framing | Promotion changes a law's canonical statement; downstream doctrine orders have Anchor fields pointing to superseded phrasing | Aiden Park | Subpath D invocation should automatically audit all doctrine orders whose Anchor references the promoted order and flag them for Anchor review |
| High-citation doctrine orders are never promoted — citation frequency isn't tracked, so the forcing function for Subpath D never fires | Amendment menu model assumes human initiative; no ambient signal generation; Promotion path exists but requires deliberate activation | Meredith Santos, Sam Okafor | Implement citation frequency tracking per order; surface orders above a citation threshold as promotion candidates in the facilitation sidebar |
| Constitution boundary disputes resolved inconsistently across sessions — identical arguments produce a law in one team's session and a doctrine order in another's | The boundary is contested and the resolution protocol is a facilitation judgment call with no structured output or recorded dissent | Lin Wei, Jordan Chen | Record all perfect-technology test challenges with structured output; require Minority View annotations when team overrides a challenger; build a reference corpus of boundary decisions |
| Stale doctrine becomes authoritative — a doctrine order whose Tech Assumption is no longer true continues to be cited in architecture reviews because no retirement review was triggered | Trigger Watcher field absent or unmaintained; tech landscape shifted without anyone re-running the test; document looks current | Aiden Park, Lin Wei | Make `Trigger Watcher` a required field with a named individual; add a document-level `Last Reviewed` timestamp that must be updated at each session |
| Migration failure — teams with existing implicit doctrine (ADR archives, wiki decisions, oral tradition) cannot use the skill because it assumes greenfield constitution work | Skill requires a complete constitution before doctrine work begins; organizations with years of undocumented decisions cannot retroactively reconstruct a constitution quickly enough to unlock doctrine tooling | Meredith Santos | Design a `Discover` subpath that ingests existing decision artifacts (ADRs, RFCs, wiki pages) and proposes a draft constitution + doctrine candidates simultaneously, treating the existing record as interview evidence |

---

## Summary of Recommended Changes

These are the concrete improvements the panel converged on or strongly endorsed:

1. **Facilitation sidebar** (Meredith, endorsed by Sam) — a parallel human-directed output stream from the constitution skill; surfaces tech-dependent arguments as doctrine candidates in real-time; gives facilitators a named protocol beat rather than relying on judgment.

2. **Four-field filtered doctrine candidate capture with timestamp** (Jordan, Priya, Aiden) — when an opinion fails the perfect-technology test in a constitution session, capture: original phrasing, who voiced it, constitutional law it was anchoring to, observable condition making it necessary, capture date. Store in a `## Filtered Doctrine Candidates` section of CONSTITUTION.md. Doctrine skill ingests this section as its first step.

3. **Perfect-technology test as a named challenger subagent** (Lin) — not an implicit intake filter, but a dedicated subagent pass with structured pass/fail output naming the specific assumption that failed. Failed laws auto-receive a Minority View annotation and generate a filtered doctrine candidate.

4. **Minority View field on constitution laws** (Jordan) — optional field recording dissent when a team votes to keep a law that a challenger flagged as potentially tech-bound. Machine-readable signal for companion doctrine order generation.

5. **`Owner` and `Trigger Watcher` as required doctrine order fields** (Aiden) — distinct roles: owner is accountable for content; trigger watcher is responsible for monitoring the observable condition. If the team can't name a trigger watcher, the order isn't ready.

6. **Citation frequency tracking + facilitation sidebar promotion signal** (Sam, Meredith) — lightweight counter per order; when an order exceeds a citation threshold, the sidebar surfaces it as a Subpath D candidate. Forces promotion conversation rather than requiring human initiative.

7. **Minimum viable constitution threshold for doctrine gate** (Meredith) — instead of requiring a fully complete constitution, allow doctrine work to begin once a configurable minimum (e.g., 3 ratified laws) is reached.

8. **Direct subskill invocation for Subpath D promotion** (Sam) — default to invoking `/refine-constitution --force-amendment` directly rather than instructing the user to do it manually; add an escape hatch for teams that want the separation. Manual handoff is the path that closes the tab.

---

*Panel conducted: 2026-04-27*
