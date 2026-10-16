// Run with: node --test telegram-worker/worker.test.mjs
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";

const env = { TELEGRAM_BOT_TOKEN: "123:abc", TELEGRAM_CHAT_ID: "42",
              GITHUB_TOKEN: "github_pat_x", WEBHOOK_SECRET: "s3cret" };
let calls, runsReply;

beforeEach(() => {
  calls = [];
  runsReply = { workflow_runs: [] };
  globalThis.fetch = async (url, opts = {}) => {
    calls.push({ url, method: opts.method || "GET", body: opts.body && JSON.parse(opts.body),
                 headers: opts.headers });
    if (url.includes("/dispatches")) return new Response(null, { status: 204 });
    if (url.includes("/runs")) return Response.json(runsReply);
    return Response.json({ ok: true, result: true });          // Telegram
  };
});

async function load() {             // fresh module = fresh double-tap memory
  return (await import(`./worker.js?${Math.random()}`)).default;
}

function update(text, chatId = 42, secret = "s3cret") {
  return new Request("https://w.example/", {
    method: "POST", body: JSON.stringify({ message: { chat: { id: chatId }, text } }),
    headers: { "X-Telegram-Bot-Api-Secret-Token": secret, "Content-Type": "application/json" },
  });
}
const sent = () => calls.filter((c) => c.url.includes("sendMessage")).map((c) => c.body.text);
const dispatches = () => calls.filter((c) => c.url.includes("/dispatches"));

test("rejects requests without Telegram's secret", async () => {
  const w = await load();
  assert.equal((await w.fetch(update("/search", 42, "wrong"), env)).status, 403);
  assert.equal(calls.length, 0);
});

test("ignores other people", async () => {
  const w = await load();
  const res = await w.fetch(update("/search", 999), env);
  assert.equal(res.status, 200);
  assert.equal(calls.length, 0);
});

test("/search starts a new-only run and confirms", async () => {
  const w = await load();
  await w.fetch(update("/search"), env);
  const [d] = dispatches();
  assert.deepEqual(d.body, { ref: "main", inputs: { source: "propertyguru", new_only: "true" } });
  assert.match(d.headers.Authorization, /^Bearer github_pat_x$/);
  assert.ok(d.headers["User-Agent"]);
  assert.match(sent()[0], /new or cheaper/);
});

test("/all resends everything", async () => {
  const w = await load();
  await w.fetch(update("/all@SGCondoBot"), env);
  assert.equal(dispatches()[0].body.inputs.new_only, "false");
});

test("double tap: no second run while one is running", async () => {
  const w = await load();
  runsReply = { workflow_runs: [{ status: "in_progress", created_at: "2026-10-16T03:11:52Z" }] };
  await w.fetch(update("/search"), env);
  assert.equal(dispatches().length, 0);
  assert.match(sent()[0], /already running/);
});

test("double tap: no second run just after starting one", async () => {
  const w = await load();
  await w.fetch(update("/search"), env);
  await w.fetch(update("/search"), env);            // GitHub doesn't list the run yet
  assert.equal(dispatches().length, 1);
  assert.match(sent()[1], /just started/);
});

test("/status lists runs and the next scheduled search", async () => {
  const w = await load();
  runsReply = { workflow_runs: [
    { status: "completed", conclusion: "success", created_at: "2026-10-16T03:11:52Z", html_url: "https://gh/1" },
    { status: "completed", conclusion: "failure", created_at: "2026-10-15T15:46:14Z", html_url: "https://gh/2" },
  ] };
  await w.fetch(update("/status"), env);
  const text = sent()[0];
  assert.match(text, /✅ ok · Fri 16 Oct, 11:11/);
  assert.match(text, /❌ failure/);
  assert.match(text, /Next scheduled search/);
});

test("unknown text gets the help message", async () => {
  const w = await load();
  await w.fetch(update("hello"), env);
  assert.match(sent()[0], /\/search/);
  assert.equal(dispatches().length, 0);
});

test("GitHub errors are reported in Telegram, not swallowed", async () => {
  const w = await load();
  globalThis.fetch = async (url, opts = {}) => {
    calls.push({ url, body: opts.body && JSON.parse(opts.body) });
    if (url.includes("github")) return new Response("{}", { status: 401 });
    return Response.json({ ok: true });
  };
  const res = await w.fetch(update("/search"), env);
  assert.equal(res.status, 200);
  assert.match(sent()[0], /401 \(GitHub token wrong or expired\)/);
});

test("/setup needs the key, then registers the webhook and menu", async () => {
  const w = await load();
  assert.equal((await w.fetch(new Request("https://w.example/setup?key=nope"), env)).status, 403);
  const res = await w.fetch(new Request("https://w.example/setup?key=s3cret"), env);
  assert.equal(res.status, 200);
  const hook = calls.find((c) => c.url.endsWith("/setWebhook")).body;
  assert.equal(hook.url, "https://w.example/");
  assert.equal(hook.secret_token, "s3cret");
  assert.ok(calls.some((c) => c.url.endsWith("/setMyCommands")));
});

test("next scheduled time", async () => {
  const { nextScheduled } = await import("./worker.js");
  // 11:20 SGT -> 19:47 same day; 20:00 SGT -> 07:47 next day
  assert.match(nextScheduled(new Date("2026-10-16T03:20:00Z")), /Fri 16 Oct, 19:47/);
  assert.match(nextScheduled(new Date("2026-10-16T12:00:00Z")), /Sat 17 Oct, 07:47/);
});
