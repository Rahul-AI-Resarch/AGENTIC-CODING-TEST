/* BAA app glue — wires UI to the in-browser Conductor. No server needed. */

const $ = (id) => document.getElementById(id);
const PHASES = ["spec", "decompose", "scaffold", "microloop", "gates", "ship"];
const EXAMPLES = [
  "an original top-down arcade maze-chase game: pellets, 4 patrolling ghosts, power-up that flips the chase for 6 seconds, lives + score HUD",
  "a falling-block tile-matching game with rotation, line clears, next-piece preview and rising speed levels",
  "an original 3D wind-sailing trader: procedural ocean, sail trim vs wind, tacking, a harbor town, cargo runs, day/night cycle (three.js)",
  "a side-scrolling platformer with double jump, moving platforms, coins and a checkpoint system"
];

let cfg = loadCfg();
let llm = null, conductor = null, running = false;

function loadCfg() {
  try { return JSON.parse(localStorage.getItem("baa-cfg") || "{}"); } catch (e) { return {}; }
}
function saveCfg(c) { localStorage.setItem("baa-cfg", JSON.stringify(c)); }

function refreshPill() {
  const p = $("providerPill");
  if (cfg.apiKey) {
    p.textContent = (PROVIDERS[cfg.provider] ? PROVIDERS[cfg.provider].label : cfg.provider) + " · " + (cfg.model || "");
    p.style.borderColor = "var(--acc)"; p.style.color = "var(--acc)";
  } else { p.textContent = "no key set"; p.style.borderColor = ""; p.style.color = ""; }
}

/* ---------- settings dialog ---------- */
(function initSettings() {
  const sel = $("setProvider");
  for (const k of Object.keys(PROVIDERS)) {
    const o = document.createElement("option"); o.value = k; o.textContent = PROVIDERS[k].label; sel.appendChild(o);
  }
  sel.onchange = () => {
    const compat = sel.value === "openai-compatible";
    $("lblBase").style.display = compat ? "block" : "none";
    $("setBase").style.display = compat ? "block" : "none";
    if (!$("setModel").value && PROVIDERS[sel.value]) $("setModel").placeholder = PROVIDERS[sel.value].model;
  };
  $("openSettings").onclick = () => {
    sel.value = cfg.provider || "openai";
    $("setModel").value = cfg.model || "";
    $("setBase").value = cfg.baseUrl || "";
    $("setKey").value = cfg.apiKey || "";
    sel.onchange();
    $("settingsDlg").showModal();
  };
  $("closeSettings").onclick = () => $("settingsDlg").close();
  $("saveSettings").onclick = () => {
    cfg = {
      provider: sel.value,
      model: $("setModel").value.trim() || PROVIDERS[sel.value].model,
      baseUrl: sel.value === "openai-compatible" ? $("setBase").value.trim() : undefined,
      apiKey: $("setKey").value.trim()
    };
    saveCfg(cfg); refreshPill(); $("settingsDlg").close();
    logLine("ok", "BYOK saved: " + PROVIDERS[cfg.provider].label + " / " + cfg.model);
  };
})();

/* ---------- phase bar + ledger rendering ---------- */
(function initPhaseBar() {
  const bar = $("phaseBar");
  PHASES.forEach(p => { const d = document.createElement("div"); d.className = "ph"; d.id = "ph-" + p; d.textContent = p; bar.appendChild(d); });
})();

function setPhaseUI(p) {
  const idx = PHASES.indexOf(p);
  PHASES.forEach((x, i) => {
    const el = $("ph-" + x);
    el.className = "ph" + (i < idx ? " done" : i === idx ? " active" : "");
  });
}

function renderLedger() {
  const tb = $("ledger");
  if (!conductor || !conductor.cards.length) return;
  tb.innerHTML = "";
  let pass = 0, quar = 0;
  conductor.cards.forEach((c, i) => {
    if (c.status === "PASS") pass++;
    if (c.status === "QUARANTINED") quar++;
    const tr = document.createElement("tr");
    tr.className = "card-row";
    tr.innerHTML = "<td><b>" + c.layer + "</b></td><td>" + esc(c.name) +
      "<div style='color:var(--dim);font-size:11px'>" + esc(c.description).slice(0, 90) + "</div></td>" +
      "<td><span class='badge " + c.status + "'>" + c.status + "</span></td><td>" + (c.attempts || 0) + "</td>";
    tr.onclick = () => toggleTest(tr, i, c);
    tb.appendChild(tr);
  });
  $("stCards").textContent = conductor.cards.length;
  $("stPass").textContent = pass;
  $("stQuar").textContent = quar;
  $("stTok").textContent = llm ? llm.usage.calls : 0;
}

function toggleTest(tr, i, c) {
  const nx = tr.nextElementSibling;
  if (nx && nx.classList.contains("test-row")) { nx.remove(); return; }
  const row = document.createElement("tr");
  row.className = "test-row";
  const td = document.createElement("td");
  td.colSpan = 4;
  const pre = document.createElement("code");
  pre.className = "t";
  pre.textContent = c.test_src ? c.test_src : "(no acceptance test generated — quarantined before test-first step)\n" + (c.error || "");
  td.appendChild(pre); row.appendChild(td);
  tr.after(row);
}

function esc(s) { const d = document.createElement("div"); d.textContent = String(s || ""); return d.innerHTML; }

const logBox = $("logBox");
function logLine(cls, msg) {
  const d = document.createElement("div");
  if (cls) d.className = cls;
  d.textContent = new Date().toLocaleTimeString() + "  " + msg;
  logBox.appendChild(d); logBox.scrollTop = logBox.scrollHeight;
}

conductorHooks();
function conductorHooks() { /* placeholder for symmetry; wiring happens per-run */ }

/* ---------- build flow ---------- */
$("examples").innerHTML = "";
EXAMPLES.forEach(ex => {
  const s = document.createElement("span");
  s.textContent = ex.length > 46 ? ex.slice(0, 46) + "…" : ex;
  s.title = ex;
  s.onclick = () => { $("prompt").value = ex; };
  $("examples").appendChild(s);
});

$("buildBtn").onclick = async () => {
  const prompt = $("prompt").value.trim();
  if (!prompt) { logLine("er", "describe the game first"); return; }
  if (!cfg.apiKey) { $("settingsDlg").showModal(); logLine("er", "set your API key first (BYOK)"); return; }
  running = true;
  $("buildBtn").disabled = true; $("stopBtn").style.display = "block";
  logBox.innerHTML = "";
  llm = new LLM(cfg);
  conductor = new Conductor(llm, { maxImplTries: 3, maxRepairs: 2 });
  conductor.runner = makeRunner(25000);
  conductor.state = makeRunState(prompt);
  conductor.onEvent = (type, msg) => {
    if (type === "phase") { setPhaseUI(msg); logLine("ph-l", "▶ phase: " + msg); }
    else if (type === "pass" || type === "gate-pass") logLine("ok", "✓ " + msg);
    else if (type === "fail" || type === "quarantine" || type === "gate-fail" || type === "gate-quarantine") logLine("er", "✗ " + msg);
    else if (type === "card") { markRunning(msg); logLine("", "· card: " + msg); }
    else logLine("", msg);
    renderLedger();
  };
  renderLedger();
  try {
    const html = await conductor.run(prompt);
    ship(html);
    setPhaseUI("done-all");
    PHASES.forEach(x => $("ph-" + x).className = "ph done");
    logLine("ok", "★ shipped — live preview updated");
  } catch (e) {
    logLine("er", "run halted: " + e.message);
    if (conductor.html && conductor.finished !== true && conductor.cards.some(c => c.status === "PASS")) {
      ship(conductor.html); logLine("", "partial build shipped for review");
    }
  } finally {
    running = false;
    $("buildBtn").disabled = false; $("stopBtn").style.display = "none";
  }
};

function markRunning(cardId) {
  if (!conductor) return;
  const c = conductor.cards.find(x => x.id === cardId);
  if (c && c.status === "PENDING") c.status = "RUNNING";
  renderLedger();
}

$("stopBtn").onclick = () => { if (conductor) conductor.abort(); };

/* localStorage-backed run state so a closed tab can resume passed cards */
function makeRunState(prompt) {
  const key = "baa-run-" + btoa(unescape(encodeURIComponent(prompt)).slice(0, 40));
  return {
    persist(c) {
      try {
        localStorage.setItem(key, JSON.stringify({
          prompt, spec: c.spec, html: c.html, scaffold: c.scaffold,
          cards: c.cards.map(x => ({ id:x.id, layer:x.layer, name:x.name, description:x.description,
            status:x.status, attempts:x.attempts, repairs:x.repairs, test_src:x.test_src, error:x.error }))
        }));
      } catch (e) {}
    },
    restore() {
      try {
        const s = JSON.parse(localStorage.getItem(key) || "null");
        if (!s || s.prompt !== prompt) return null;
        return { spec: s.spec, html: s.html, scaffold: s.scaffold,
          cards: s.cards.map(x => ({ ...x, test_fn: x.test_src ? extractFn(x.test_src).fn : null })) };
      } catch (e) { return null; }
    }
  };
}

function ship(html) {
  const name = conductor && conductor.spec ? conductor.spec.title : "game";
  $("prevName").textContent = name;
  const blobUrl = URL.createObjectURL(new Blob([html], { type: "text/html" }));
  $("prevFrame").src = blobUrl;
  $("openTab").hidden = false; $("openTab").href = blobUrl; $("openTab").target = "_blank";
  $("downloadHtml").hidden = false; $("downloadHtml").href = blobUrl;
  $("downloadHtml").download = name.toLowerCase().replace(/[^a-z0-9]+/g, "-") + ".html";
  // persist last build so it survives reload
  try { localStorage.setItem("baa-last", JSON.stringify({ name, html, when: Date.now() })); } catch (e) {}
}

/* restore last shipped build on load */
try {
  const last = JSON.parse(localStorage.getItem("baa-last") || "null");
  if (last && last.html) {
    const blobUrl = URL.createObjectURL(new Blob([last.html], { type: "text/html" }));
    $("prevFrame").src = blobUrl; $("prevName").textContent = last.name + " (last run)";
    $("openTab").hidden = false; $("openTab").href = blobUrl; $("openTab").target = "_blank";
    $("downloadHtml").hidden = false; $("downloadHtml").href = blobUrl;
  }
} catch (e) {}

refreshPill();
if (!cfg.apiKey) setTimeout(() => $("settingsDlg").showModal(), 400);
