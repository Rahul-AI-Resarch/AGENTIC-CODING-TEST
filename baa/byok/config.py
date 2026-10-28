"""BYOK layer — Bring Your Own Key.

Provider-agnostic configuration for the Build Anything Agent (YOK).
Supports any OpenAI-compatible endpoint and Google Gemini.
Keys are NEVER stored in code; only read from environment / .env.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional convenience: load .env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


VALID_PROVIDERS = ("openai", "gemini", "openai-compatible", "ollama")


@dataclass
class BYOKConfig:
    """Resolved runtime configuration for one build run."""

    provider: str = "openai"                      # openai | gemini | openai-compatible | ollama
    model: str = ""                              # e.g. gpt-4o, kimi-k2, gemini-2.5-pro
    api_key: str = field(default="", repr=False)
    base_url: str | None = None                  # for openai-compatible/ollama endpoints
    temperature: float = 0.0                     # deterministic by default
    max_tokens: int = 8192
    request_timeout: float = 120.0
    cache_dir: str = ".baa_cache"                # LLM response cache (prompt-hash keyed)
    token_budget: int = 4_000_000                # global per-run ceiling
    wall_clock_minutes: int = 90                 # global per-run ceiling
    attempts_per_card: int = 3                   # implement retries inside micro-loop
    repairs_per_card: int = 2                    # surgical repair retries on gate failure

    @classmethod
    def from_env(cls) -> "BYOKConfig":
        provider = os.getenv("BAA_PROVIDER", "openai").strip().lower()
        if provider not in VALID_PROVIDERS:
            raise ValueError(
                f"BAA_PROVIDER={provider!r} invalid. Choose one of {VALID_PROVIDERS}"
            )

        if provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
            model = os.getenv("BAA_MODEL", "gemini-2.5-flash")
            base_url = None
        elif provider == "ollama":
            api_key = "not-needed"
            model = os.getenv("BAA_MODEL", "qwen2.5-coder:32b")
            base_url = os.getenv("BAA_BASE_URL", "http://localhost:11434/v1")
        else:  # openai / openai-compatible (covers Moonshot/Kimi, DeepSeek, vLLM...)
            api_key = os.getenv("OPENAI_API_KEY") or os.getenv("BAA_API_KEY") or ""
            model = os.getenv("BAA_MODEL", "gpt-4o")
            base_url = os.getenv("BAA_BASE_URL") or None

        if not api_key:
            raise RuntimeError(
                "No API key found. This agent is BYOK: export OPENAI_API_KEY "
                "(or GEMINI_API_KEY), or put it in a .env file at repo root."
            )

        return cls(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=float(os.getenv("BAA_TEMPERATURE", "0.0")),
            max_tokens=int(os.getenv("BAA_MAX_TOKENS", "8192")),
            token_budget=int(os.getenv("BAA_TOKEN_BUDGET", "4000000")),
            wall_clock_minutes=int(os.getenv("BAA_WALL_CLOCK_MINUTES", "90")),
        )

    def redacted(self) -> dict:
        d = self.__dict__.copy()
        d["api_key"] = "***redacted***" if self.api_key else ""
        return d
