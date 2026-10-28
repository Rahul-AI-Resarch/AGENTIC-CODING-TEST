/* BAA console front-end.
 *
 * Modes (auto-detected):
 *   1. LOCAL mode  — page served by `python -m baa.web` (same origin).
 *      Full control: start/resume builds, live ledger + log polling.
 *   2. LEDGER mode — static GitHub Pages deploy with runs/ledger.sample.json
 *      present next to it: read-only visualization of that run.
 *   3. DEMO mode   — bundled sample run so the UI always shows something.
 */
"use strict";

const PHASES = [
  { key: "A", label: "A · Spec" },
  { key: "B", label: "B · Decompose" },
  { key: "C", label: "C · Scaffold" },
  { key: "D", label: "D · Micro-loop" },
  { key: "E", label: "E · Integration gates" },
  { key: "F", label: "F · Ship" },
  { key: "DONE", label: "✓ Done" },
];
const PH_ORDER = ["A", "B", "C", "D", "E", "F", "DONE"];

const $ = (id) => document.getElementById(id);
let pollTimer = null;
let mode = "demo";

/* ------------------------------------------------------------------ utils */
function log(msg, cls) {
  const el = document.createElement("div");
  if (cls) el.className = cls;
  el.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  $("log").appendChild(el);
  $("log").scrollTop = $("log").scrollHeight;
}

async function getJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${url} → HTTP ${r.status}`);
  return r.json();
}

/* ------------------------------------------------------------------ render */
function renderStepper(phase) {
  const cur = PH_ORDER.indexOf(phase && phase.startsWith("E-") ? "E" : phase);
  $("stepper").innerHTML = PHASES.map((p, i) => {
    let cls = "ph";
    if (phase && (phase === "E-fail" || phase === "halted")) {
      if (i < cur) cls += " done";
      else if (i === Math.max(cur, 4)) cls += " fail";
    } else {
      if (i < cur) cls += " done";
      else if (i === cur) cls += cur === PH_ORDER.length - 1 ? " done" : " active";
    }
    return `<span class="${cls}">${p.label}</span>`;
  }).join("");
}

function renderLedger(ledger) {
  const cards = (ledger.cards || []).slice().sort(
    (a, b) => (LAYERIDX(a.layer) - LAYERIDX(b.layer)) || a.id.localeCompare(b.id));
  $("run-label").textContent = ledger.meta && ledger.meta.run_id ? `· ${ledger.meta.run_id}` : "";
  $("ledger-body").innerHTML = cards.map(c => `
    <tr class="card-row" data-cid="${esc(c.id)}">
      <td><span class="st st-${c.status}">${c.status}</span></td>
      <td class="cid" title="${esc(c.title)}">${esc(c.id)}</td>
      <td class="cid">${esc(c.layer)}</td>
      <td class="muted">${esc((c.acceptance || "").slice(0, 110))}</td>
      <td>${c.attempts}/${c.repairs}</td>
    </tr>
    ${c.test_source ? `<tr class="test-row hidden" data-for="${esc(c.id)}"><td colspan="5"><pre class="testsrc">${esc(c.test_source)}</pre></td></tr>` : ""}`).join("")
    || `<tr><td colspan="5" class="muted">no cards yet</td></tr>`;

  // click a card row to toggle its acceptance test source (Kimi-style: every feature shows its test)
  $("ledger-body").querySelectorAll(".card-row").forEach(row => {
    if (!row.nextElementSibling || !row.nextElementSibling.classList.contains("test-row")) return;
    row.style.cursor = "pointer";
    row.title = "click to show/hide this card's acceptance test";
    row.addEventListener("click", () => row.nextElementSibling.classList.toggle("hidden"));
  });

  const n = (s) => cards.filter(c => c.status === s).length;
  $("s-pass").textContent = n("pass") + n("patched");
  $("s-patch").textContent = n("patched");
  $("s-quar").textContent = n("quarantined") + n("failed");
  $("s-pend").textContent = n("pending") + n("in_progress");

  renderStepper(ledger.meta && ledger.meta.phase);
  const note = ledger.meta && (ledger.meta.halt_reason || ledger.meta.final_html);
  $("phase-note").textContent = note
    ? (ledger.meta.halt_reason ? `⚠ ${ledger.meta.halt_reason}` : `shipped → ${note}`)
    : `phase ${(ledger.meta && ledger.meta.phase) || "?"} · ${cards.length} cards`;
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g,
    ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}
function LAYERIDX(l) {
  const order = ["L0-engine","L1-physics","L2-entities","L3-systems",
                 "L4-mechanics","L5-ui","L6-content","L7-feel"];
  const i = order.indexOf(l);
  return i === -1 ? 99 : i;
}

/* ------------------------------------------------------------------ modes */
async function detectMode() {
  // local server? probe our own API
  try {
    const st = await getJSON("api/status");
    if (st && st.agent === "baa") return setupLocal(st);
  } catch (e) { /* not local */ }
  // bundled ledger on pages?
  try {
    const led = await getJSON("runs/ledger.sample.json");
    $("mode-badge").textContent = "ledger view";
    log("Loaded runs/ledger.sample.json (read-only). Use 'Load demo run' for the walkthrough.");
    renderLedger(led);
    return "ledger";
  } catch (e) { /* fall through */ }
  $("mode-badge").textContent = "demo mode";
  loadDemo();
  return "demo";
}

function setupLocal(st) {
  mode = "local";
  $("mode-badge").textContent = "● connected (local agent)";
  $("btn-build").disabled = false;
  $("btn-resume").disabled = false;
  log(`Connected to BAA agent. provider=${st.provider} model=${st.model}`);
  if (st.current_run) { renderLedger(st.current_run); startPolling(); }
  else log("Agent idle — enter a prompt and press Build.");
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(async () => {
    try {
      const st = await getJSON("api/status");
      if (st.current_run) renderLedger(st.current_run);
      if (st.log) showServerLog(st.log);
      if (!st.running) {
        stopPolling();
        $("btn-stop").classList.add("hidden");
        $("btn-build").disabled = false;
        log(st.last_phase === "DONE" ? "Run finished — ship complete." : "Run stopped.", 
            st.last_phase === "DONE" ? "ok" : "warn");
      }
    } catch (e) { stopPolling(); log("Lost connection to agent.", "err"); }
  }, 2000);
}
function stopPolling() { if (pollTimer) clearInterval(pollTimer); pollTimer = null; }

let lastLogLen = 0;
function showServerLog(lines) {
  for (let i = lastLogLen; i < lines.length; i++) {
    const l = lines[i];
    log(l, l.includes("PASS") ? "ok" : (l.includes("QUARANTINED") || l.includes("FAIL") ? "err" : null));
  }
  lastLogLen = lines.length;
}

/* ------------------------------------------------------------------ actions */
async function startBuild(resume) {
  const body = {
    prompt: $("prompt").value.trim(),
    provider: $("provider").value,
    model: $("model").value.trim() || undefined,
    api_key: $("apikey").value.trim() || undefined,   // sent only to localhost agent
  };
  if (resume) body.resume = true;
  if (!body.prompt && !resume) { log("Enter a build prompt first.", "warn"); return; }
  try {
    const res = await getJSON("api/build", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    log(resume ? `Resuming run ${res.run_id}…` : `Started run ${res.run_id}…`, "ok");
    $("btn-stop").classList.remove("hidden");
    $("btn-build").disabled = true;
    startPolling();
  } catch (e) { log(`Build request failed: ${e.message}`, "err"); }
}

async function stopBuild() {
  try { await getJSON("api/stop", { method: "POST" }); log("Stop requested.", "warn"); }
  catch (e) { log(e.message, "err"); }
}

function loadDemo() {
  mode = "demo";
  $("mode-badge").textContent = "demo mode";
  renderLedger(DEMO_LEDGER);
  log("Demo run loaded — this is what a real run's ledger looks like mid Phase D.");
}

function loadGamePreview() {
  let url = $("game-url").value.trim();
  if (!url) url = location.pathname.replace(/index\.html$/, "") + "runs/demo-game/index.html";
  const fr = $("gameframe");
  fr.src = url;
  fr.classList.remove("hidden");
  log(`Preview loading: ${url}`);
}

/* ------------------------------------------------------------------ demo data */
const DEMO_LEDGER = {
  meta: { run_id: "windward-trader-demo", phase: "D" },
  cards: [
    { id: "scene-rig",        layer: "L0-engine",   status: "pass",       attempts: 1, repairs: 0, title: "three.js scene + camera rig", acceptance: "Renderer boots, follow-camera updates per frame, zero console errors." },
    { id: "input-map",        layer: "L0-engine",   status: "pass",       attempts: 1, repairs: 0, title: "keyboard/mouse input map",     acceptance: "WASD + mouse events dispatch into state; no dead keys." },
    { id: "fixed-timestep",   layer: "L0-engine",   status: "patched",    attempts: 2, repairs: 1, title: "fixed timestep loop",          acceptance: "Physics steps at 60Hz regardless of FPS; spiral-of-death guard." },
    { id: "hull-body",        layer: "L1-physics",  status: "pass",       attempts: 1, repairs: 0, title: "rigid hull body",              acceptance: "Mass/inertia sane; no NaN in velocity after 600 frames." },
    { id: "buoyancy",         layer: "L1-physics",  status: "pass",       attempts: 2, repairs: 0, title: "water buoyancy + drag",        acceptance: "Boat settles at waterline within 3s; drift decays." },
    { id: "wind-model",       layer: "L3-systems",  status: "in_progress",attempts: 1, repairs: 0, title: "global wind field",            acceptance: "Apparent-wind vector updates when heading changes; gust variance bounded." },
    { id: "sail-trim",        layer: "L4-mechanics",status: "pending",    attempts: 0, repairs: 0, title: "sail trim + tack penalty",     acceptance: "Beat-to-wind loses speed; reach gains max thrust." },
    { id: "hud-gauges",       layer: "L5-ui",       status: "pending",    attempts: 0, repairs: 0, title: "compass/speed/wind HUD",       acceptance: "HUD ids exist; values mirror state each frame." },
    { id: "islands",          layer: "L6-content",  status: "pending",    attempts: 0, repairs: 0, title: "procedural islands + routes",  acceptance: "≥8 islands seeded deterministically; trade route graph connected." },
    { id: "wake-fx",          layer: "L7-feel",     status: "pending",    attempts: 0, repairs: 0, title: "wake particles + water shader",acceptance: "Particle pool recycled; frame cost < 1.5ms." },
  ],
};

/* ------------------------------------------------------------------ boot */
$("btn-build").addEventListener("click", () => startBuild(false));
$("btn-resume").addEventListener("click", () => startBuild(true));
$("btn-stop").addEventListener("click", stopBuild);
$("btn-demo").addEventListener("click", loadDemo);
$("btn-load-game").addEventListener("click", loadGamePreview);
if (mode !== "local") $("btn-build").disabled = true;
detectMode().then(m => { if (m !== "local") $("btn-build").disabled = true; });
