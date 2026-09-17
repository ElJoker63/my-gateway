"""
Combos API — CRUD for named routing chains.
Combos alias a friendly name (e.g. "combo:fast") to an ordered list of
provider/model targets with a failover strategy.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.combos import Combo, ComboTarget, combo_store

logger = logging.getLogger(__name__)
router = APIRouter()


class ComboTargetIn(BaseModel):
    provider: str = Field(..., min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=256)
    weight: int = Field(default=1, ge=1, le=100)


class ComboCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    targets: list[ComboTargetIn] = Field(..., min_length=1, max_length=16)
    strategy: str = Field(default="strict", pattern="^(strict|round_robin|least_used|race)$")
    race_size: int = Field(default=2, ge=2, le=8)


@router.get("", tags=["Combos"])
async def list_combos():
    """List all registered combos."""
    combos = await combo_store.list()
    return {"combos": [c.to_dict() for c in combos], "total": len(combos)}


@router.post("", status_code=201, tags=["Combos"])
async def create_combo(payload: ComboCreate):
    """Create or update a combo."""
    combo = Combo(
        name=payload.name,
        targets=[ComboTarget(**t.model_dump()) for t in payload.targets],
        strategy=payload.strategy,
        race_size=payload.race_size,
    )
    await combo_store.save(combo)
    return combo.to_dict()


@router.get("/{name}", tags=["Combos"])
async def get_combo(name: str):
    """Fetch one combo by name."""
    combo = await combo_store.get(name)
    if not combo:
        raise HTTPException(status_code=404, detail=f"Combo '{name}' not found")
    return combo.to_dict()


@router.delete("/{name}", tags=["Combos"])
async def delete_combo(name: str):
    """Delete a combo."""
    if not await combo_store.delete(name):
        raise HTTPException(status_code=404, detail=f"Combo '{name}' not found")
    return {"status": "deleted", "name": name}
