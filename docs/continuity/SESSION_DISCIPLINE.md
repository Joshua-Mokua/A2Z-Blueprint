# SESSION_DISCIPLINE.md

**Purpose:** the operator-side playbook that makes `SESSION_BOOTSTRAP.md`
actually work. Continuity is half tooling, half discipline. The bootstrap
file is the tooling; this file is the discipline.

**Audience:** Joshua (operator), future collaborators, and any Claude
instance reading this in-session.

---

## Core principle

> **Chats are execution environments, not memory stores.**

Memory lives in the repo: governance artifacts, canonical registries,
ledgers, CHANGELOGs. Chats are where work gets done, not where context
gets accumulated. When a chat ends, nothing should be lost â€” because
everything important is in the repo.

If you find yourself thinking "I need to remember this for next chat,"
the answer is: **write it to the repo**, not the chat. Update
`SESSION_BOOTSTRAP.md`, append to `REVIVAL_LEDGER.md`, or amend the
relevant CHANGELOG.

---

## Starting a new chat â€” the opener

Every new chat begins with one of these openers. Pick based on intent.

### Opener A â€” Continuing existing work

For when you're picking up where a previous session left off.

```
I'm working on A2Z Blueprint. Before we begin:

1. Read docs/continuity/SESSION_BOOTSTRAP.md from
   github.com/Joshua-Mokua/A2Z-Blueprint. That orients you to current
   state, active workstreams, and known rediscovery traps.

2. Last shipped commit: <SHA from bootstrap>

3. Today I want to work on: <one-sentence intent>

Acknowledge that you've read the bootstrap, summarize back in 2-3
sentences what you understand about current state, then we'll begin.
```

### Opener B â€” Starting a fresh workstream

For when you're beginning a new arc not covered in active workstreams.

```
I'm working on A2Z Blueprint. Before we begin:

1. Read docs/continuity/SESSION_BOOTSTRAP.md (gives current state and
   rediscovery traps).

2. I'm starting a NEW workstream: <describe>. This is not in the current
   "Active workstreams" list in the bootstrap.

3. Read relevant existing artifacts: <list 1-3 specific artifacts the
   workstream touches, e.g. AI_GOVERNANCE.md for AI work>

Acknowledge bootstrap + relevant artifacts read, propose a plan in 5
bullets or fewer, then we'll begin.
```

### Opener C â€” Diagnostic-only session

For when you're investigating, not building.

```
I'm investigating something in A2Z Blueprint. Quick context: <one
paragraph>. Don't author code yet. Just help me diagnose. If you need
state context, read docs/continuity/SESSION_BOOTSTRAP.md and any
specific artifact I name.
```

---

## When to start a new chat

**Start fresh when:**

- A batch just shipped (the previous chat's diagnostic context is no
  longer useful)
- The current chat is past ~30 turns (degradation begins to show)
- You're switching workstreams (Stage C â†’ Phase 1 â†’ React migration)
- You're seeing repeated mistakes from the AI in the current chat
  (sign of context degradation)
- The current chat has a very long search/inspection trail (large
  context budget already consumed)

**Continue in the current chat when:**

- The work is one continuous arc still in progress
- The context built up is directly relevant to the next step
- You'd lose meaningful diagnostic state by restarting

**Bias:** when in doubt, start fresh. Restarting is cheap. Suffering
through a degraded session is expensive.

---

## When to update SESSION_BOOTSTRAP.md

**Always update when:**

- A batch ships (new commit SHA, new batch number, possibly new gate count)
- A doctrine claim is corrected (CGR1 reality-grounding procedure ran)
- A new rediscovery trap was painfully learned (add it to the traps list)
- Active workstream changes significantly
- The "Next concrete action" needs to point somewhere different

**The discipline:** updating the bootstrap is part of finishing a batch,
not a separate task. The git commit that ships the batch should ALSO
update the bootstrap. If you ship code without updating the bootstrap,
the next session pays rediscovery tax.

**Quick checklist at batch ship time:**

```
[ ] Code shipped and tested
[ ] Per-batch CHANGELOG written (e.g. docs/CHANGELOG_vXXXXX.md)
[ ] REVIVAL_LEDGER.md updated (top entry = newest)
[ ] GOVERNANCE_REALITY_INDEX.md updated if any doctrine corrected
[ ] SESSION_BOOTSTRAP.md updated:
    - Commit SHA in "Current certified state"
    - Batch number
    - Gate count if changed
    - "Active workstreams" if changed
    - "Top rediscovery traps" if new trap learned
    - "Next concrete action" â€” what's next
[ ] All staged + committed together
[ ] Pushed to origin/main
```

---

## How to avoid rediscovery loops

**Symptoms of a rediscovery loop:**

- Re-running `findstr` for things you already searched for
- Re-loading large file contents into context that you already saw
- Re-explaining doctrine you already established
- The AI proposing solutions that contradict CGR1-classified ASPIRATIONAL
  doctrine as if it were ACTIVE

**Counter-measures:**

1. **Always start a new chat with an opener** (above). Never start with
   "hey can you help me with X" â€” that produces archaeology.
2. **Be explicit about reality vs. aspiration.** If the AI proposes
   work that depends on something ASPIRATIONAL per
   GOVERNANCE_REALITY_INDEX.md, push back: "that's ASPIRATIONAL â€” let's
   work in current reality."
3. **Keep diagnostic dumps in the chat, NOT in the bootstrap.** The
   bootstrap should reference where to look, not contain the data
   itself. Once a chat ends, the dump is gone â€” but the canonical
   source (the actual file in the repo) remains.
4. **When the AI is wrong about state**, correct it in-chat AND
   add a trap to SESSION_BOOTSTRAP.md so the next session avoids it.

---

## Bootstrap update template

When updating the bootstrap at end of batch, use this diff pattern:

```diff
- **Last commit on main:** `<old SHA>` (vX.YYY Batch N)
+ **Last commit on main:** `<new SHA>` (vX.ZZZ Batch M)
- **Last shipped batch:** vX.YYY Batch N â€” <old date>
+ **Last shipped batch:** vX.ZZZ Batch M â€” <new date>
  (... existing content ...)
- **Gate count:** <old count> total
+ **Gate count:** <new count> total
```

Then update workstreams, traps (if new), next action.

This should take 2-3 minutes per batch. If it takes longer, the
bootstrap is getting too detailed â€” prune.

---

## When to delete this file

If a year from now, A2Z has automated continuity tooling, an AI
assistant with persistent project memory, or a different architecture
that makes this file redundant â€” delete it without ceremony. This file
exists to solve a specific operational problem; when the problem is
solved differently, the file's job is done.

Better to delete and recreate than maintain something that's drifted
from its purpose.

---

## What this file deliberately does NOT cover

- Per-artifact governance details (lives in `docs/architecture/`)
- Per-batch deltas (lives in `docs/CHANGELOG_*.md`)
- Operational lineage (lives in `REVIVAL_LEDGER.md`)
- Doctrine classification (lives in `GOVERNANCE_REALITY_INDEX.md`)
- Coding standards (would live in a CONTRIBUTING.md â€” TBD if needed)
- Deployment runbooks (TBD)

If you need any of those, those artifacts (or their absence) are the
right place to look â€” not this file.

---

**End of SESSION_DISCIPLINE.md** â€” last updated: 2026-05-22.
