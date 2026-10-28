// Stealth (auto-off, real signed-in Codex) low-level forward.
//
// undici `fetch` is a faithful HTTP client but it is NOT silent: it injects
// connection/keep-alive, accept-encoding, accept-language and sec-fetch-mode
// headers the official Codex client never sends, and it controls header order
// and the TLS/ALPN fingerprint. To make the auto-off path indistinguishable
// from Codex talking to chatgpt.com directly, this module:
//   - opens an HTTP/2 (TLS, ALPN h2) session itself;
//   - replays the exact headers Codex sent (no fetch defaults added);
//   - writes the exact original (already zstd) body bytes;
//   - wraps the h2 response in a standard web Response so the existing
//     pipeResponse pipeline is reused unchanged.
//
// Egress: a direct TLS socket is tried first (best case: TUN/transparent VPN
// or direct network). If direct fails fast (DNS poisoning / connect timeout,
// which is what happens when the VPN is "system proxy only"), the same TLS+h2
// connection is tunneled through the local HTTP proxy with CONNECT. Nothing
// about the wire changes: SNI is still chatgpt.com, ALPN is still h2, headers
// and body are byte-identical; only the local TCP leg goes via the proxy.
// The TLS ClientHello is still Node's either way (that last fingerprint cannot
// change without a different TLS stack).
import http2 from "node:http2";
import net from "node:net";
import tls from "node:tls";
import { execFileSync } from "node:child_process";

// Hop-by-hop / h1 transport headers that must never travel over h2. Host is
// replaced by :authority; content-length is the one transport header h2 still
// allows, so it is preserved.
const DROP = new Set([
  "host",
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "proxy-connection",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
]);

function replayHeaders(req) {
  const out = {};
  for (let i = 0; i < req.rawHeaders.length; i += 2) {
    const name = req.rawHeaders[i];
    const value = req.rawHeaders[i + 1];
    const lower = name.toLowerCase();
    if (DROP.has(lower)) continue;
    if (lower in out) {
      out[lower] = `${out[lower]},${value}`;
    } else {
      out[lower] = value;
    }
  }
  return out;
}

/* ----------------------- local proxy discovery ----------------------- */

// Direct dialing must fail fast: when TUN is off the DNS is poisoned and the
// connect hangs, and every egress-cache expiry pays this probe once. 5s made
// each network switch cost a visible stall; 2s keeps the same direct-first
// semantics while cutting that penalty. On failure the proxy path still takes
// over and is held for PROXY_HOLD_MS.
const DIRECT_PROBE_TIMEOUT_MS = 2000;
const PROXY_HOLD_MS = 5 * 60 * 1000; // prefer a working proxy for 5 min
const DIRECT_HOLD_MS = 60 * 1000;

function normalizeProxy(value) {
  if (!value) return null;
  let v = String(value).trim();
  if (!v) return null;
  if (!/^\w+:\/\//.test(v)) v = `http://${v}`;
  let u;
  try {
    u = new URL(v);
  } catch {
    return null;
  }
  // Only HTTP proxies (which support CONNECT) are handled. SOCKS needs a
  // separate client and is intentionally not silently rewritten.
  if (u.protocol !== "http:" || !u.hostname) return null;
  if (!u.port) u.port = "80";
  return u;
}

export function proxyFromEnv(env = process.env) {
  for (const key of ["HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"]) {
    const u = normalizeProxy(env[key]);
    if (u) return u;
  }
  return null;
}

// WinINET ProxyServer can be "host:port", "host:port;", or a per-protocol map:
// "http=host:port;https=host:port;".
export function parseWinInetProxyServer(raw) {
  if (!raw) return null;
  const generic = [];
  const map = {};
  for (const token of String(raw).split(";")) {
    const t = token.trim();
    if (!t) continue;
    const eq = t.indexOf("=");
    if (eq === -1) {
      if (generic.length === 0) generic.push(t);
    } else {
      map[t.slice(0, eq).trim().toLowerCase()] = t.slice(eq + 1).trim();
    }
  }
  return normalizeProxy(map.https || map.http || generic[0]);
}

export function wininetProxy() {
  if (process.platform !== "win32") return null;
  try {
    const out = execFileSync(
      "reg",
      ["query", "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings"],
      { encoding: "utf8", timeout: 2000, stdio: ["ignore", "pipe", "ignore"] },
    );
    let enabled = false;
    let server = null;
    for (const line of out.split(/\r?\n/)) {
      const m = line.match(/^\s*([A-Za-z]+)\s+REG_\w+\s+(.*)$/);
      if (!m) continue;
      if (m[1] === "ProxyEnable") enabled = m[2].trim() === "0x1";
      if (m[1] === "ProxyServer") server = m[2].trim();
    }
    return enabled ? parseWinInetProxyServer(server) : null;
  } catch {
    return null;
  }
}

// Alias kept for start.mjs, which imports the WinINET reader under this name.
// Returns a URL (with .href) for the current Windows system proxy, or null.
export const readWininetProxy = wininetProxy;

export function detectProxy() {
  return proxyFromEnv() || wininetProxy() || null;
}

/* ----------------------- socket establishment ------------------------ */

function tlsOver(socket, host, { timeoutMs = DIRECT_PROBE_TIMEOUT_MS } = {}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (fn, v) => {
      if (settled) return;
      settled = true;
      fn(v);
    };
    const tlsSock = tls.connect({ socket, servername: host, ALPNProtocols: ["h2"] });
    tlsSock.setTimeout(timeoutMs);
    tlsSock.on("secureConnect", () => {
      if (!tlsSock.authorized) {
        tlsSock.destroy();
        return finish(reject, tlsSock.authorizationError || new Error("TLS not authorized"));
      }
      // Same reasoning as connectDirect: the deadline bounds the handshake, not
      // the connection's lifetime. (This path never destroyed on timeout, so it
      // was already harmless -- cleared here so both egresses behave alike.)
      tlsSock.setTimeout(0);
      finish(resolve, tlsSock);
    });
    tlsSock.on("error", (e) => finish(reject, e));
    tlsSock.on("timeout", () => finish(reject, new Error("TLS handshake timeout")));
  });
}

function connectDirect(host, port, { timeoutMs = DIRECT_PROBE_TIMEOUT_MS, signal } = {}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (fn, v) => {
      if (settled) return;
      settled = true;
      fn(v);
    };
    const sock = tls.connect({ host, port, servername: host, ALPNProtocols: ["h2"] });
    sock.setTimeout(timeoutMs);
    sock.on("secureConnect", () => {
      if (!sock.authorized) {
        sock.destroy();
        return finish(reject, sock.authorizationError || new Error("TLS not authorized"));
      }
      // The deadline bounds the CONNECT, not the connection's lifetime. Leaving
      // it armed turned every >5s gap in the response stream -- exactly the
      // model's prefill between the response headers and the first token -- into
      // a destroy() of a live, healthy session, which surfaced as
      // "stream disconnected before completion".
      sock.setTimeout(0);
      finish(resolve, sock);
    });
    sock.on("error", (e) => finish(reject, e));
    sock.on("timeout", () => {
      if (settled) return;
      sock.destroy();
      finish(reject, new Error("direct connect timeout"));
    });
    if (signal) {
      if (signal.aborted) return finish(reject, new Error("aborted"));
      signal.addEventListener(
        "abort",
        () => {
          sock.destroy();
          finish(reject, new Error("aborted"));
        },
        { once: true },
      );
    }
  });
}

export function connectViaProxy(proxy, host, port, { timeoutMs = DIRECT_PROBE_TIMEOUT_MS, signal } = {}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (fn, v) => {
      if (settled) return;
      settled = true;
      fn(v);
    };
    const raw = net.connect({ host: proxy.hostname, port: Number(proxy.port) });
    raw.setTimeout(timeoutMs);
    raw.on("error", (e) => {
      raw.destroy();
      finish(reject, e);
    });
    raw.on("timeout", () => {
      raw.destroy();
      finish(reject, new Error("proxy connect timeout"));
    });
    if (signal) {
      if (signal.aborted) return finish(reject, new Error("aborted"));
      signal.addEventListener(
        "abort",
        () => {
          raw.destroy();
          finish(reject, new Error("aborted"));
        },
        { once: true },
      );
    }
    raw.on("connect", () => {
      let req = `CONNECT ${host}:${port} HTTP/1.1\r\nHost: ${host}:${port}\r\n`;
      if (proxy.username || proxy.password) {
        const token = Buffer.from(
          `${decodeURIComponent(proxy.username)}:${decodeURIComponent(proxy.password)}`,
        ).toString("base64");
        req += `Proxy-Authorization: Basic ${token}\r\n`;
      }
      req += "\r\n";
      raw.write(req);

      let buf = Buffer.alloc(0);
      const onData = (chunk) => {
        buf = Buffer.concat([buf, chunk]);
        const idx = buf.indexOf("\r\n\r\n");
        if (idx === -1) {
          if (buf.length > 8192) {
            raw.destroy();
            finish(reject, new Error("proxy CONNECT response too large"));
          }
          return;
        }
        raw.removeListener("data", onData);
        const statusLine = buf.slice(0, idx).toString("utf8").split("\r\n")[0];
        const m = statusLine.match(/HTTP\/1\.[01]\s+(\d{3})/);
        if (!m || Number(m[1]) < 200 || Number(m[1]) >= 300) {
          raw.destroy();
          return finish(reject, new Error(`proxy CONNECT failed: ${statusLine}`));
        }
        raw.setTimeout(0);
        tlsOver(raw, host, { timeoutMs }).then(
          (v) => finish(resolve, v),
          (e) => finish(reject, e),
        );
      };
      raw.on("data", onData);
    });
  });
}

// Remember which egress last worked so a poisoned-direct path doesn't cost a
// multi-second timeout on every single request.
let egress = { mode: null, until: 0 };

export async function establishSocket(host, port, { signal } = {}) {
  const now = Date.now();
  if (egress.mode === "proxy" && now < egress.until) {
    const proxy = detectProxy();
    if (proxy) {
      try {
        return await connectViaProxy(proxy, host, port, { signal });
      } catch {
        egress = { mode: null, until: 0 }; // proxy regressed; re-probe direct
      }
    } else {
      egress = { mode: null, until: 0 };
    }
  }

  try {
    const sock = await connectDirect(host, port, { signal });
    egress = { mode: "direct", until: Date.now() + DIRECT_HOLD_MS };
    return sock;
  } catch (directErr) {
    const proxy = detectProxy();
    if (!proxy) throw directErr;
    const sock = await connectViaProxy(proxy, host, port, { signal });
    egress = { mode: "proxy", until: Date.now() + PROXY_HOLD_MS };
    return sock;
  }
}

/* ----------------------------- h2 session ---------------------------- */

// One keep-alive h2 session per origin, recreated on close/goaway/error.
const sessions = new Map();
async function getSession(origin, { signal } = {}) {
  const cached = sessions.get(origin);
  if (cached && !cached.closed && !cached.destroyed) return cached;

  const host = new URL(origin).hostname;
  const socket = await establishSocket(host, 443, { signal });
  const session = http2.connect(origin, {
    ALPNProtocols: ["h2"],
    servername: host,
    createConnection: () => socket,
  });
  const entry = { session, closed: false, activeStreams: 0 };
  const onGone = () => {
    entry.closed = true;
    if (sessions.get(origin) === entry) sessions.delete(origin);
  };
  session.on("goaway", onGone);
  session.on("close", onGone);
  session.on("error", onGone);
  sessions.set(origin, entry);

  if (signal) {
    if (signal.aborted) session.close();
    else signal.addEventListener("abort", () => session.close(), { once: true });
  }
  return entry;
}

// A stream that dies before its response headers is indistinguishable from a
// half-dead keep-alive session: the socket never emitted goaway/close, so the
// cached entry above still looks usable and the next attempt would fail the
// same way. Drop it so the retry below dials a fresh connection.
function dropSession(origin) {
  const entry = sessions.get(origin);
  if (!entry) return;
  sessions.delete(origin);
  try {
    entry.session.destroy();
  } catch {
    /* already gone */
  }
}

// Forget the cached egress preference and retire pooled h2 sessions.
// Called when the Windows system proxy changes (see fetch-transport watcher):
// the held proxy/direct choice and any socket dialed through the old proxy
// must not be reused, so the next request re-probes and connects fresh.
//
// Sessions are closed gracefully, not destroyed: `session.close()` sends a
// GOAWAY and lets in-flight streams finish on their own, so a generation
// mid-stream is never cut. Entries are removed immediately so the next
// request dials a fresh connection. The optional `entries` parameter keeps
// the map injectable for tests.
export function drainStealthSessions(entries = sessions) {
  egress = { mode: null, until: 0 };
  for (const [origin, entry] of Array.from(entries.entries())) {
    entries.delete(origin);
    entry.closed = true;
    try {
      if (!entry.session.destroyed) entry.session.close();
    } catch {
      /* already gone */
    }
  }
}

// Only failures raised before the response headers can be replayed: the request
// body is a fully materialized Buffer and nothing has been relayed downstream
// yet. Anything after the headers belongs to the live body stream and must
// propagate unchanged, so only the two pre-header paths below are tagged.
function tagPreHeaderFailure(error) {
  const tagged = error instanceof Error ? error : new Error(String(error));
  tagged.retryableStealth = true;
  return tagged;
}

// Bounded retry for the pre-header failures above. Every attempt replays the
// identical headers and body, so a retry cannot change what leaves the machine
// -- it only gives a dead session another connection.
const STEALTH_MAX_ATTEMPTS = 3;
const STEALTH_RETRY_BACKOFF_MS = [200, 600];

async function forwardStealthOnce(origin, url, req, rawBody, { signal } = {}) {
  const entry = await getSession(origin, { signal });
  const session = entry.session;
  entry.activeStreams += 1;

  const headers = replayHeaders(req);
  headers[http2.constants.HTTP2_HEADER_METHOD] = http2.constants.HTTP2_METHOD_POST;
  headers[http2.constants.HTTP2_HEADER_PATH] = url.pathname + url.search;
  headers[http2.constants.HTTP2_HEADER_SCHEME] = url.protocol.replace(":", "");
  headers[http2.constants.HTTP2_HEADER_AUTHORITY] = url.host;

  const stream = session.request(headers, { endStream: false });
  if (signal) {
    if (signal.aborted) stream.close();
    else signal.addEventListener("abort", () => stream.close(), { once: true });
  }

  // Collect the response into a web ReadableStream.
  let responseHeaders;
  const head = new Promise((resolve, reject) => {
    stream.on("response", (h) => {
      responseHeaders = h;
      resolve();
    });
    stream.on("error", (error) => reject(tagPreHeaderFailure(error)));
    stream.on("close", () => {
      if (!responseHeaders) {
        reject(tagPreHeaderFailure(new Error("stealth h2 stream closed before response")));
      }
    });
  });

  let enqueue, finishBody;
  const bodyStream = new ReadableStream({
    start(controller) {
      const closed = () => controller.desiredSize === null;
      enqueue = (c) => {
        // A late h2 data frame can arrive after the controller already closed;
        // enqueue would then throw ERR_INVALID_STATE and fault the stream.
        if (closed()) return;
        try {
          controller.enqueue(c);
        } catch {
          /* already closed */
        }
      };
      finishBody = (error) => {
        try {
          if (error) controller.error(error);
          else controller.close();
        } catch {
          /* already closed */
        }
      };
    },
  });

  // Exactly one terminal event ends the body. `close` fires on every path --
  // normal end, RST, goaway, destroy -- so it is the single teardown point;
  // `end` and `error` are just the fast paths to the same finish. This keeps
  // the controller's lifecycle aligned with the stream's instead of only
  // closing on `end` and leaking on abnormal closes.
  let bodyDone = false;
  const finish = (error) => {
    if (bodyDone) return;
    bodyDone = true;
    entry.activeStreams -= 1;
    if (entry.closed && entry.activeStreams === 0 && sessions.get(origin) === entry) {
      sessions.delete(origin);
    }
    finishBody(error);
  };
  stream.on("data", (chunk) => enqueue(Buffer.from(chunk)));
  stream.on("end", () => finish());
  stream.on("error", (error) => finish(error));
  stream.on("close", () => finish());

  if (rawBody && rawBody.length) stream.write(rawBody);
  stream.end();

  await head;

  const out = new Headers();
  for (const [name, value] of Object.entries(responseHeaders)) {
    if (name.startsWith(":")) continue;
    if (Array.isArray(value)) for (const v of value) out.append(name, v);
    else out.set(name, value);
  }
  const status = Number(responseHeaders[http2.constants.HTTP2_HEADER_STATUS]) || 502;
  return new Response(bodyStream, { status, headers: out });
}

export async function forwardStealthNative(targetUrl, req, rawBody, { signal } = {}) {
  const url = new URL(targetUrl);
  const origin = url.origin;
  let lastError;

  for (let attempt = 1; attempt <= STEALTH_MAX_ATTEMPTS; attempt += 1) {
    try {
      return await forwardStealthOnce(origin, url, req, rawBody, { signal });
    } catch (error) {
      lastError = error;
      // A response body that already started streaming, an aborted request, or
      // a failure while dialing is not ours to replay: only the tagged
      // pre-header failures are.
      if (error?.retryableStealth !== true || signal?.aborted) throw error;
      if (attempt === STEALTH_MAX_ATTEMPTS) break;
      dropSession(origin);
      const delay =
        STEALTH_RETRY_BACKOFF_MS[Math.min(attempt - 1, STEALTH_RETRY_BACKOFF_MS.length - 1)];
      process.stderr.write(
        `[codex-router] stealth retry ${attempt}/${STEALTH_MAX_ATTEMPTS} after: ${error.message}\n`,
      );
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  throw lastError;
}
