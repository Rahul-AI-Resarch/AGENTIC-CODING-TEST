"""Phase F — Ship: assemble the final single-file index.html.

Takes runs/<id>/work.html (or skeleton if micro-loop never ran), strips
TODO anchors, appends a self-test harness behind ?selftest=1, writes
dist/<game_id>/index.html and copies the contact screenshot.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

SELFTEST_SNIPPET = """
/*==SECTION:selftest==*/
if (new URLSearchParams(location.search).get('selftest') === '1') {
  window.__BAASELFTEST__ = new Promise(async (resolve) => {
    const results = [];
    const tests = %TESTS%;
    for (const t of tests) {
      try {
        const fn = new Function('mock','assert', t.src);
        const assert = (c,m)=>{ if(!c) throw new Error(m||'assert'); };
        await fn(window.__BAAMock, assert);
        results.push({id:t.id, pass:true});
      } catch(e) { results.push({id:t.id, pass:false, err:String(e).slice(0,200)}); }
    }
    resolve(results);
  });
}
/*==END:selftest==*/
"""


def assemble_final(ctx) -> Path:
    work = ctx.run_dir / "work.html"
    src = work if work.exists() else Path(ctx.ledger.meta["skeleton_path"])
    html = src.read_text()

    # strip leftover TODO anchors from cards that were quarantined silently
    html = re.sub(r"/\* TODO\((?!boot)[\w-]+\) \*/", "/* feature quarantined */", html)

    game_id = ctx.ledger.meta.get("game_id") or _guess_game_id(html)
    dist = Path("dist") / game_id
    dist.mkdir(parents=True, exist_ok=True)

    tests = []
    tdir = ctx.run_dir / "tests"
    if tdir.exists():
        for f in sorted(tdir.glob("*.js")):
            card = ctx.ledger.cards.get(f.stem)
            if card and card.status in ("pass", "patched"):
                tests.append({"id": f.stem, "src": f.read_text()})
    snippet = SELFTEST_SNIPPET.replace(
        "%TESTS%", __import__("json").dumps(tests)
    )
    html = html.replace("</body>", snippet + "\n</body>") if "</body>" in html \
        else html + snippet

    out = dist / "index.html"
    out.write_text(html)
    shot = ctx.run_dir / "contact.png"
    if shot.exists():
        shutil.copy(shot, dist / "contact.png")
    ctx.ledger.meta["game_id"] = game_id
    return out


def _guess_game_id(html: str) -> str:
    m = re.search(r"<title>([^<]+)</title>", html, flags=re.I)
    slug = re.sub(r"[^a-z0-9]+", "-", m.group(1).lower()).strip("-") if m else "game"
    return slug or "game"
