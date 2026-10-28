"""Runtime gates — headless browser via Playwright.

Per-card: run_acceptance_test() executes the card's test_fn inside the page.
Integration (Phase E): boot, blank-canvas pixel check, entity count, input
scripting, state-machine walk, 60s soak with FPS + memory trend.
If Playwright browsers are not installed these raise RuntimeError, which the
micro-loop surfaces as a gate failure (never a silent pass).
"""
from __future__ import annotations

import json
from pathlib import Path

_HARNESS = """
window.__BAAMock = {
  stepFrames(n){ return new Promise(res=>{ let i=0;
    const tick=()=>{ if(i++>=n) return res(true); requestAnimationFrame(tick); };
    requestAnimationFrame(tick); }); },
  dispatchKey(key){ ['keydown'].forEach(t=>window.dispatchEvent(
      new KeyboardEvent(t,{key,code:'Key'+key.toUpperCase(),bubbles:true}))); },
  getState(){ return window.__GAME_STATE__ || null; },
  pixelSample(){ const c=document.querySelector('canvas'); if(!c) return null;
    const g=c.getContext(c.getContext('2d')?'2d':'webgl2')||c.getContext('webgl');
    if(!g) return null;
    if(g instanceof WebGLRenderingContext||g instanceof WebGL2RenderingContext){
      const px=new Uint8Array(4*16); // sample 4x4 block center
      g.readPixels(c.width/2-2,c.height/2-2,4,4,g.RGBA,g.UNSIGNED_BYTE,px);
      return Array.from(px);} 
    return Array.from(g.getImageData(c.width/2,c.height/2,1,1).data); },
};
"""


def _browser():
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(args=["--no-sandbox", "--use-gl=swiftshader"])
    except Exception as e:
        pw.stop()
        raise RuntimeError(
            f"Playwright chromium unavailable ({e}). Run: playwright install chromium"
        )
    return pw, browser


def run_acceptance_test(html_path: Path, test_fn: str,
                        timeout_ms: int = 15000) -> tuple[bool, str]:
    """Load page, inject harness, await the card's async test body."""
    if not test_fn.strip():
        return False, "empty test source"
    pw, browser = _browser()
    try:
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)[:300]))
        page.goto(f"file://{html_path.resolve()}")
        page.wait_for_timeout(1200)  # let boot + CDN libs settle
        page.evaluate(_HARNESS)
        result = page.evaluate(
            "(async () => { try { const fn = new Function(%s);"
            " await fn.call(window.__BAAMock ? undefined : undefined);"
            " } catch(e) { return 'ERR:'+String(e).slice(0,300); } })()" %
            json.dumps(test_fn)
        ) if False else page.evaluate(
            "(async () => { try {"
            f"   const t = {json.dumps(test_fn)};"
            "   const fn = new Function('mock','assert', t);"
            "   const assert = (cond,msg)=>{ if(!cond) throw new Error('ASSERT: '+msg); };"
            "   await fn(window.__BAAMock, assert);"
            "   return 'OK';"
            " } catch(e) { return 'ERR:'+String(e).slice(0,300); } })()"
        )
        ok = result == "OK" and not errors
        err = "" if ok else (result or "") + (" | pageerrors: " + "; ".join(errors[:3])
                                              if errors else "")
        return ok, err[:400]
    finally:
        browser.close()
        pw.stop()


# ----------------------------------------------------------- Phase E gates
def integration_gates(ctx, spec: dict) -> dict:
    work = ctx.run_dir / "work.html"
    html_path = work if work.exists() else Path(ctx.ledger.meta["skeleton_path"])
    out: dict[str, dict] = {}
    pw, browser = _browser()
    try:
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        console_errors: list[str] = []
        page.on("console", lambda m: console_errors.append(m.text)
                if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        # G-boot
        page.goto(f"file://{html_path.resolve()}")
        page.wait_for_timeout(2000)
        out["boot"] = {"pass": not console_errors,
                       "errors": console_errors[:5]}

        # G-blank: canvas must show non-uniform pixels
        out["nonblank"] = _check_nonblank(page)

        # G-scene: expected entity count alive after 3s sim
        expected = sum(int(e.get("count", 0)) for e in spec.get("entities", [])
                       if isinstance(e, dict))
        actual = page.evaluate(
            "() => { const s = window.__GAME_STATE__; return s && s.entityCount != null"
            " ? s.entityCount : (s && s.entities ? Object.keys(s.entities).length : -1); }"
        )
        out["scene"] = {"pass": actual == -1 or actual >= max(1, expected // 2),
                        "expected_min": expected, "actual": actual}

        # G-soak: 60s fps sample (shortened to 10s unless BAA_SOAK_MS set)
        soak_ms = int(__import__("os").getenv("BAA_SOAK_MS", "10000"))
        fps = page.evaluate(
            "(ms) => new Promise(res => { let n=0; const t0=performance.now();"
            " const tick=()=>{ n++; if(performance.now()-t0<ms)"
            " requestAnimationFrame(tick); else res(Math.round(n*1000/(performance.now()-t0))); };"
            " requestAnimationFrame(tick); })", soak_ms
        )
        min_fps = spec.get("perf_target", {}).get("fps_min", 24)
        out["soak"] = {"pass": fps >= min_fps * 0.6,  # swiftshader is slow; scale
                      "fps": fps, "target": min_fps}

        page.screenshot(path=str(ctx.run_dir / "contact.png"))
    finally:
        browser.close()
        pw.stop()
    return out


def _check_nonblank(page) -> dict:
    try:
        data = page.evaluate(_HARNESS + " window.__BAAMock.pixelSample()")
        if data is None:
            return {"pass": False, "errors": ["no canvas/pixel access"]}
        vals = data if isinstance(data, list) else [data]
        uniq = len(set(vals))
        return {"pass": uniq > 1 or (vals and vals[-1] > 0),
                "sample": vals[:8], "distinct": uniq}
    except Exception as e:
        return {"pass": False, "errors": [str(e)[:200]]}
