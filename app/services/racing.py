"""
Race execution — fire N combo targets in parallel, first valid wins.

Each worker runs the full call path (key acquire → provider chat → record
outcome) on an isolated copy of the request; the first success cancels the
rest. On total failure the caller falls back to sequential retry-next-target.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.services.key_manager import key_manager

logger = logging.getLogger(__name__)


@dataclass
class RaceOutcome:
    """Result of one combo race."""
    ok: bool
    result: dict | None = None
    target: Any | None = None  # ComboTarget that won
    attempts: int = 0
    error: str | None = None


async def race_targets(
    targets: list[Any],
    call_fn,
    race_size: int = 2,
    abort_grace_ms: int = 50,
) -> RaceOutcome:
    """
    Run `call_fn(target)` for up to `race_size` targets concurrently.

    `call_fn` is async and must raise on failure. The first coroutine to
    return successfully wins; others are cancelled. Returns the winner's
    RaceOutcome, or the last error when every racer fails.
    """
    if not targets:
        return RaceOutcome(ok=False, error="no targets")

    size = max(1, min(race_size, len(targets)))
    todo = targets[:size]
    winner: asyncio.Future = asyncio.get_running_loop().create_future()
    tasks: list[asyncio.Task] = []
    last_error: BaseException | None = None

    async def _worker(target):
        nonlocal last_error
        try:
            result = await call_fn(target)
            if not winner.done():
                winner.set_result((target, result))
        except Exception as e:
            last_error = e

    for t in todo:
        tasks.append(asyncio.create_task(_worker(t)))

    _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    if not winner.done():
        # First finisher was a failure — wait for the rest
        await asyncio.gather(*pending, return_exceptions=True)
        pending = []

    # Cancel losers politely, then hard-cancel after the grace window
    for p in pending:
        p.cancel()
    if pending:
        await asyncio.wait(pending, timeout=max(abort_grace_ms, 1) / 1000.0)

    for t in tasks:
        if t.done() and not t.cancelled() and (exc := t.exception()) is not None:
            last_error = exc if last_error is None else last_error

    if winner.done():
        target, result = winner.result()
        return RaceOutcome(ok=True, result=result, target=target, attempts=len(todo))

    return RaceOutcome(ok=False, attempts=len(todo), error=str(last_error))


async def race_or_failover(
    targets: list[Any],
    call_fn,
    strategy: str = "strict",
    race_size: int = 2,
) -> RaceOutcome:
    """
    Dispatch per combo strategy:
    - race:        parallel first-wins
    - strict:      sequential order, stop at first success
    - least_used / round_robin: caller already ordered targets; same as strict
    """
    if strategy == "race" and len(targets) > 1:
        return await race_targets(targets, call_fn, race_size=race_size)

    last_error: BaseException | None = None
    attempts = 0
    for target in targets:
        attempts += 1
        try:
            result = await call_fn(target)
            return RaceOutcome(ok=True, result=result, target=target, attempts=attempts)
        except Exception as e:
            last_error = e
            continue
    return RaceOutcome(ok=False, attempts=attempts, error=str(last_error))


async def execute_combo(
    combo,
    call_fn,
    key_manager_instance=None,
) -> RaceOutcome:
    """
    Order a combo's targets per its strategy, then race/failover through them.

    Strategy ordering happens here so `call_fn` stays a dumb provider call.
    `key_manager_instance` lets least_used share the same "requests_used" view
    as real traffic; defaults to the global key_manager.
    """
    km = key_manager_instance or key_manager
    targets = list(combo.targets)

    if combo.strategy == "round_robin" and len(targets) > 1:
        from app.services.combos import combo_store
        idx = await combo_store.next_rotation_index(combo.name, len(targets))
        targets = targets[idx:] + targets[:idx]
    elif combo.strategy == "least_used" and len(targets) > 1:
        # Use the pool status probe already implemented for the KeyManager
        async def _usage(target) -> int:
            try:
                status = await km.get_pool_status(target.provider)
                return sum(k.get("requests_used", 0) for k in status.get("keys", []))
            except Exception:
                return 0

        usage = await asyncio.gather(*(_usage(t) for t in targets))
        targets = [t for _, t in sorted(zip(usage, targets, strict=True), key=lambda x: x[0])]

    outcome = await race_or_failover(targets, call_fn, combo.strategy, combo.race_size)
    # Metrics per combo execution are recorded by the chat pipeline so each
    # request counts once; circuit-breaker updates happen inside the caller's
    # call_fn. This function only orchestrates the strategy.
    return outcome

