// Per-session registry of Codex /responses traffic (vendored by Jev).
//
// Node is the single chokepoint (codex-facing port), so it observes BOTH the
// requested model (payload.model) and the model the upstream actually serves
// (the `model` field echoed in response.created / response.completed SSE
// events). This module records them per thread and persists to sessions.json so
// the local control panel can show how many sessions exist, what each asked
// for, what it really got, and when the two diverged.
//
// Turn classification: alongside the visible user-composed turn, Codex Desktop
// opens both explicitly spawned subagents and internal utility/background
// sessions (memory extraction, review passes, ...) that are hardwired to a
// native model regardless of what the user picked. We label each turn:
//   - "main":       the visible composer turn (strict signature).
//   - "subagent":   a concrete child worker (x-openai-subagent marker or a
//                   parent thread header) -- these markers are reliable.
//   - "background": everything else, i.e. Codex-internal utility work.
//
// Identity handling: a turn's first /responses call occasionally carries no
// thread-id header. Keying that call by model would split ONE message into a
// spurious "model:<x>" row plus the real thread row. Instead, id-less calls
// land in a short-lived pending bucket per requested model; when the real
// thread id arrives (within the same turn) the pending counts fold into that
// one session. Only if no real id appears within PENDING_TTL_MS do we
// materialize a single clearly-labelled "unidentified:<model>" row.
import fs from "node:fs";
import path from "node:path";

import {
  parentThreadIdFromHeaders,
  threadIdFromHeaders,
} from "./codex-session-names.mjs";
import { STATE_DIR } from "./paths.mjs";

const FILE = path.join(STATE_DIR, "sessions.json");
const MAX_SESSIONS = 80;
const ACTIVE_MS = 120_000;
const MAX_MISMATCH = 12;
const PERSIST_DEBOUNCE_MS = 600;
const PENDING_TTL_MS = 12_000;
const PENDING_RECENT_MS = 20_000;

const map = new Map();
// requested model -> { requests, firstAt, lastAt, served, info, timer }
const pending = new Map();
let persistTimer;

function nowIso() {
  return new Date().toISOString();
}

function headerText(headers, name) {
  const value = headers?.[name];
  if (Array.isArray(value)) return value[0];
  return typeof value === "string" ? value : undefined;
}

function load() {
  try {
    const raw = JSON.parse(fs.readFileSync(FILE, "utf8"));
    if (Array.isArray(raw.sessions)) {
      for (const s of raw.sessions) if (s && s.id) map.set(s.id, s);
    }
  } catch {
    /* first run */
  }
}
load();

function persist() {
  try {
    const sessions = [...map.values()]
      .sort((a, b) => (b.lastAt || "").localeCompare(a.lastAt || ""))
      .slice(0, MAX_SESSIONS);
    const tmp = FILE + ".tmp";
    fs.writeFileSync(tmp, JSON.stringify({ version: 1, sessions }));
    fs.renameSync(tmp, FILE);
  } catch {
    /* never break a turn over registry persistence */
  }
}

function schedulePersist() {
  if (persistTimer) return;
  persistTimer = setTimeout(() => {
    persistTimer = null;
    persist();
  }, PERSIST_DEBOUNCE_MS);
  persistTimer.unref?.();
}

function get(id) {
  let s = map.get(id);
  if (!s) {
    s = {
      id,
      firstAt: nowIso(),
      lastAt: nowIso(),
      requests: 0,
      requested: null,
      served: null,
      mismatchCount: 0,
      mismatches: [],
      turnChecked: false,
      kind: null,
      agentName: null,
      turnMeta: null,
    };
    map.set(id, s);
  }
  return s;
}

function applyInfo(s, info) {
  if (!info) return;
  if (info.kind && (!s.kind || info.kind === "main")) s.kind = info.kind;
  if (info.agentName && !s.agentName) s.agentName = info.agentName;
  if (info.turnMeta && !s.turnMeta) s.turnMeta = info.turnMeta;
}

function noteMismatchOnce(s, want, served) {
  if (s.turnChecked) return;
  s.turnChecked = true;
  if (want && served && served !== want) {
    s.mismatchCount = (s.mismatchCount || 0) + 1;
    s.mismatches = s.mismatches || [];
    s.mismatches.unshift({ at: nowIso(), requested: want, served });
    s.mismatches = s.mismatches.slice(0, MAX_MISMATCH);
  }
}

// Fold a recent id-less pending bucket into the real session that just showed
// up. The real start already counted the turn once, so add pending.requests-1.
function foldPending(s, requested) {
  const p = pending.get(requested);
  if (!p) return;
  const age = Date.now() - new Date(p.lastAt || 0).getTime();
  if (age <= PENDING_RECENT_MS) {
    s.requests += Math.max(0, p.requests - 1);
    if (p.firstAt && p.firstAt < s.firstAt) s.firstAt = p.firstAt;
    applyInfo(s, p.info);
    if (p.served) {
      s.served = p.served;
      noteMismatchOnce(s, requested, p.served);
    }
  }
  clearTimeout(p.timer);
  pending.delete(requested);
}

function startPending(requested, info) {
  if (!requested) return;
  const now = nowIso();
  let p = pending.get(requested);
  if (!p) {
    p = {
      requests: 0,
      firstAt: now,
      lastAt: now,
      served: null,
      timer: null,
      info: info || null,
    };
    pending.set(requested, p);
  } else if (info) {
    if (!p.info) p.info = info;
    else if (info.kind === "main") p.info = { ...p.info, ...info, kind: "main" };
  }
  p.requests += 1;
  p.lastAt = now;
  if (!p.timer) {
    p.timer = setTimeout(() => materializePending(requested), PENDING_TTL_MS);
    p.timer.unref?.();
  }
}

function materializePending(requested) {
  const p = pending.get(requested);
  if (!p) return;
  pending.delete(requested);
  const s = get(`unidentified:${requested}`);
  s.requested = requested;
  s.requests = Math.max(s.requests || 0, 1) + Math.max(0, p.requests - 1);
  if (p.firstAt && p.firstAt < s.firstAt) s.firstAt = p.firstAt;
  s.lastAt = p.lastAt;
  applyInfo(s, p.info);
  if (p.served) {
    s.served = p.served;
    noteMismatchOnce(s, requested, p.served);
  }
  schedulePersist();
}

// Resolve the thread/session id for a request, preferring the explicit thread
// header and falling back to the parent thread header.
export function sessionIdFromRequest(request) {
  const headers = request?.headers || {};
  return threadIdFromHeaders(headers) || parentThreadIdFromHeaders(headers) || null;
}

// Classify a /responses turn from its request headers. See the module header
// for the meaning of the three kinds.
export function turnKindFromRequest(request) {
  const headers = request?.headers || {};
  const text = headerText(headers, "x-codex-turn-metadata");
  let meta;
  if (text) {
    try {
      meta = JSON.parse(text);
    } catch {
      meta = undefined;
    }
  }
  const subagentHeader = headerText(headers, "x-openai-subagent")?.trim();
  const hasSubagentMarker =
    Boolean(subagentHeader) &&
    !["0", "false"].includes(subagentHeader.toLowerCase());
  const hasParent = Boolean(parentThreadIdFromHeaders(headers));
  const agentName =
    typeof meta?.agent_name === "string" ? meta.agent_name : undefined;
  const turnMeta = meta
    ? {
        ...(agentName ? { agent_name: agentName } : {}),
        ...(typeof meta.request_kind === "string"
          ? { request_kind: meta.request_kind }
          : {}),
        ...(typeof meta.turn_trigger === "string"
          ? { turn_trigger: meta.turn_trigger }
          : {}),
        ...(typeof meta.thread_source === "string"
          ? { thread_source: meta.thread_source }
          : {}),
      }
    : {};

  const isMain =
    agentName === "/root" &&
    meta?.thread_source === "user" &&
    meta?.turn_trigger === "composer" &&
    meta?.request_kind === "turn";
  if (isMain) {
    return { kind: "main", agentName: agentName || "/root", turnMeta };
  }

  const namedSubagent =
    subagentHeader && !["1", "true"].includes(subagentHeader.toLowerCase())
      ? subagentHeader
      : undefined;
  if (hasSubagentMarker || hasParent) {
    return { kind: "subagent", agentName: namedSubagent || agentName, turnMeta };
  }

  return { kind: "background", agentName, turnMeta };
}

// Mark a turn starting. Id-less calls buffer in pending instead of opening a
// spurious row.
export function start(request, requestedModel) {
  const id = sessionIdFromRequest(request);
  const info = turnKindFromRequest(request);
  if (!id) return startPending(requestedModel, info);
  const s = get(id);
  if (requestedModel) s.requested = requestedModel;
  s.served = null;
  s.turnChecked = false;
  applyInfo(s, info);
  s.requests += 1;
  s.lastAt = nowIso();
  if (requestedModel) foldPending(s, requestedModel);
  schedulePersist();
}

// Feed parsed SSE events; capture the served model and record (once per turn)
// when it differs from the requested model.
export function observeEvent(id, requestedModel, payload) {
  if (!id || !payload) return;
  const served = payload.model || payload.response?.model;
  if (!served) return;
  const s = get(id);
  if (requestedModel) s.requested = requestedModel;
  s.served = served;
  s.lastAt = nowIso();
  if (requestedModel) foldPending(s, requestedModel);
  noteMismatchOnce(s, requestedModel || s.requested, served);
  schedulePersist();
}

export function snapshot() {
  const t = Date.now();
  const sessions = [...map.values()]
    .map((s) => ({
      ...s,
      active: t - new Date(s.lastAt || 0).getTime() < ACTIVE_MS,
    }))
    .sort((a, b) => (b.lastAt || "").localeCompare(a.lastAt || ""))
    .slice(0, MAX_SESSIONS);
  return { version: 1, generatedAt: nowIso(), sessions };
}
