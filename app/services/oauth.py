"""
OAuth 2.0 engine — PKCE and device-code flows for providers that don't
take static API keys (Kiro via AWS SSO OIDC, Antigravity via Google Cloud
Code, Gemini Code Assist via Google).

Client ids come from the public registrations used by the official CLIs
(Kiro CLI, Google Cloud Code).

State lives in Redis (shared across workers) with an in-memory fallback.
"""

import base64
import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass, field

import httpx

from app.services.oauth_store import oauth_store

logger = logging.getLogger(__name__)


# =============================================================================
# PKCE helpers
# =============================================================================

def pkce_pair() -> tuple[str, str]:
    """Return (verifier, S256 challenge) per RFC 7636."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def new_state() -> str:
    return secrets.token_urlsafe(24)


# =============================================================================
# Provider specs
# =============================================================================

@dataclass
class OAuthSpec:
    """Redirect/endpoint constants for one OAuth provider."""
    name: str
    flow: str                      # "pkce" | "device_code"
    authorize_url: str
    token_url: str
    client_id: str
    client_secret: str = ""        # public for native apps
    scopes: tuple[str, ...] = ()
    redirect_uri: str = ""
    extra_auth_params: dict = field(default_factory=dict)
    extra_token_params: dict = field(default_factory=dict)
    token_auth_method: str = "client_secret_post"  # Google native apps use body not basic


KIRO_SPEC = OAuthSpec(
    name="kiro",
    flow="device_code",
    authorize_url="https://oidc.us-east-1.amazonaws.com/device_authorization",
    token_url="https://oidc.us-east-1.amazonaws.com/token",
    client_id="",  # filled by client registration at flow start
    client_secret="",
    scopes=(
        "codewhisperer:completions",
        "codewhisperer:analysis",
        "codewhisperer:conversations",
    ),
)

ANTIGRAVITY_SPEC = OAuthSpec(
    name="antigravity",
    flow="pkce",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    # Defaults are the public Google Cloud Code client credentials for native
    # apps — Google documents these as distributable in source code. They are
    # still read from env so forks can register their own client.
    # See https://developers.google.com/identity/protocols/oauth2/native-app
    client_id=os.getenv(
        "ANTIGRAVITY_CLIENT_ID",
        "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com",
    ),
    client_secret=os.getenv("ANTIGRAVITY_CLIENT_SECRET", ""),
    scopes=(
        "openid",
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/cclog",
        "https://www.googleapis.com/auth/experimentsandconfigs",
    ),
    redirect_uri=os.getenv("ANTIGRAVITY_REDIRECT_URI", "http://localhost:8000/dashboard/oauth/callback"),
    extra_auth_params={"access_type": "offline", "prompt": "consent"},
)

SPECS: dict[str, OAuthSpec] = {s.name: s for s in (KIRO_SPEC, ANTIGRAVITY_SPEC)}


# =============================================================================
# Pending flow state
# =============================================================================


@dataclass
class PendingFlow:
    """One in-flight OAuth handshake waiting for the user to consent."""
    provider: str
    state: str
    verifier: str
    created_at: float = field(default_factory=time.time)
    device_code: str | None = None
    interval: int = 5


_pending: dict[str, PendingFlow] = {}  # state -> PendingFlow
_PENDING_TTL = 600  # 10 minutes


def _gc_pending():
    cutoff = time.time() - _PENDING_TTL
    for state in [s for s, f in _pending.items() if f.created_at < cutoff]:
        _pending.pop(state, None)


# =============================================================================
# PKCE flow (Google)
# =============================================================================

async def start_pkce_flow(spec: OAuthSpec) -> dict:
    """Build the authorization URL + stashed verifier for a PKCE flow."""
    verifier, challenge = pkce_pair()
    state = new_state()

    _gc_pending()
    _pending[state] = PendingFlow(provider=spec.name, state=state, verifier=verifier)

    from urllib.parse import urlencode
    params = {
        "client_id": spec.client_id,
        "redirect_uri": spec.redirect_uri,
        "response_type": "code",
        "scope": " ".join(spec.scopes),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        **spec.extra_auth_params,
    }
    auth_url = f"{spec.authorize_url}?{urlencode(params)}"

    return {
        "provider": spec.name,
        "flow": "pkce",
        "authUrl": auth_url,
        "state": state,
    }


async def complete_pkce_flow(state: str, code: str) -> dict:
    """Exchange the callback code for tokens and store them."""
    flow = _pending.pop(state, None)
    if not flow:
        raise ValueError("OAuth state not found or expired")

    spec = SPECS[flow.provider]

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": spec.client_id,
        "client_secret": spec.client_secret,
        "redirect_uri": spec.redirect_uri,
        "code_verifier": flow.verifier,
        **spec.extra_token_params,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            spec.token_url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if resp.status_code != 200:
        raise ValueError(f"token exchange failed: HTTP {resp.status_code} {resp.text[:300]}")

    data = resp.json()
    await _persist_tokens(spec.name, data)

    # Post-exchange: look up the project for Antigravity
    if spec.name == "antigravity":
        await _bootstrap_antigravity_project(data.get("access_token"))

    return {"provider": spec.name, "connected": True}


async def _bootstrap_antigravity_project(access_token: str) -> None:
    """Fetch the Cloud Code project id and email for the antigravity account."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
                json={"metadata": {"ideType": "ANTIGRAVITY", "pluginType": "GEMINI"}},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            body = resp.json()
            project = body.get("cloudaicompanionProject")
            stored = await oauth_store.get("antigravity") or {}
            stored_meta = stored.get("meta", {})
            stored_meta["project_id"] = project
            stored.setdefault("meta", {}).update(stored_meta)
            await oauth_store.save("antigravity", stored)
    except Exception as e:
        logger.warning(f"Antigravity project bootstrap failed: {e}")


# =============================================================================
# Device Code flow (Kiro / AWS SSO OIDC)
# =============================================================================

async def start_device_flow(spec: OAuthSpec) -> dict:
    """
    Start an AWS SSO OIDC device authorization:
    1. Register a transient public client.
    2. Request a device code.
    3. Return the verification URI + user code + polling info.
    """
    region = "us-east-1"
    oidc_base = f"https://oidc.{region}.amazonaws.com"

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Register a transient client
        reg_resp = await client.post(
            f"{oidc_base}/client/register",
            json={
                "clientName": f"my-gateway-{spec.name}",
                "clientType": "public",
                "scopes": list(spec.scopes),
                "grantTypes": [
                    "urn:ietf:params:oauth:grant-type:device_code",
                    "refresh_token",
                ],
            },
        )
        if reg_resp.status_code != 200:
            raise ValueError(f"client registration failed: {reg_resp.status_code} {reg_resp.text[:300]}")
        reg = reg_resp.json()
        client_id = reg["clientId"]
        client_secret = reg["clientSecret"]

        # 2. Start device authorization
        dev_resp = await client.post(
            f"{oidc_base}/device_authorization",
            json={
                "clientId": client_id,
                "clientSecret": client_secret,
                "startUrl": f"https://{region}.awsapps.com/start",
            },
        )
        if dev_resp.status_code != 200:
            raise ValueError(f"device authorization failed: {dev_resp.status_code} {dev_resp.text[:300]}")
        dev = dev_resp.json()

    state = new_state()
    _gc_pending()
    _pending[state] = PendingFlow(
        provider=spec.name,
        state=state,
        verifier="",
        device_code=dev["deviceCode"],
        interval=dev.get("interval", 5),
    )

    # Stash the transient client creds so the poller can finish the flow.
    _pending[state].verifier = f"{client_id}:{client_secret}"

    return {
        "provider": spec.name,
        "flow": "device_code",
        "verificationUri": dev["verificationUri"],
        "verificationUriComplete": dev.get("verificationUriComplete", dev["verificationUri"]),
        "userCode": dev["userCode"],
        "expiresIn": dev["expiresIn"],
        "interval": dev.get("interval", 5),
        "state": state,
    }


async def complete_device_flow(state: str) -> dict:
    """Poll OIDC /token until the user authorizes (caller retries on slow_down)."""
    flow = _pending.get(state)
    if not flow or not flow.device_code:
        raise ValueError("OAuth state not found or expired")

    spec = SPECS[flow.provider]
    client_id, client_secret = flow.verifier.split(":", 1)
    oidc_base = "https://oidc.us-east-1.amazonaws.com"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{oidc_base}/token",
            json={
                "clientId": client_id,
                "clientSecret": client_secret,
                "deviceCode": flow.device_code,
                "grantType": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )

    if resp.status_code == 400:
        # pending: slow_down / authorization_pending
        err = resp.json()
        code = err.get("error", "")
        if code in ("authorization_pending", "slow_down"):
            raise PendingError(code, interval=flow.interval)
        raise ValueError(f"token poll failed: {err}")

    resp.raise_for_status()
    _pending.pop(state, None)

    # AWS OIDC returns camelCase keys (accessToken/refreshToken/expiresIn)
    raw = resp.json()
    normalized = {
        "access_token": raw.get("accessToken") or raw.get("access_token"),
        "refresh_token": raw.get("refreshToken") or raw.get("refresh_token"),
        "expires_in": raw.get("expiresIn") or raw.get("expires_in", 3600),
        "scope": raw.get("scope", ""),
    }
    return await _persist_tokens(spec.name, normalized)


class PendingError(Exception):
    """Device flow not yet authorized — caller should keep polling."""

    def __init__(self, code: str, interval: int = 5):
        super().__init__(code)
        self.code = code
        self.interval = interval


async def refresh_token_flow(provider: str) -> dict:
    """Refresh an expired OAuth token using its refresh_token."""
    stored = await oauth_store.get(provider)
    if not stored or not stored.get("refresh_token"):
        raise ValueError(f"No refresh token for '{provider}'")

    spec = SPECS[provider]
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": stored["refresh_token"],
        "client_id": spec.client_id,
    }
    if spec.client_secret:
        payload["client_secret"] = spec.client_secret

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            spec.token_url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if resp.status_code != 200:
        raise ValueError(f"refresh failed: HTTP {resp.status_code}")

    data = resp.json()
    data.setdefault("refresh_token", stored["refresh_token"])
    return await _persist_tokens(provider, data)


async def _persist_tokens(provider: str, token_response: dict) -> dict:
    """Normalize a token response and store it."""
    expires_in = int(token_response.get("expires_in", 3600))
    record = {
        "access_token": token_response["access_token"],
        "refresh_token": token_response.get("refresh_token"),
        "expires_at": time.time() + expires_in,
        "scopes": token_response.get("scope", "").split() if token_response.get("scope") else [],
        "meta": {},
    }
    await oauth_store.save(provider, record)
    logger.info(f"OAuth tokens stored for '{provider}' (expires in {expires_in}s)")
    return record


async def get_valid_access_token(provider: str) -> str:
    """Return a fresh access token, refreshing when close to expiry."""
    stored = await oauth_store.get(provider)
    if not stored:
        raise ValueError(f"Provider '{provider}' is not connected - finish OAuth first")

    if await oauth_store.is_expired(provider):
        if stored.get("refresh_token"):
            stored = await refresh_token_flow(provider)
        else:
            raise ValueError(f"Token expired for '{provider}' and it has no refresh token")

    return stored["access_token"]
