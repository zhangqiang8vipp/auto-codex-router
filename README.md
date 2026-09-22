# Auto Codex Router · 自动 Codex 路由

[![ci](https://github.com/zhangqiang8vipp/auto-codex-router/actions/workflows/ci.yml/badge.svg)](https://github.com/zhangqiang8vipp/auto-codex-router/actions/workflows/ci.yml)

**Session-aware model routing for Codex — one semantic decision per turn, then continuity.**
**面向 Codex 的会话感知模型路由——每个轮次只做一次语义决策，之后保持连续。**

A meaningful user turn opens a *route lease* (model + reasoning effort). Tool
continuations, background calls and compaction keep that route without asking
the decision model again; repeated tool failures may raise the lease locally.
The next meaningful user turn reopens routing.

一个有意义的用户轮次会建立一条“路由租约”（模型 + 推理强度）。后续的工具续接、后台调用与压缩
都会沿用该路由，不再重复询问决策模型；连续工具失败会在本地升级。下一个有意义的用户轮次才会
重新路由。

- **EN:** Destination, milestones and borrowed ideas: [VISION.md](VISION.md), [ROADMAP.md](ROADMAP.md).
- **中文：** 产品目标、里程碑与借鉴的思想见 [VISION.md](VISION.md)、[ROADMAP.md](ROADMAP.md)。
- **EN:** Historical simulation (≈ −60 % vs full Astra, with caveats): [BACKTEST.md](BACKTEST.md).
- **中文：** 历史回测（相比全程 Astra 约省 60%，含口径说明）见 [BACKTEST.md](BACKTEST.md)。

---

## How it works · 工作原理

**EN — KEEP is the default; REPLAN requires evidence.**

| Situation | Action |
| --- | --- |
| New meaningful user turn | Decide (ask the semantic judge) |
| Tool call → result → continuation | **KEEP** the same model + effort |
| Compaction | **KEEP** |
| Replay of the same turn | **KEEP** |
| Tool failures `< 2` | **KEEP** |
| Tool failures `≥ 2` | Raise to at least **Sol · high** |
| Tool failures `≥ 3` | Raise to at least **Astra · xhigh** |

**中文——默认保持（KEEP），只有出现证据才重新规划（REPLAN）。**

| 情况 | 动作 |
| --- | --- |
| 新的有意义用户轮次 | 决策（询问语义判断器） |
| 工具调用 → 结果 → 续接 | **保持** 同一模型 + 强度 |
| 上下文压缩 | **保持** |
| 同一轮次重放 | **保持** |
| 工具失败 `< 2` 次 | **保持** |
| 工具失败 `≥ 2` 次 | 至少升到 **Sol · high** |
| 工具失败 `≥ 3` 次 | 至少升到 **Astra · xhigh** |

Leases are persisted (a service restart keeps them) and invalidated when the
policy version changes. Concurrent requests for the same session are merged via
single-flight, so they never pay for two decisions at once.

租约会持久化（服务重启后仍保留），策略版本变更时自动失效。同一会话的并发请求通过 single-flight
合并，不会同时为两次决策付费。

---

## Built-in control panel · 内置控制面板

**EN:** Once the service is running, open **http://127.0.0.1:4319/** in a browser.
The panel is bilingual and works offline:

- Turn **Auto routing** on/off (replaces the old desktop pill);
- See the **current route** — model, effort, source and reason;
- Watch **today's stats** — total calls, decisions, lease reuse, escalations,
  and how many decisions were saved;
- Follow a **live activity** feed.

**中文：** 服务运行后，在浏览器打开 **http://127.0.0.1:4319/**。面板中英双语、可离线使用：

- 开启 / 关闭 **自动路由**（替代旧的桌面角标）；
- 查看 **当前路由**——模型、推理强度、来源与原因；
- 查看 **今日统计**——总请求、决策次数、租约复用、升级，以及省下了多少次决策；
- 查看 **实时活动** 流。

> **Default is OFF.** Auto routing is never enabled without an explicit action.
> **默认为关闭状态。** 未经明确操作，不会开启自动路由。

---

## Install · 安装

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/zhangqiang8vipp/auto-codex-router/main/install.ps1 | iex
```

**macOS / Linux:**

```bash
git clone https://github.com/zhangqiang8vipp/auto-codex-router.git
cd auto-codex-router && ./setup-local.sh
```

**EN:** Installing with an AI agent? Hand it [AGENTS.md](AGENTS.md).
**中文：** 用 AI 智能体来安装？把 [AGENTS.md](AGENTS.md) 交给它。

This project plugs into an existing local **Codex Router** installation through
its official extension points (a generic provider + a curated model), so router
updates do not overwrite it.

本项目通过官方扩展点（一个通用 provider + 一个 curated 模型）接入已有的本地 **Codex Router**，
因此 router 更新不会覆盖它。

---

## Acknowledgments · 致谢

**EN:** This project began as a fork of
[**0xNatoshi/jev-codex-router**](https://github.com/0xNatoshi/jev-codex-router)
(MIT), which builds on the
[codex-router](https://github.com/duolahypercho/codex-router) runtime. It has
since grown into an independent branch with its own session-aware routing,
route leases, Windows tooling and reliability work. Sincere thanks to
[**@0xNatoshi**](https://github.com/0xNatoshi) and the upstream contributors
for open-sourcing their work — this project is built on their shoulders and will
remain open source under MIT.

**中文：** 本项目最初 fork 自
[**0xNatoshi/jev-codex-router**](https://github.com/0xNatoshi/jev-codex-router)
（MIT），后者构建于 [codex-router](https://github.com/duolahypercho/codex-router)
运行时之上。此后它发展为一个独立分支，加入了自己的会话感知路由、路由租约、Windows 工具链与
可靠性改造。由衷感谢 [**@0xNatoshi**](https://github.com/0xNatoshi) 与上游贡献者开源他们的
工作——本项目站在他们的肩膀上，并将始终以 MIT 保持开源。

---

## License · 许可证

MIT. Fork it, change the policy, keep your own tandem — no permission needed.
MIT。欢迎 fork、修改策略、保留你自己的模型组合，无需另行授权。
