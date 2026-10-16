/**
 * Telegram commands for the SG condo shortlist, as a Cloudflare Worker.
 *
 *   /search  run now, only listings new or cheaper since the last alert
 *   /all     run now, resend every current match
 *   /status  last runs and the next scheduled one
 *
 * Telegram sends each message to this Worker (a "webhook"). The Worker starts
 * the GitHub workflow through the same "run workflow" API that cron-job.org uses.
 *
 * Secrets (Cloudflare: Worker > Settings > Variables and Secrets):
 *   TELEGRAM_BOT_TOKEN  the bot token from @BotFather
 *   TELEGRAM_CHAT_ID    your own chat ID: messages from anyone else are ignored
 *   GITHUB_TOKEN        fine-grained token, this repo only, Actions: read and write
 *   WEBHOOK_SECRET      any random string (letters, digits, _ and -); proves a
 *                       request really comes from Telegram
 *
 * One-off setup: open https://<your-worker-url>/setup?key=<WEBHOOK_SECRET>
 */

const REPO = "bi2ly/sg-rental-shortlister";
const WORKFLOW = "daily-shortlist.yml";
const SCHEDULE_SGT = [[7, 47], [19, 47]];        // cron-job.org times
const ACTIVE = ["queued", "in_progress", "waiting", "pending", "requested"];
const GUARD_MS = 90_000;   // a run may take a few seconds to appear on GitHub

let lastDispatch = 0;      // best-effort double-tap guard within one Worker instance

const COMMANDS = [
  { command: "search", description: "Search now: new or cheaper listings only" },
  { command: "all", description: "Search now: resend every current match" },
  { command: "status", description: "Last runs and next scheduled run" },
];

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/setup") return setup(url, env);
    if (request.method !== "POST") return new Response("Not found", { status: 404 });
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("Forbidden", { status: 403 });
    }
    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("ok");
    }
    const msg = update.message;
    if (!msg || String(msg.chat?.id) !== String(env.TELEGRAM_CHAT_ID).trim()) {
      return new Response("ok");              // not you: ignore silently
    }
    const cmd = (msg.text || "").trim().split(/\s+/)[0].split("@")[0].toLowerCase();
    let reply;
    try {
      if (cmd === "/search") reply = await search(env, true);
      else if (cmd === "/all") reply = await search(env, false);
      else if (cmd === "/status") reply = await status(env);
      else reply = help();
    } catch (e) {
      reply = `⚠️ Something went wrong: ${escapeHtml(e.message)}`;
    }
    await telegram(env, "sendMessage", {
      chat_id: env.TELEGRAM_CHAT_ID, text: reply, parse_mode: "HTML",
      disable_web_page_preview: true,
    });
    return new Response("ok");                // always 200, or Telegram retries
  },
};

function help() {
  return "🏠 <b>Condo shortlist</b>\n\n" +
    "/search: search now, new or cheaper listings only\n" +
    "/all: search now, resend every current match\n" +
    "/status: last runs and the next scheduled one\n\n" +
    "Scheduled searches run at 07:47 and 19:47.";
}

async function search(env, newOnly) {
  const runs = await github(env, `/actions/workflows/${WORKFLOW}/runs?per_page=5`);
  const running = (runs.workflow_runs || []).find((r) => ACTIVE.includes(r.status));
  if (running) {
    return `⏳ A search is already running (started ${sgTime(running.created_at)}). ` +
      "Results will arrive here shortly.";
  }
  if (Date.now() - lastDispatch < GUARD_MS) {
    return "⏳ A search was just started. Results will arrive here shortly.";
  }
  await github(env, `/actions/workflows/${WORKFLOW}/dispatches`, {
    ref: "main", inputs: { source: "propertyguru", new_only: String(newOnly) },
  });
  lastDispatch = Date.now();
  return newOnly
    ? "🔎 Searching for new or cheaper listings… results in about 5 minutes."
    : "🔎 Searching all current matches… results in about 5 minutes.";
}

async function status(env) {
  const runs = (await github(env, `/actions/workflows/${WORKFLOW}/runs?per_page=3`)).workflow_runs || [];
  const lines = ["📊 <b>Status</b>"];
  if (!runs.length) lines.push("No runs yet.");
  for (const r of runs) {
    const state = ACTIVE.includes(r.status) ? "⏳ running"
      : r.conclusion === "success" ? "✅ ok" : `❌ ${r.conclusion || r.status}`;
    lines.push(`${state} · ${sgTime(r.created_at)} · <a href="${r.html_url}">details</a>`);
  }
  lines.push(`\nNext scheduled search: ${nextScheduled(new Date())}`);
  return lines.join("\n");
}

// --- helpers -------------------------------------------------------------------

async function github(env, path, body) {
  const res = await fetch(`https://api.github.com/repos/${REPO}${path}`, {
    method: body ? "POST" : "GET",
    headers: {
      Authorization: `Bearer ${String(env.GITHUB_TOKEN).trim()}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "sg-rental-shortlister-telegram",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const hint = res.status === 401 ? " (GitHub token wrong or expired)"
      : res.status === 403 || res.status === 404 ? " (token needs Actions: read and write on this repo)" : "";
    throw new Error(`GitHub replied ${res.status}${hint}`);
  }
  return res.status === 204 ? {} : res.json();
}

async function telegram(env, method, payload) {
  const res = await fetch(`https://api.telegram.org/bot${String(env.TELEGRAM_BOT_TOKEN).trim()}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

async function setup(url, env) {
  if (!env.WEBHOOK_SECRET || url.searchParams.get("key") !== env.WEBHOOK_SECRET) {
    return new Response("Wrong or missing key.", { status: 403 });
  }
  const hook = await telegram(env, "setWebhook", {
    url: `${url.origin}/`, secret_token: env.WEBHOOK_SECRET,
    allowed_updates: ["message"], drop_pending_updates: true,
  });
  const menu = await telegram(env, "setMyCommands", { commands: COMMANDS });
  const ok = hook.ok && menu.ok;
  const text = ok
    ? "✅ Done: your bot now sends commands to this Worker. Send /status to the bot to test."
    : `❌ Telegram said: ${hook.description || menu.description || "unknown error"}. ` +
      "Check TELEGRAM_BOT_TOKEN.";
  return new Response(text, { status: ok ? 200 : 500,
    headers: { "Content-Type": "text/plain; charset=utf-8" } });
}

function sgTime(iso) {
  return new Date(iso).toLocaleString("en-GB", {
    timeZone: "Asia/Singapore", weekday: "short", day: "numeric", month: "short",
    hour: "2-digit", minute: "2-digit",
  });
}

export function nextScheduled(now) {
  const sg = new Date(now.getTime() + 8 * 3600_000);           // Singapore wall clock
  for (let d = 0; d < 2; d++) {
    for (const [h, m] of SCHEDULE_SGT) {
      const t = Date.UTC(sg.getUTCFullYear(), sg.getUTCMonth(), sg.getUTCDate() + d, h, m) - 8 * 3600_000;
      if (t > now.getTime()) return sgTime(new Date(t).toISOString());
    }
  }
  return "unknown";
}

function escapeHtml(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);
}
