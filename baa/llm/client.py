"""LLM client — talks to the provider chosen via BYOK config.

One interface, three backends (OpenAI-compatible, Gemini, local/Ollama).
Responses are cached by prompt-hash so re-runs cost nothing and gates stay
deterministic. The rest of the agent NEVER imports a vendor SDK directly.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from baa.byok.config import BYOKConfig


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, cfg: BYOKConfig):
        self.cfg = cfg
        self.cache_dir = Path(cfg.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = None
        if cfg.provider in ("openai", "openai-compatible", "ollama"):
            from openai import OpenAI  # lazy import

            self._client = OpenAI(
                api_key=cfg.api_key,
                base_url=cfg.base_url,
                timeout=cfg.request_timeout,
            )
            self._mode = "openai"
        elif cfg.provider == "gemini":
            self._mode = "gemini"
        else:  # pragma: no cover
            raise LLMError(f"unsupported provider {cfg.provider}")

    # ------------------------------------------------------------------ api
    def complete(self, system: str, user: str, tag: str = "") -> str:
        """Return raw text completion for a (system,user) prompt pair."""
        key = self._hash(system, user)
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text())["text"]

        text = self._call_with_retry(system, user)
        cache_file.write_text(json.dumps({"tag": tag, "text": text}))
        return text

    def complete_json(self, system: str, user: str, tag: str = "") -> dict:
        """Ask for strict JSON; parse defensively (strip fences, retry once)."""
        sys2 = system + "\nRespond with VALID JSON ONLY. No prose, no code fences."
        for attempt in range(2):
            raw = self.complete(sys2, user, tag=f"{tag}:json{attempt}")
            parsed = _lenient_json(raw)
            if parsed is not None:
                return parsed
            user = user + "\n\nIMPORTANT: your previous reply was not valid JSON. Return pure JSON."
        raise LLMError(f"model failed to produce valid JSON for tag={tag!r}")

    # ------------------------------------------------------------- internals
    def _call_with_retry(self, system: str, user: str) -> str:
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                if self._mode == "openai":
                    resp = self._client.chat.completions.create(
                        model=self.cfg.model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        temperature=self.cfg.temperature,
                        max_tokens=self.cfg.max_tokens,
                    )
                    return resp.choices[0].message.content or ""
                if self._mode == "gemini":
                    return self._gemini_call(system, user)
            except Exception as e:  # network/rate-limit blips
                last_err = e
                time.sleep(2 ** attempt)
        raise LLMError(f"LLM call failed after retries: {last_err}")

    def _gemini_call(self, system: str, user: str) -> str:
        import requests

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.cfg.model}:generateContent?key={self.cfg.api_key}"
        )
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": self.cfg.temperature,
                "maxOutputTokens": self.cfg.max_tokens,
            },
        }
        r = requests.post(url, json=body, timeout=self.cfg.request_timeout)
        r.raise_for_status()
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    @staticmethod
    def _hash(system: str, user: str) -> str:
        h = hashlib.sha256()
        h.update(system.encode()); h.update(b"\x00"); h.update(user.encode())
        return h.hexdigest()[:32]


def _lenient_json(raw: str) -> dict | None:
    """Best-effort JSON extraction: strip ```fences``` then find outer braces."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {"_list": obj}
    except Exception:
        pass
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(s[start : end + 1])
        except Exception:
            return None
    return None
