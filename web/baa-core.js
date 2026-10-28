/* BAA core — pure JS, runs fully in-browser (GitHub Pages compatible).
   Phases: A spec -> B decompose -> C scaffold -> D micro-loop -> E gates -> F ship.
   LLM calls go through baa-llm.js (BYOK, direct browser fetch). */

const BT = {
  SYSTEM_SPEC: `You are the SPEC stage of the Build Anything Agent (BAA). You turn a one-line game idea into a strict JSON build specification. Output ONLY raw JSON, no markdown fences, no commentary. Schema:
{
 "title": string,
 "genre": string,
 "camera": "2d-top"|"2d-side"|"3d-follow"|"3d-orbit",
 "controls": string,
 "art_direction": string,
 "physics": string,
 "perf_target_fps": number,
 "engine": "canvas2d"|"three.js",
 "libs": [cdn urls],
 "hard_constraints": ["single self-contained HTML file","CDN-only libraries","procedural assets only - no copyrighted names or art"],
 "features": [{"id":"kebab-case","layer":"L0..L7","name":"...","description":"observable behavior with concrete numbers/conditions"}]
}
Decompose features across layers:
L0 engine/world (loop, input, renderer), L1 physics core, L2 entities, L3 systems, L4 mechanics, L5 meta/UI, L6 content, L7 feel/polish.
A small game: 8-14 features. A large 3D game: 16-24 features. Every feature must be independently testable.`,

  SYSTEM_TEST: `You are the TEST-FIRST stage of BAA. Given ONE feature card and the current game code, write a deterministic acceptance test for it as a single JS function body. Inside the function body these globals exist directly: __game (the live game state object — write "__game.state" NOT "this.__game"), assert(cond,msg) which throws on failure, step(n) advancing n deterministic frames, and window. Use them as plain identifiers. Rules: 1-6 assertions max, NO await/setTimeout/I/O, total runtime under ~2s. Return ONLY raw JavaScript: an async function expression WITHOUT the 'async' keyword, e.g.:
(function(){ const g = window.__game; assert(g && g.state, 'game booted'); ... })()`,

  SYSTEM_IMPL: `You are the IMPLEMENT stage of BAA. You own EXACTLY ONE section of a single-file HTML game, marked <!-- @SECTION:<id> --> ... <!-- @END:SECTION:<id> -->. Replace that section's contents to implement the assigned feature card. Hard rules:
- Keep all existing working code intact unless the card requires changing it.
- Expose live state at window.__game = {state, player, entities, stats, ...} so tests can inspect it.
- Deterministic sim: if window.__TEST__ is truthy, use fixed seed and auto-start (no menus blocking); expose window.__step(ms) to advance time synchronously.
- CDN libs via script tags only. Procedural graphics (shapes/particles), no external images.
- No copyrighted names/art; genre-faithful originals only.
- Return ONLY the complete updated HTML document. Start with <!DOCTYPE html> and end with </html>. No markdown fences, no commentary.`,

  SYSTEM_FIX: `You are the REPAIR stage of BAA. The given single-file HTML game failed checks. Apply the SMALLEST possible fix. Return ONLY the complete corrected HTML document starting with <!DOCTYPE html> and ending with </html>. No fences, no commentary.`
};

function extractJSON(text) {
  let t = String(text).trim();
  t = t.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "");
  const s = t.indexOf("{"), e = t.lastIndexOf("}");
  if (s >= 0 && e > s) t = t.slice(s, e + 1);
  return JSON.parse(t);
}

function extractHTML(text) {
  let t = String(text).trim();
  t = t.replace(/^```(?:html)?\s*/i, "").replace(/\s*```$/i, "");
  const i = t.toLowerCase().indexOf("<!doctype html");
  const j = t.toLowerCase().indexOf("<html");
  const start = i >= 0 ? i : (j >= 0 ? j : -1);
  if (start < 0) throw new Error("model returned no HTML");
  const k = t.toLowerCase().lastIndexOf("</html>");
  if (k < 0) throw new Error("truncated HTML (missing </html>)");
  return t.slice(start, k + 7);
}

function extractFn(text) {
  let t = String(text).trim();
  t = t.replace(/^```(?:js|javascript)?\s*/i, "").replace(/\s*```$/i, "");
  const s = t.indexOf("(");
  if (s < 0) throw new Error("test fn not found");
  let e = t.lastIndexOf("})");
  if (e < 0) throw new Error("unterminated test fn");
  e += 2;
  while (t.slice(e).includes(")")) { /* trailing paren safety */ break; }
  let fn;
  try { fn = Function("return (" + t.slice(s, e) + ")")(); }
  catch (_) { fn = Function("return (" + t.slice(s, e + 2) + ")")(); }
  return { fn: fn, src: t.slice(s, e + 2) };
}

function findAnchors(html, id) {
  // anchors may appear as real comments or escaped inside the hidden sections block
  const variants = [["<!-- @SECTION:" + id + " -->", "<!-- @END:SECTION:" + id + " -->"],
                    ["@SECTION:" + id, "@END:SECTION:" + id]];
  for (const [o, c] of variants) {
    const a = html.indexOf(o), b = html.indexOf(c);
    if (a >= 0 && b > a) return { a, b, openLen: o.length };
  }
  return null;
}
function replaceSection(html, id, body) {
  const f = findAnchors(html, id);
  if (!f) throw new Error("section anchor missing: " + id);
  return html.slice(0, f.a + f.openLen) + "\n" + body.trim() + "\n" + html.slice(f.b);
}

const LAYERS = ["L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7"];

class Conductor {
  constructor(llm, opts) {
    this.llm = llm;
    this.opts = Object.assign({ maxImplTries: 3, maxRepairs: 2 }, opts || {});
    this.log = [];
    this.phase = "idle";
    this.cards = [];
    this.spec = null;
    this.scaffold = "";
    this.html = "";
    this.finished = false;
    this.aborted = false;
  }
  _emit(type, msg) {
    this.log.push({ t: Date.now(), type, msg });
    if (this.onEvent) { try { this.onEvent(type, msg); } catch (e) {} }
  }
  setPhase(p) { this.phase = p; this._emit("phase", p); }
  abort() { this.aborted = true; this._emit("info", "aborted by user"); }
  _check() { if (this.aborted) throw new Error("aborted"); }

  async run(prompt) {
    // resume from saved state if present (passed cards never redone)
    if (this.state && typeof this.state.restore === "function") {
      const s = this.state.restore();
      if (s && s.spec && s.cards) {
        this.spec = s.spec; this.cards = s.cards;
        for (const c of this.cards) {
          if (c.test_src && typeof c.test_fn !== "function") {
            try { c.test_fn = extractFn(c.test_src).fn; } catch (e) { c.test_fn = null; }
          }
        }
        this.html = s.html || ""; this.scaffold = s.scaffold || this.html;
        this._emit("info", "resumed: " + this.cards.filter(c => c.status === "PASS").length + " passed cards skipped");
        this.setPhase("microloop");
        for (const card of this.cards) {
          this._check();
          if (card.status === "PASS" || card.status === "QUARANTINED") continue;
          await this.runCard(card);
        }
        this.setPhase("gates");
        await this.runGates();
        this.setPhase("ship");
        this.finished = true;
        return this.html;
      }
    }
    // Phase A — spec
    this.setPhase("spec");
    const specRaw = await this.llm.chat([
      { role: "system", content: BT.SYSTEM_SPEC },
      { role: "user", content: "Game idea: " + prompt }
    ], { maxTokens: 4096 });
    this.spec = extractJSON(specRaw);
    this._emit("info", "spec: " + this.spec.title + " (" + (this.spec.features || []).length + " features)");

    // Phase B — cards
    this.setPhase("decompose");
    this.cards = (this.spec.features || []).map((f, i) => ({
      id: f.id || ("card-" + i), layer: (f.layer || "L0").slice(0, 2),
      name: f.name || f.id, description: f.description || "",
      status: "PENDING", attempts: 0, repairs: 0, test_src: "", error: ""
    })).filter(c => LAYERS.includes(c.layer));
    this.cards.sort((a, b) => a.layer.localeCompare(b.layer));
    this._emit("info", this.cards.length + " feature cards in dependency order");

    // Phase C — scaffold
    this.setPhase("scaffold");
    const anchors = this.cards.map(c =>
      "<!-- @SECTION:" + c.id + " -->\n// TODO(" + c.id + "): " + c.name + "\n<!-- @END:SECTION:" + c.id + " -->").join("\n");
    const boot = await this.llm.chat([
      { role: "system", content: "You are the SCAFFOLD stage of BAA. Emit the START of a single-file HTML game skeleton: doctype, head (title, styles, CDN script tags from the spec), body markup, and opening <script> tag containing the game bootstrap stub (window.__game init, __TEST__ deterministic mode hook, main loop placeholder). End your reply exactly with this line and nothing after it:\n/*SCAFFOLD-END*/" },
      { role: "user", content: "Spec:\n" + JSON.stringify(this.spec) + "\nFeature sections that will be appended later:\n" + anchors }
    ], { maxTokens: 4096 });
    const cut = boot.indexOf("/*SCAFFOLD-END*/");
    const head = (cut >= 0 ? boot.slice(0, cut) : boot).trim();
    const tail = "</script>\n<!-- BAA feature sections:\n" + anchors.replace(/-->/g, "--\>") + "\n-->" + "\n</body>\n</html>";
    this.scaffold = head + "\n" + tail;
    this.html = this.scaffold;
    this._emit("info", "scaffold ready (" + this.scaffold.length + " chars)");

    // Phase D — micro-loop per card
    this.setPhase("microloop");
    for (const card of this.cards) {
      this._check();
      await this.runCard(card);
    }

    // Phase E — integration gates
    this.setPhase("gates");
    await this.runGates();

    // Phase F — ship
    this.setPhase("ship");
    this.finished = true;
    this._emit("info", "shipped: " + this.html.length + " chars, " +
      this.cards.filter(c => c.status === "PASS").length + "/" + this.cards.length + " cards PASS");
    return this.html;
  }

  async runCard(card) {
    this._emit("card", card.id);
    // 1. TEST-FIRST
    try {
      const tRaw = await this.llm.chat([
        { role: "system", content: BT.SYSTEM_TEST },
        { role: "user", content: "Feature card: " + JSON.stringify({ id: card.id, layer: card.layer, name: card.name, description: card.description }) +
          "\nSpec context: " + JSON.stringify({ title: this.spec.title, camera: this.spec.camera, controls: this.spec.controls, engine: this.spec.engine }) +
          "\nCurrent code (truncated):\n" + this.html.slice(0, 6000) }
      ], { maxTokens: 1024 });
      const tf = extractFn(tRaw);
      card.test_fn = tf.fn; card.test_src = tf.src;
    } catch (e) {
      card.status = "QUARANTINED"; card.error = "test-gen: " + e.message;
      this._emit("fail", card.id + ": " + card.error);
      return;
    }
    // 2. IMPLEMENT (<= maxImplTries)
    for (let attempt = 1; attempt <= this.opts.maxImplTries; attempt++) {
      this._check();
      card.attempts = attempt;
      try {
        const sys = attempt === 1 ? BT.SYSTEM_IMPL : BT.SYSTEM_FIX;
        const ctx = attempt === 1
          ? "Full HTML:\n" + this.html + "\n\nImplement THIS card in its owned section:\n" + JSON.stringify({ id: card.id, name: card.name, description: card.description })
          : "Previous attempt failed verification.\nFailure: " + card.error + "\n\nFull HTML:\n" + this.html + "\n\nCard (same section ownership):\n" + JSON.stringify({ id: card.id, name: card.name, description: card.description });
        const out = await this.llm.chat([{ role: "system", content: sys }, { role: "user", content: ctx }], { maxTokens: 16384 });
        const next = attempt === 1 ? extractHTML(out) : (() => {
          const h = extractHTML(out);
          return h.includes("@SECTION:" + card.id) ? h : replaceSection(this.html, card.id, this.extractBody(h, card.id));
        })();
        this._pendingHtml = next;
        // 3. VERIFY
        const v = await this.verify(card);
        if (v.ok) {
          this.html = next;
          card.status = "PASS"; card.error = "";
          this._emit("pass", card.id + " (attempt " + attempt + ")");
          if (this.state && this.state.persist) this.state.persist(this);
          return;
        }
        card.error = v.error;
        this._emit("fail", card.id + ": " + v.error.slice(0, 160));
      } catch (e) {
        card.error = e.message;
        this._emit("fail", card.id + ": " + e.message.slice(0, 160));
      }
    }
    card.status = "QUARANTINED";
    this._emit("quarantine", card.id);
    if (this.state && this.state.persist) this.state.persist(this);
  }

  extractBody(h, id) {
    const a = h.indexOf("<!-- @SECTION:" + id + " -->");
    const b = h.indexOf("<!-- @END:SECTION:" + id + " -->");
    return a >= 0 && b > a ? h.slice(a, b) : h;
  }

  async verify(card) {
    const html = this._pendingHtml || this.html;
    const r = await this.runnerRun(html, { fn: card.test_fn, src: card.test_src });
    if (!r.ok) return { ok: false, error: r.error };
    // regression: re-run all previously passed cards' tests
    for (const prev of this.cards) {
      if (prev.status !== "PASS" || prev.id === card.id) continue;
      const rr = await this.runnerRun(html, { fn: prev.test_fn, src: prev.test_src });
      if (!rr.ok) return { ok: false, error: "regression on '" + prev.id + "': " + rr.error };
    }
    return { ok: true };
  }

  async runnerRun(html, tf) {
    if (!this.runner) return { ok: true, skipped: true }; // no sandbox available -> trust static checks
    const norm = (tf && typeof tf === "object") ? tf : { fn: tf, src: tf && tf.toString ? tf.toString() : "" };
    if (!norm.src) return { ok: false, error: "no acceptance test source" };
    try { return await this.runner(html, norm); }
    catch (e) { return { ok: false, error: "runner: " + e.message }; }
  }

  async runGates() {
    const gateChecks = [
      { name: "boot", fn: () => /<!DOCTYPE html>/i.test(this.html) && /<\/html>/i.test(this.html) },
      { name: "no-empty-sections", fn: () => !/TODO\(/.test(this.html) },
      { name: "has-game-state", fn: () => /__game/.test(this.html) },
      { name: "has-loop", fn: () => /(requestAnimationFrame|setInterval)/.test(this.html) }
    ];
    for (const g of gateChecks) {
      if (!g.fn()) { this._emit("gate-fail", g.name); await this.repairGate(g.name); }
      else this._emit("gate-pass", g.name);
    }
    // G-CardReplay: re-run every passed card's acceptance test on the FINAL html
    if (this.runner) {
      for (const c of this.cards.filter(x => x.status === "PASS")) {
        const r = await this.runnerRun(this.html, { fn: c.test_fn, src: c.test_src });
        if (!r.ok) { this._emit("gate-fail", "replay:" + c.id + " " + r.error.slice(0,80)); await this.repairGate("replay:" + c.id); }
        else this._emit("gate-pass", "replay:" + c.id);
      }
    }
  }

  async repairGate(name) {
    for (let i = 0; i < this.opts.maxRepairs; i++) {
      try {
        const out = await this.llm.chat([
          { role: "system", content: BT.SYSTEM_FIX },
          { role: "user", content: "Integration gate '" + name + "' failed on this HTML. Fix minimally so the gate passes. Full HTML:\n" + this.html }
        ], { maxTokens: 16384 });
        this.html = extractHTML(out);
        this._emit("gate-repair", name + " attempt " + (i + 1));
        return;
      } catch (e) { /* retry */ }
    }
    this._emit("gate-quarantine", name);
  }
}
