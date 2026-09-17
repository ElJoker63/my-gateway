"""
OAuth API — start/complete OAuth handshakes for providers that don't take
static API keys (Kiro via AWS SSO OIDC device flow, Antigravity via Google
PKCE flow).

Flow:
- POST /api/oauth/{provider}/start → {flow, authUrl} or {verificationUri, userCode}
- GET  /api/oauth/{provider}/poll?state=...  — device flow polling (404 pending / 200 done)
- GET  /api/oauth/{provider}/callback?code=...&state=... — PKCE callback
- GET  /api/oauth/status — connection state per provider
- DELETE /api/oauth/{provider} — disconnect
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.services import oauth
from app.services.oauth import SPECS, PendingError
from app.services.oauth_store import oauth_store

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{provider}/start", tags=["OAuth"])
async def start_oauth(provider: str):
    """Begin an OAuth handshake for the named provider."""
    spec = SPECS.get(provider)
    if not spec:
        raise HTTPException(status_code=404, detail=f"Unknown OAuth provider '{provider}'")

    try:
        if spec.flow == "device_code":
            return await oauth.start_device_flow(spec)
        if spec.flow == "pkce":
            return await oauth.start_pkce_flow(spec)
        raise HTTPException(status_code=400, detail=f"Unsupported flow '{spec.flow}'")
    except Exception as e:
        logger.exception(f"OAuth start failed for {provider}")
        raise HTTPException(status_code=502, detail=f"OAuth start failed: {e}") from e


@router.get("/{provider}/poll", tags=["OAuth"])
async def poll_device(provider: str, state: str = Query(...)):
    """Poll a device-code flow. Returns 202 while pending, 200 when connected."""
    spec = SPECS.get(provider)
    if not spec or spec.flow != "device_code":
        raise HTTPException(status_code=400, detail="Not a device-code provider")

    try:
        await oauth.complete_device_flow(state)
        return {"provider": provider, "connected": True}
    except PendingError as e:
        raise HTTPException(
            status_code=202,
            detail={"status": e.code, "interval_hint": e.interval},
        ) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception(f"Device poll failed for {provider}")
        raise HTTPException(status_code=502, detail="OAuth poll failed") from e


@router.get("/{provider}/callback", tags=["OAuth"])
async def oauth_callback(provider: str, code: str = Query(...), state: str = Query(...)):
    """PKCE callback target — completes the exchange initiated by start."""
    spec = SPECS.get(provider)
    if not spec or spec.flow != "pkce":
        raise HTTPException(status_code=400, detail="Not a PKCE provider")

    try:
        await oauth.complete_pkce_flow(state, code)
        return {"provider": provider, "connected": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception(f"PKCE callback failed for {provider}")
        raise HTTPException(status_code=502, detail="OAuth callback failed") from e


@router.get("/status", tags=["OAuth"])
async def oauth_status():
    """Auth state per OAuth-backed provider."""
    return await oauth_store.list_connected()


@router.delete("/{provider}", tags=["OAuth"])
async def disconnect_oauth(provider: str):
    """Forget stored OAuth tokens for a provider."""
    deleted = await oauth_store.delete(provider)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' was not connected")
    return {"provider": provider, "disconnected": True}
