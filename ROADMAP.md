# Roadmap — Session-aware Codex Runtime

> Last updated: 2026-09-22  
> Baseline: `main@755d2fc`  
> Product direction: see [VISION.md](VISION.md)

## 0. What we are building

This project is evolving from a per-call model router into a **local,
session-aware execution runtime for Codex**.

In plain language, the runtime should continuously know:

1. **what task Codex is doing now;**
2. **whether anything important has actually changed;**
3. **what context the next step truly needs;**
4. **which model + reasoning effort should execute that step;**
5. **what must survive Codex compaction so the task does not “forget” critical
   constraints or decisions.**

The runtime should not invoke another model merely because Codex emitted another
HTTP `/responses` call.

The core rule is:

> **KEEP is the default. REPLAN requires evidence.**

The long-term core abstractions are:

```text
Session State
    ↓
Context Lease
    ↓
Route Lease
    ↓
Execution + Reliability
```

Jev is the current semantic route judge. It is a replaceable decision provider,
not the final product.

---

## 1. Current baseline — already completed

### Transport and reliability foundation

The current production path already has:

- Codex native Responses transport;
- native Luna / Terra / Sol / Astra execution;
- model + reasoning-effort routing;
- authenticated exact native-route callback into Codex Router;
- safe fallback to legacy redirect suppression when the exact-route hook cannot
  be verified;
- SSE response-id continuity;
- terminal quota handling;
- breaker and retry handling;
- monotonic escalation deadline;
- Auto ON/OFF control;
- passive Shadow Eval;
- route/session telemetry.

### Route Lease v1

Merged in `755d2fc`.

A meaningful new user turn opens a semantic routing decision and stores:

```text
model
effort
turn identity
policy version
route source
```

Then:

```text
tool continuation
→ KEEP

background continuation
→ KEEP

compaction continuation
→ KEEP

duplicate/replayed user turn
→ KEEP

failure streak >= 2
→ local floor: Sol/high

failure streak >= 3
→ local floor: Astra/xhigh

new meaningful user turn
→ REPLAN
```

Repeated tool failures escalate locally and do **not** require another Jev call.

This is the first major architectural change away from “Jev on every Responses
call.”

---

## 2. Non-negotiable runtime invariants

These rules must remain true through all future refactors.

### Continuity

- A valid Route Lease is reused across ordinary tool loops.
- Codex compaction is a context lifecycle event, **not** a route boundary.
- A replay of the same semantic user turn must not create another paid Jev
  decision.
- Concurrent copies of one semantic decision must coalesce.
- A policy-version change invalidates an old lease.

### Reliability

- Intelligent policy may fail; transport correctness must not.
- Never write a second HTTP response after downstream response commit.
- Client disconnect ends that execution path.
- Breakers may skip unhealthy tiers upward but must never wrap a high-tier
  request downward accidentally.
- Terminal account/workspace quota is not model-health evidence.

### Error semantics

**Internal runtime failures must never masquerade as Codex's official usage
limit.**

Only an explicit native ChatGPT/OpenAI quota signal may be translated into the
terminal Codex usage-limit path.

The following must **not** become `insufficient_quota`:

```text
Jev failure
router/caller-edge connection failure
HTTP 502
HTTP 503
HTTP 504
deadline expiry
breaker-open failure
ordinary transient 429 / rate_limit_exceeded
local Python exception
```

The following native upstream signals may be treated as true terminal quota:

```text
usage_limit_reached
usage_not_included
insufficient_quota
credit / workspace hard-limit headers
other explicitly allowlisted native hard-stop codes
```

This distinction needs permanent regression coverage.

### Privacy

Route/session metadata may persist:

- hashes;
- model/effort;
- policy version;
- bounded counters;
- provenance labels.

Route/session metadata must not persist:

- raw prompt text;
- tool output;
- credentials;
- absolute paths;
- ChatGPT session tokens.

---

# 3. Immediate next work — finish Route Lease v1 properly

This is the highest-priority work before any context pruning.

## 3.1 Lock down the error invariant

Add regression tests proving:

```text
502 internal error          != official usage limit
503 breaker open            != official usage limit
504 deadline                != official usage limit
Jev failure                 != official usage limit
caller-edge connection fail != official usage limit
ordinary 429                != official usage limit

real native hard quota
=> terminal Codex usage-limit semantics
```

**Exit condition:** future transport refactors cannot accidentally turn an
internal failure into the Codex “You have reached your usage limit” UI.

## 3.2 Validate Route Lease with real telemetry

Use the current Shadow Eval/logging to measure:

- Jev semantic decision count;
- Jev paid cache-miss count;
- lease KEEP count;
- local escalation count;
- model-switch count;
- tool error rate;
- retry rate;
- latency;
- total/cached native tokens;
- compaction turns;
- route source breakdown.

The important metric is not simply “fewer Jev calls.”

The first gate is:

```text
quality / operational reliability >= old baseline
```

Only after that do we optimize:

```text
Jev calls ↓
latency ↓
switches ↓
routing overhead ↓
```

## 3.3 Verify these real workflows

Focused end-to-end scenarios:

1. one user turn → many tool calls → only one semantic Jev decision;
2. duplicate/replayed request → no extra paid Jev decision;
3. concurrent continuations → no duplicate semantic decision;
4. first tool failure → KEEP;
5. repeated failures → local escalation, zero extra Jev;
6. Codex compaction during active work → Route Lease survives;
7. new real user task → old lease is invalidated;
8. service restart → persisted lease can recover continuity;
9. Auto OFF → native Codex behaviour remains intact;
10. real account quota → native Codex usage-limit UI, no HTTP retry storm.

**Exit condition:** Route Lease v1 is boring and predictable in daily use.

---

# 4. Phase 2 — Boundary Engine

Route Lease v1 currently treats a meaningful new user turn as a REPLAN boundary.
That is intentionally conservative.

The next improvement is to distinguish:

```text
“继续”
“接着做”
“跑一下测试”
“看看结果”
```

from a genuinely new task or phase.

## First implementation

Do **not** begin with another generative model.

Use deterministic state and explicit execution events first:

```text
same active goal
same tool chain
same verification target
no contradictory user instruction
no new hard constraint
        ↓
KEEP
```

Clear boundaries include:

- new task/goal;
- user changes requirements;
- active plan invalidated;
- investigation → implementation;
- implementation → verification;
- repeated failure requiring replan;
- task complete → new task.

## Later implementation

Once enough real outcome data exists:

```text
deterministic boundary rules
          ↓
small local classifier
      /             \
 confident         uncertain
    ↓                 ↓
 boundary          Jev / planner
```

**Exit condition:** “continue” turns no longer pay for unnecessary route
judgements while genuine task changes still REPLAN reliably.

---

# 5. Phase 3 — Durable Task Ledger + Compaction Sentinel

Codex may compact long context. The runtime must not assume compaction preserves
every hard user constraint in a form we can audit.

The runtime therefore needs a small structured durable ledger.

## Persist only durable semantic state

Examples:

```text
goal
hard constraints
acceptance criteria
accepted decisions
open blockers
verified facts
important evidence references
verification state
current phase id
```

Do **not** build a second canonical chat transcript.

Facts need provenance, for example:

```text
USER_CONSTRAINT
OBSERVED_FACT
VERIFIED_DECISION
AGENT_HYPOTHESIS
DERIVED_STATE
```

A user constraint must never silently become equivalent to an agent hypothesis.

## Compaction handling

Codex compaction should increment a context generation:

```text
generation 17
    ↓ compaction
generation 18
```

Then:

```text
Route Lease
→ normally KEEP

Context Lease
→ invalidate / reconcile
```

**Exit condition:** after compaction, the runtime can reconstruct the current
goal, constraints, unresolved work and route continuity without trusting an
opaque compressed history as its only memory.

---

# 6. Phase 4 — Context Compiler in shadow mode

Before deleting anything from production context, compute what the runtime
*would* keep or omit.

Conceptual buckets:

```text
PINNED
- user goal
- hard constraints
- active plan
- unresolved error
- active tool-chain dependency

ACTIVE
- currently relevant files/entities
- recent evidence
- current investigation

SUMMARY
- completed phases
- resolved investigations

OMIT
- duplicate reads
- stale successful tool output
- disproved detail no longer needed
- unrelated historical noise
```

Shadow mode records:

- full context size;
- proposed served context size;
- items kept;
- items omitted;
- later items that would have required rehydration.

No production pruning yet.

**Exit condition:** we have evidence about false-eviction risk before changing
the model's real input.

---

# 7. Phase 5 — Conservative Context Execution + Rehydration

Enable production pruning gradually.

Order:

1. exact duplicates;
2. repeated tool noise;
3. completed/stale successful outputs;
4. summarized completed phases;
5. dependency-aware eviction;
6. adaptive context budget.

Rehydration sources should prefer deterministic/local retrieval:

```text
current repository
git
tests
SQLite / FTS5 session index
ripgrep
symbol index
durable ledger evidence refs
```

A generative model is not required to retrieve known facts.

Key principle:

> **A good context system is not one that deletes aggressively. It is one that
> can safely remove information because it knows how to recover it.**

**Exit condition:** served context drops materially without a post-pruning
quality cliff or constraint-loss regressions.

---

# 8. Phase 6 — Local routing, Jev as fallback/teacher

Jev should eventually stop being the mandatory online classifier.

Desired control path:

```text
valid continuity lease?
      |
      +-- yes --> KEEP
      |
      no
      ↓
deterministic boundary
      ↓
small local router
   /             \
confident       uncertain / OOD
   |                 |
 route               Jev
```

Training/evaluation data can come from:

- task/phase signals;
- previous route;
- failure streak;
- tool outcomes;
- Jev choices;
- actual served route;
- latency/tokens;
- task completion proxies.

Jev becomes:

- fallback judge;
- teacher;
- hard-case planner;
- shadow evaluator.

The runtime should remain usable with:

```text
provider = jev
provider = ollama
provider = local
provider = hybrid
```

---

# 9. Phase 7 — Joint Execution Planner

Only after Route Lease, Boundary Engine and Context Compiler are independently
stable should context and routing become one decision.

The planner consumes:

```text
Session State
current phase
Durable Ledger
working-set pressure
previous Context Lease
previous Route Lease
cache/switch economics
failure evidence
```

and emits one **Execution Directive**:

```text
phase
context lease
route lease
safeguards
valid-until conditions
```

This avoids contradictory independent decisions such as:

```text
Context Manager: “easy phase, discard investigation state”
Route Manager:   “hard debugging phase, switch to Astra”
```

Both must be derived from the same execution state.

---

# 10. What we borrow instead of reinventing

The project should integrate proven ideas rather than copy whole frameworks.

## vLLM SAAR / Semantic Router

<https://vllm.ai/blog/2026-06-02-session-aware-agentic-routing>

Use for:

- session-aware route continuity;
- tool-loop hard locks;
- safe switching boundaries;
- later switch/cache economics;
- replayable decision traces.

## OpenClaw

<https://github.com/openclaw/openclaw/blob/main/docs/concepts/compaction.md>

Use for:

- compaction as an explicit lifecycle;
- pre-compaction durable-memory/checkpoint thinking;
- memory separate from active context.

## Hermes Agent

<https://github.com/NousResearch/hermes-agent>

Use for:

- durable session/state patterns;
- SQLite + FTS5 retrieval;
- small persistent memory plus on-demand historical lookup;
- pluggable context-engine ideas.

## Switchcraft

<https://www.microsoft.com/en-us/research/publication/switchcraft-ai-model-router-for-agentic-tool-calling/>

Use for:

- small low-latency local routing model;
- avoiding a large generative router for every decision.

## RouteLLM

<https://arxiv.org/abs/2406.18665>

Use for:

- learning quality/cost routing from preference/outcome data;
- avoiding hand-written model-share targets.

## ACON

<https://www.microsoft.com/en-us/research/publication/acon-optimizing-context-compression-for-long-horizon-llm-agents/>

Use for:

- outcome-driven context compression;
- learning from full-context success vs compressed-context failure;
- later distillation of a small compressor.

The rule is: borrow the architecture/ideas that solve each layer; keep Codex
native Responses transport and ChatGPT session integration as this project's
own execution substrate.

---

# 11. Which layers may call a model API?

Most runtime control should not.

| Layer | Extra model call? | Technique |
|---|---:|---|
| HTTP / SSE / breaker / quota / deadlines | No | deterministic code |
| session identity | No | hashes + state |
| tool-loop continuity | No | Route Lease |
| compaction detection | No | request/event shape |
| ordinary KEEP decision | No | state machine |
| repeated-failure escalation | No | deterministic floors |
| repository/session retrieval | No | git / SQLite FTS5 / ripgrep |
| durable user constraints | Usually no | provenance-aware facts |
| semantic boundary detection | Later, sometimes | local classifier |
| route selection at a real boundary | Sometimes | local router / Jev |
| semantic context summarization | Occasionally | auxiliary/local model |
| actual coding execution | Yes | native Luna/Terra/Sol/Astra |
| passive online evaluation | No | telemetry |
| controlled offline judging/training | Optional | eval pipeline |

A healthy long-running coding task should look more like:

```text
30 native Codex execution calls
1-3 semantic route decisions
0-few auxiliary memory/context calls
```

not:

```text
30 native Codex calls
30 Jev calls
```

---

# 12. Evaluation strategy

Do not optimize for “router accuracy” in isolation.

The product objective is:

```text
first:
task quality / reliability >= baseline

then minimize:
unnecessary route decisions
model cost
latency
context tokens
model switches
recovery work
```

Track:

- Jev decisions;
- paid Jev decisions;
- lease KEEP;
- local escalation;
- model switches;
- completion/failed Responses;
- tool errors;
- retries;
- latency;
- input/output/cached tokens;
- compactions;
- post-compaction errors/corrections;
- later context rehydration;
- duplicate work after compaction.

Long-term controlled baselines:

```text
native/fixed default
fixed strong model
adaptive runtime
```

Do not claim semantic quality improvements from passive production telemetry
alone.

---

# 13. Recommended execution order

The development order should remain:

```text
DONE
Transport + runtime safety
        ↓
DONE
Route Lease v1
        ↓
NEXT
Route Lease hardening + error invariant tests + real telemetry
        ↓
Boundary Engine
        ↓
Durable Task Ledger + Compaction Sentinel
        ↓
Context Compiler shadow mode
        ↓
Conservative Context Execution + Rehydration
        ↓
Local Router / Jev fallback
        ↓
Joint Context + Route Execution Planner
```

Do not jump directly to aggressive context pruning or a large multi-model
planner before the continuity layer is proven.

The next engineering objective is deliberately narrow:

> **Make “do not ask Jev again unless execution state really changed” a boring,
> tested, observable invariant.**
