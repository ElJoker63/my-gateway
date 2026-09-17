"""
Combo registry — named provider+model chains.

A combo aliases a friendly name ("smart", "fast", "coder") to an ordered
list of targets. Requests can use `model="combo:smart"` to route through it.
Strategies:
- strict:      try targets in order, fail over on error
- round_robin: rotate the starting target
- least_used:  prefer the target with the lowest recent request count
- race:        fire several targets in parallel, first valid response wins
"""

import json
import logging
import time
from dataclasses import dataclass, field

from app.database.redis import get_redis

logger = logging.getLogger(__name__)

COMBO_PREFIX = "gw:combo:"
COMBO_INDEX = "gw:combos:index"
COMBO_RR_PREFIX = "gw:combo:rr:"


@dataclass
class ComboTarget:
    """One target in a combo's chain."""
    provider: str
    model: str | None = None  # None → provider default model
    weight: int = 1

    def to_dict(self) -> dict:
        return {"provider": self.provider, "model": self.model, "weight": self.weight}


@dataclass
class Combo:
    """A named routing chain with an execution strategy."""
    name: str
    targets: list[ComboTarget]
    strategy: str = "strict"  # strict | round_robin | least_used | race
    race_size: int = 2        # only used by strategy="race"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "targets": [t.to_dict() for t in self.targets],
            "strategy": self.strategy,
            "race_size": self.race_size,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Combo":
        return cls(
            name=data["name"],
            targets=[ComboTarget(**t) for t in data.get("targets", [])],
            strategy=data.get("strategy", "strict"),
            race_size=data.get("race_size", 2),
            created_at=data.get("created_at", time.time()),
        )


class ComboStore:
    """Redis-backed combo registry with in-memory fallback."""

    def __init__(self):
        self._local: dict[str, Combo] = {}

    async def list(self) -> list[Combo]:
        try:
            redis = await get_redis()
            keys = await redis.smembers(COMBO_INDEX)
            combos = []
            for raw in keys:
                name = raw.decode() if isinstance(raw, bytes) else raw
                raw_data = await redis.get(f"{COMBO_PREFIX}{name}")
                if raw_data:
                    combos.append(Combo.from_dict(json.loads(raw_data)))
            return combos or list(self._local.values())
        except Exception as e:
            logger.debug(f"Combo list via Redis failed ({e}); using local cache")
            return list(self._local.values())

    async def get(self, name: str) -> Combo | None:
        """Look up a combo by name, with or without the 'combo:' prefix."""
        clean = name.removeprefix("combo:")
        try:
            redis = await get_redis()
            raw = await redis.get(f"{COMBO_PREFIX}{clean}")
            if raw:
                return Combo.from_dict(json.loads(raw))
        except Exception as e:
            logger.debug(f"Combo get via Redis failed ({e})")
        return self._local.get(clean)

    async def save(self, combo: Combo):
        self._local[combo.name] = combo
        try:
            redis = await get_redis()
            await redis.set(f"{COMBO_PREFIX}{combo.name}", json.dumps(combo.to_dict()))
            await redis.sadd(COMBO_INDEX, combo.name)
        except Exception as e:
            logger.warning(f"Failed to persist combo '{combo.name}' to Redis: {e}")

    async def delete(self, name: str) -> bool:
        clean = name.removeprefix("combo:")
        existed_local = self._local.pop(clean, None) is not None
        try:
            redis = await get_redis()
            removed = await redis.delete(f"{COMBO_PREFIX}{clean}")
            await redis.srem(COMBO_INDEX, clean)
            return bool(removed) or existed_local
        except Exception as e:
            logger.warning(f"Failed to delete combo '{clean}' from Redis: {e}")
            return existed_local

    async def next_rotation_index(self, combo_name: str, modulo: int) -> int:
        """Atomic round-robin counter shared across workers."""
        if modulo <= 0:
            return 0
        try:
            redis = await get_redis()
            return int(await redis.incr(f"{COMBO_RR_PREFIX}{combo_name}")) % modulo
        except Exception:
            combo = self._local.get(combo_name)
            if combo is None:
                return 0
            idx = getattr(combo, "_local_rr", 0)
            combo._local_rr = idx + 1
            return idx % modulo


combo_store = ComboStore()
