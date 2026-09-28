// Unit tests for the stealth native forward's proxy discovery and CONNECT
// tunnel. Run via `node --test native-stealth-forward.test.mjs`, or through
// the pytest wrapper test_native_stealth.py.
import test from "node:test";
import assert from "node:assert/strict";
import net from "node:net";

import {
  proxyFromEnv,
  parseWinInetProxyServer,
  connectViaProxy,
} from "./vendor/native-stealth-forward.mjs";

test("proxyFromEnv prefers HTTPS_PROXY and accepts bare host:port", () => {
  const u = proxyFromEnv({ HTTPS_PROXY: "127.0.0.1:7897" });
  assert.equal(u.protocol, "http:");
  assert.equal(u.hostname, "127.0.0.1");
  assert.equal(u.port, "7897");
});

test("proxyFromEnv follows documented precedence", () => {
  const u = proxyFromEnv({
    HTTPS_PROXY: "http://a:1",
    https_proxy: "http://b:2",
    HTTP_PROXY: "http://c:3",
  });
  assert.equal(u.hostname, "a");
  assert.equal(u.port, "1");
});

test("proxyFromEnv ignores empty and SOCKS values", () => {
  assert.equal(proxyFromEnv({ HTTPS_PROXY: "", ALL_PROXY: "socks5://127.0.0.1:10808" }), null);
  const http = proxyFromEnv({ ALL_PROXY: "http://127.0.0.1:7897" });
  assert.equal(http.port, "7897");
});

test("parseWinInetProxyServer handles a single server value", () => {
  const u = parseWinInetProxyServer("127.0.0.1:7897;");
  assert.equal(u.href, "http://127.0.0.1:7897/");
});

test("parseWinInetProxyServer prefers the https entry of a per-protocol map", () => {
  const u = parseWinInetProxyServer(
    "http=127.0.0.1:7897;https=127.0.0.1:7898;",
  );
  assert.equal(u.port, "7898");
});

test("parseWinInetProxyServer falls back to http then generic", () => {
  assert.equal(parseWinInetProxyServer("http=127.0.0.1:7001;").port, "7001");
  assert.equal(parseWinInetProxyServer("garbage").href, "http://garbage/");
  assert.equal(parseWinInetProxyServer(""), null);
});

test("connectViaProxy sends a CONNECT line and surfaces proxy refusal", async () => {
  let received = "";
  const server = net.createServer((sock) => {
    sock.on("data", (chunk) => {
      received += chunk.toString();
      sock.write("HTTP/1.1 403 Forbidden\r\n\r\n");
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  await assert.rejects(
    connectViaProxy(new URL(`http://127.0.0.1:${port}`), "chatgpt.com", 443, {
      timeoutMs: 4000,
    }),
    /403/,
  );
  assert.match(received, /^CONNECT chatgpt\.com:443 HTTP\/1\.1/);
  server.close();
});
