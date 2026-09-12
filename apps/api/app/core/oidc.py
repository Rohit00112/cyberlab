"""OIDC discovery and JWT verification against Keycloak.

The issuer that tokens declare is ``settings.oidc_issuer_url`` (the externally
reachable Keycloak URL, e.g. ``http://localhost:8080/realms/cyberlab``). Server-
to-server requests (well-known, JWKS) go through ``settings.oidc_well_known_url``,
which may point at the internal host. Any discovered endpoint that references the
external frontend URL is rewritten to the internal host for server-side use.
"""
from __future__ import annotations

import time

import httpx
import jwt

from app.core.config import get_settings

settings = get_settings()

ALLOWED_AUDIENCES = {"api", "web"}
_GRACE_AUDIENCES = {"account"}
_CACHE_TTL = 300
_NETWORK_TIMEOUT = 5.0


class OidcProvider:
    def __init__(self) -> None:
        self._well_known: dict = {}
        self._jwks = None
        self._well_known_at = 0.0
        self._jwks_at = 0.0
        self._external_base = settings.oidc_issuer_url.rstrip("/")
        well_known = settings.oidc_well_known_url
        suffix = "/.well-known/openid-configuration"
        self._internal_base = well_known[: -len(suffix)] if well_known.endswith(suffix) else well_known

    def _internal(self, url: str) -> str:
        if not url or self._external_base not in url:
            return url
        return url.replace(self._external_base, self._internal_base)

    async def _config(self) -> dict:
        if not self._well_known or time.time() - self._well_known_at > _CACHE_TTL:
            async with httpx.AsyncClient(timeout=_NETWORK_TIMEOUT) as client:
                resp = await client.get(settings.oidc_well_known_url)
                resp.raise_for_status()
                self._well_known = resp.json()
                self._well_known_at = time.time()
        return self._well_known

    async def _jwkset(self):
        if self._jwks is None or time.time() - self._jwks_at > _CACHE_TTL:
            config = await self._config()
            jwks_url = self._internal(config["jwks_uri"])
            async with httpx.AsyncClient(timeout=_NETWORK_TIMEOUT) as client:
                resp = await client.get(jwks_url)
                resp.raise_for_status()
                self._jwks = jwt.PyJWKSet.from_dict(resp.json())
                self._jwks_at = time.time()
        return self._jwks

    async def decode_token(self, token: str) -> dict:
        """Verify signature, issuer and (where present) audience."""
        jwks = await self._jwkset()
        try:
            return self._verify(token, jwks)
        except jwt.PyJWTError:
            # refresh cached keys once in case of rotation
            self._jwks = None
            return self._verify(token, await self._jwkset())

    def _verify(self, token: str, jwks) -> dict:
        header = jwt.get_unverified_header(token)
        jwk = next((k for k in jwks.keys if k.key_id == header.get("kid")), jwks.keys[0])
        claims = jwt.decode(
            token,
            key=jwk.key,
            algorithms=["RS256"],
            issuer=settings.oidc_issuer_url,
            options={"verify_aud": False},
        )
        aud = claims.get("aud")
        if aud is not None:
            audiences = [aud] if isinstance(aud, str) else aud
            if not (ALLOWED_AUDIENCES | _GRACE_AUDIENCES) & set(audiences):
                raise jwt.InvalidAudienceError("Unexpected token audience")
        return claims


oidc = OidcProvider()