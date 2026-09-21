# Jev Codex Router

[![ci](https://github.com/zhangqiang8vipp/jev-codex-router/actions/workflows/ci.yml/badge.svg)](https://github.com/zhangqiang8vipp/jev-codex-router/actions/workflows/ci.yml)

**Session-aware model routing for Codex, with [Jev](https://docs.typesafe.ai) (TypeSafe System One) as the current semantic route judge.**

A meaningful user turn opens a route lease (model + reasoning effort). Tool
continuations, background calls and compaction continuations keep that route
without asking Jev again; repeated tool failures may raise the lease locally.
The next meaningful user turn reopens semantic routing. Every route uses
standard speed.

The long-term product direction is a local session-aware Codex execution
runtime that jointly manages continuity, context and model capacity. See
[VISION.md](VISION.md) for the destination and [ROADMAP.md](ROADMAP.md) for the
implementation plan, milestones, borrowed ideas and safety gates.

**Historical simulation: ≈ −60 % vs full Astra** on 237 turns under the old
policy. This is not measured Codex quota saved, nor evidence for the current
policy — protocol and limitations in [BACKTEST.md](BACKTEST.md).
Installing with an AI agent? Hand it [AGENTS.md](AGENTS.md).

This is not a fork of any router: it plugs into an existing local
**Codex Router** installation through its official extension points
(a *generic provider* + a *curated model*), so router updates never overwrite it.

**Fork it. Change the policy. Keep your own tandem.** MIT. No permission needed.
See [Fork and customize](#fork-and-customize--允许自己改) below.

## Auto toggle on Windows

Codex already owns the model picker and reasoning-effort control. This project
does **not** duplicate them. On Windows it adds one small WPF/UIAutomation
`Auto` pill next to Codex's native reasoning control.

- **Auto OFF**: Jev Auto is disabled. On a normal installation with no prior
  native redirect, Codex's own model + reasoning choices go straight through
  the native ChatGPT path.
- **Auto ON**: Codex Router's `native-redirect` is set to `jev/auto`.
  A meaningful user turn is classified by Jev and establishes a route lease.
  Subsequent tool/background/compaction calls in that session normally reuse