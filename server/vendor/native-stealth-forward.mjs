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
// The TLS ClientHello is still Node's (that last fingerprint cannot change
// without a different TLS stack), but every header/body/ALPN discrepancy the
// earlier capture found is removed.
import http2 from "node:http2";

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

// One keep-alive h2 session per origin, recreated on close/goaway/error.
const sessions = new Map();
function getSession(origin, { signal } = {}) {
  const cached = sessions.get(origin);
  if (cached && !cached.closed && !cached.destroyed) return cached.session;

  const session = http2.connect(origin, {
    ALPNProtocols: ["h2"],
    servername: new URL(origin).hostname,
  });
  const entry = { session, closed: false };
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
  return session;
}

export async function forwardStealthNative(targetUrl, req, rawBody, { signal } = {}) {
  const url = new URL(targetUrl);
  const origin = url.origin;
  const session = getSession(origin, { signal });

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
    stream.on("error", reject);
    stream.on("close", () => {
      if (!responseHeaders) reject(new Error("stealth h2 stream closed before response"));
    });
  });

  let enqueue, closeStream, fail;
  const bodyStream = new ReadableStream({
    start(controller) {
      enqueue = (c) => controller.enqueue(c);
      closeStream = () => {
        try { controller.close(); } catch { /* already closed */ }
      };
      fail = (e) => {
        try { controller.error(e); } catch { /* already closed */ }
      };
    },
  });

  stream.on("data", (chunk) => enqueue(Buffer.from(chunk)));
  stream.on("end", closeStream);
  stream.on("error", fail);

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
