"""FeatureCard schema + ledger + dependency graph — the atom of all work.

Every behavior in a game becomes one card. Cards are generated bottom-up
(L0 engine -> L7 feel) and each card runs through the micro-loop:
TEST-FIRST -> IMPLEMENT -> VERIFY -> REGRESS. The conductor only ever moves
cards between statuses; it contains no game knowledge itself.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


class Layer(str, Enum):
    L0_ENGINE = "L0-engine"
    L1_PHYSICS = "L1-physics"
    L2_ENTITIES = "L2-entities"
    L3_SYSTEMS = "L3-systems"
    L4_MECHANICS = "L4-mechanics"
    L5_UI = "L5-ui"
    L6_CONTENT = "L6-content"
    L7_FEEL = "L7-feel"


LAYER_ORDER = [l.value for l in Layer]


class CardStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASS = "pass"
    PATCHED = "patched"        # passed only after surgical repair
    QUARANTINED = "quarantined"  # exhausted retries; dependents skipped
    FAILED = "failed"          # hard failure (budget/escalation)


@dataclass
class FeatureCard:
    id: str                          # kebab-case, e.g. "wind-model"
    title: str                       # human label
    layer: str                       # one of LAYER_ORDER
    depends_on: list[str] = field(default_factory=list)
    spec_fields: list[str] = field(default_factory=list)   # paths into spec.json
    acceptance: str = ""             # plain-English behavior contract
    owned_sections: list[str] = field(default_factory=list)  # scaffold section ids
    status: str = CardStatus.PENDING.value
    attempts: int = 0
    repairs: int = 0
    test_source: str = ""            # filled by TEST-FIRST step
    impl_summary: str = ""           # short description of implemented code
    gate_log: list[dict] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FeatureCard":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


class Ledger:
    """JSON-file-backed store of all cards + run metadata. Resumable."""

    def __init__(self, run_dir: Path):
        self.path = Path(run_dir) / "ledger.json"
        self.meta: dict = {"run_id": Path(run_dir).name, "created": time.time()}
        self.cards: dict[str, FeatureCard] = {}
        if self.path.exists():
            blob = json.loads(self.path.read_text())
            self.meta.update(blob.get("meta", {}))
            for cd in blob.get("cards", []):
                c = FeatureCard.from_dict(cd)
                self.cards[c.id] = c

    # ------------------------------------------------------------------ crud
    def add(self, card: FeatureCard) -> None:
        if card.id in self.cards:
            raise ValueError(f"duplicate card id {card.id}")
        self.cards[card.id] = card

    def get(self, cid: str) -> FeatureCard:
        return self.cards[cid]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        blob = {
            "meta": self.meta,
            "cards": [c.to_dict() for c in self.cards.values()],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob, indent=2))
        tmp.replace(self.path)

    # ------------------------------------------------------------- ordering
    def ready_cards(self) -> list[FeatureCard]:
        """Cards whose deps are all resolved (PASS/PATCHED), in layer order."""
        done = {c.id for c in self.cards.values()
                if c.status in (CardStatus.PASS.value, CardStatus.PATCHED.value)}
        blocked_by_quarantine = self._quarantine_closure()
        out = [
            c for c in self.cards.values()
            if c.status == CardStatus.PENDING.value
            and set(c.depends_on) <= done
            and not (set(c.depends_on) & blocked_by_quarantine)
        ]
        return sorted(out, key=lambda c: (LAYER_ORDER.index(c.layer), c.id))

    def _quarantine_closure(self) -> set[str]:
        """Ids of cards that can never pass because an ancestor failed."""
        bad = {c.id for c in self.cards.values()
               if c.status in (CardStatus.QUARANTINED.value, CardStatus.FAILED.value)}
        changed = True
        while changed:
            changed = False
            for c in self.cards.values():
                if c.id not in bad and set(c.depends_on) & bad:
                    bad.add(c.id)
                    changed = True
        return bad

    def stats(self) -> dict:
        from collections import Counter
        return dict(Counter(c.status for c in self.cards.values()))
