/**
 * Server-side OIDC helpers for the Keycloak authorization-code + PKCE flow.
 *
 * Networking note: the web container reaches Keycloak over the compose network
 * (KEYCLOAK_INTERNAL_ISSUER) while the browser uses the external issuer.
 * Discovered backchannel endpoints that reference the external host are
 * rewritten to the internal host.
 */
import { cookies } from "next/headers";
import crypto from "node:crypto";

import { generatePkcePair } from "@/lib/auth/pkce";

export const EXTERNAL_ISSUER = process.env.NEXT_PUBLIC_KEYCLOAK_ISSUER!;
export const INTERNAL_ISSUER = process.env.KEYCLOAK_INTERNAL_ISSUER!;
export const CLIENT_ID = process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID!;
export const WEB_ORIGIN = process.env.NEXT_PUBLIC_WEB_ORIGIN!;
export const REDIRECT_URI = `${WEB_ORIGIN}/auth/callback`;
export const REFRESH_COOKIE = "cyberlab_refresh";
export const STATE_COOKIE = "cyberlab_state";
export const PKCE_COOKIE = "cyberlab_pkce";

const API_INTERNAL_BASE = process.env.API_INTERNAL_BASE ?? "http://api:8000/api/v1";
const EXTERNAL_HOST = new URL(EXTERNAL_ISSUER).host;
const INTERNAL_HOST = new URL(INTERNAL_ISSUER).host;

export interface Discovery {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  end_session_endpoint?: string;
  jwks_uri: string;
}

let discoveryCache: { at: number; config: Discovery } | undefined;

async function getDiscovery(): Promise<Discovery> {
  if (discoveryCache && Date.now() - discoveryCache.at < 5 * 60_000) {
    return discoveryCache.config;
  }
  // Discovery is always fetched through the internal host (server-reachable).
  // With Keycloak strict hostname enabled, the returned endpoints still point
  // at the external frontend (localhost:8080), which is correct for the browser.
  const res = await fetch(`${INTERNAL_ISSUER}/.well-known/openid-configuration`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`OIDC discovery failed: ${res.status}`);
  const config = (await res.json()) as Discovery;
  discoveryCache = { at: Date.now(), config };
  return config;
}

/** Rewrite a discovered endpoint to the internal Keycloak host for server use. */
function toInternal(url: string): string {
  if (!url) return url;
  return url.replace(`//${EXTERNAL_HOST}`, `//${INTERNAL_HOST}`);
}

export async function buildLoginUrl(): Promise<{ url: string; state: string; verifier: string }> {
  const discovery = await getDiscovery();
  const { verifier, challenge } = generatePkcePair();
  const state = crypto.randomBytes(24).toString("base64url");
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    response_type: "code",
    scope: "openid profile email",
    state,
    code_challenge: challenge,
    code_challenge_method: "S256",
  });
  return { url: `${discovery.authorization_endpoint}?${params.toString()}`, state, verifier };
}

export async function exchangeCodeForTokens(
  code: string,
  verifier: string,
): Promise<Record<string, string>> {
  const discovery = await getDiscovery();
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: CLIENT_ID,
    code,
    redirect_uri: REDIRECT_URI,
    code_verifier: verifier,
  });
  const res = await fetch(toInternal(discovery.token_endpoint), {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Token exchange failed (${res.status})`);
  }
  return res.json();
}

export async function refreshTokenFlow(refreshToken: string): Promise<Record<string, string>> {
  const discovery = await getDiscovery();
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    client_id: CLIENT_ID,
    refresh_token: refreshToken,
  });
  const res = await fetch(toInternal(discovery.token_endpoint), {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Token refresh failed (${res.status})`);
  }
  return res.json();
}

export async function fetchMe(accessToken: string): Promise<unknown> {
  const res = await fetch(`${API_INTERNAL_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API /me failed (${res.status})`);
  return res.json();
}

export const cookieOptions = {
  httpOnly: true,
  sameSite: "lax" as const,
  secure: process.env.NODE_ENV === "production",
  path: "/",
};

export async function getRefreshToken(): Promise<string | undefined> {
  const store = await cookies();
  return store.get(REFRESH_COOKIE)?.value;
}

export async function setRefreshToken(token: string) {
  const store = await cookies();
  store.set(REFRESH_COOKIE, token, { ...cookieOptions, maxAge: 7 * 24 * 3600 });
}

export async function clearAuthCookies() {
  const store = await cookies();
  store.delete(REFRESH_COOKIE);
  store.delete(STATE_COOKIE);
  store.delete(PKCE_COOKIE);
}