/* BAA BYOK layer — direct browser fetch to OpenAI-compatible / Gemini APIs.
   Keys live in localStorage only; never sent anywhere except the chosen provider. */

const PROVIDERS = {
  openai:            { label: "OpenAI",                 base: "https://api.openai.com/v1",               model: "gpt-4o",           style: "openai" },
  "openai-compatible": { label: "OpenAI-compatible (Kimi/DeepSeek/OpenRouter…)", base: "https://api.moonshot.ai/v1", model: "kimi-k2-0711-preview", style: "openai" },
  gemini:            { label: "Google Gemini",          base: "",                                       model: "gemini-2.5-flash", style: "gemini" },
  groq:              { label: "Groq (fast, free tier)", base: "https://api.groq.com/openai/v1",          model: "llama-3.3-70b-versatile", style: "openai" },
  ollama:            { label: "Ollama (local)",         base: "http://localhost:11434/v1",               model: "qwen2.5-coder:32b", style: "openai" }
};

class LLM {
  constructor(cfg) { this.cfg = cfg; this.usage = { calls: 0, promptTokens: 0, completionTokens: 0 }; }

  async chat(messages, opts) {
    opts = opts || {};
    const c = this.cfg;
    if (!c.apiKey) throw new Error("no API key set (BYOK: enter it in Settings)");
    const maxTok = Math.min(opts.maxTokens || 8192, c.maxTokensCap || 16384);
    if (PROVIDERS[c.provider].style === "gemini") return this._gemini(messages, maxTok);
    return this._openai(messages, maxTok);
  }

  async _openai(messages, maxTok) {
    const c = this.cfg;
    const url = (c.baseUrl || PROVIDERS[c.provider].base).replace(/\/$/, "") + "/chat/completions";
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer " + c.apiKey },
      body: JSON.stringify({
        model: c.model || PROVIDERS[c.provider].model,
        messages, temperature: 0.2, max_tokens: maxTok
      })
    });
    if (!res.ok) throw new Error("HTTP " + res.status + ": " + (await res.text()).slice(0, 300));
    const j = await res.json();
    const u = j.usage || {};
    this.usage.calls++; this.usage.promptTokens += u.prompt_tokens || 0; this.usage.completionTokens += u.completion_tokens || 0;
    const content = j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content;
    if (!content) throw new Error("empty completion");
    return content;
  }

  async _gemini(messages, maxTok) {
    const c = this.cfg;
    const model = c.model || PROVIDERS.gemini.model;
    const sys = messages.filter(m => m.role === "system").map(m => m.content).join("\n\n");
    const contents = messages.filter(m => m.role !== "system")
      .map(m => ({ role: m.role === "assistant" ? "model" : "user", parts: [{ text: m.content }] }));
    const url = "https://generativelanguage.googleapis.com/v1beta/models/" + encodeURIComponent(model) +
      ":generateContent?key=" + encodeURIComponent(c.apiKey);
    const body = { contents, generationConfig: { temperature: 0.2, maxOutputTokens: maxTok } };
    if (sys) body.systemInstruction = { parts: [{ text: sys }] };
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!res.ok) throw new Error("HTTP " + res.status + ": " + (await res.text()).slice(0, 300));
    const j = await res.json();
    const cand = j.candidates && j.candidates[0];
    const text = cand && cand.content && cand.content.parts && cand.content.parts.map(p => p.text || "").join("");
    if (!text) throw new Error("empty gemini response: " + JSON.stringify(j).slice(0, 200));
    const mu = j.usageMetadata || {};
    this.usage.calls++; this.usage.promptTokens += mu.promptTokenCount || 0; this.usage.completionTokens += mu.candidatesTokenCount || 0;
    return text;
  }
}

/* Sandbox test runner: loads candidate HTML in a hidden same-origin iframe with
   __TEST__ flag, injects assert/step helpers, runs the acceptance test fn. */
function makeRunner(timeoutMs) {
  timeoutMs = timeoutMs || 25000;
  return function run(html, testFn) {
    return new Promise((resolve) => {
      let done = false;
      const iframe = document.createElement("iframe");
      iframe.style.cssText = "position:fixed;left:-9999px;width:640px;height:480px;border:0";
      iframe.setAttribute("sandbox", "allow-scripts allow-same-origin");
      document.body.appendChild(iframe);

      const cleanup = () => { try { document.body.removeChild(iframe); } catch (e) {} };
      const finish = (r) => { if (!done) { done = true; clearTimeout(timer); resolve(r); } };

      const timer = setTimeout(() => { finish({ ok: false, error: "test timeout (" + timeoutMs + "ms)" }); cleanup(); }, timeoutMs);

      function boot() {
        try {
          const w = iframe.contentWindow;
          w.__TEST__ = true;
          if (!w.assert) w.assert = (cond, msg) => { if (!cond) throw new Error(msg || "assert failed"); };
          if (!w.step) w.step = (n) => { n = n || 1; for (let i = 0; i < n; i++) { if (typeof w.__step === "function") w.__step(16.67); } };
          w.onerror = (msg) => { finish({ ok: false, error: "pageerror: " + msg }); cleanup(); };
          w.addEventListener("unhandledrejection", (ev) => { finish({ ok: false, error: "reject: " + ev.reason }); cleanup(); });
          // give game scripts a tick to init
          setTimeout(() => {
            try {
              const doc = w.document;
              const canvas = doc.querySelector("canvas");
              if (!w.__game) { finish({ ok: false, error: "window.__game not exposed (boot failed)" }); cleanup(); return; }
              const step = (n) => {
                n = n || 1;
                for (let i = 0; i < n; i++) {
                  if (typeof w.__step === "function") w.__step(16.67);
                  else if (typeof w.requestAnimationFrame === "function") { /* rAF-driven sim advances naturally */ }
                }
              };
              const assert = (cond, msg) => { if (!cond) throw new Error(msg || "assert failed"); };
              // Compile the acceptance test against the iframe window: bare identifiers
              // (assert/step/__game/window) resolve via explicit parameters bound to w.
              let src = String(testFn.src).trim().replace(/;+\s*$/, "");
              src = src.replace(/\)\(\s*$/, ")"); // "(function(){...})()" -> "(function(){...})"
              // Inject the test source into the IFRAME document as a script that wraps it with
              // the iframe's own globals (assert/step/__game/window), exposing window.__runTest.
              const wrap = doc.createElement("script");
              wrap.textContent = "window.__runTest=function(a){var __f=(" + src + ");return __f.call(window,a);};" ;
              doc.head.appendChild(wrap);
              if (typeof w.__runTest !== "function") { finish({ ok:false, error:"test injection failed" }); cleanup(); return; }
              let result;
              try { result = w.__runTest({ assert: w.assert, step: w.step }); }
              catch (e) { finish({ ok: false, error: String(e && e.message || e) }); cleanup(); return; }
              if (result && typeof result.then === "function") {
                result.then(() => { finish({ ok: true }); cleanup(); })
                      .catch(e => { finish({ ok: false, error: String(e && e.message || e) }); cleanup(); });
              } else { finish({ ok: true }); cleanup(); }
            } catch (e) { finish({ ok: false, error: String(e && e.message || e) }); cleanup(); }
          }, 1200);
        } catch (e) { finish({ ok: false, error: "runner: " + e.message }); cleanup(); }
      }

      iframe.onload = boot;
      const d = iframe.contentDocument;
      const shim = "<script>window.__TEST__=true;" +
        "window.assert=function(c,m){if(!c)throw new Error(m||'assert failed')};" +
        "window.step=function(n){n=n||1;for(var i=0;i<n;i++){if(typeof window.__step==='function')window.__step(16.67)}};<\/script>";
      d.open(); d.write(html.replace(/<script(?!\s*src)/i, shim + "<script")); d.close();
    });
  };
}
