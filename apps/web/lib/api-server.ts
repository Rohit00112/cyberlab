/**
 * Server-side API access for RSC pages. Uses the user's httpOnly refresh cookie
 * to mint an access token, then talks to the API over the compose network.
 */
import { cookies } from "next/headers";

import { REFRESH_COOKIE, fetchMe, refreshTokenFlow } from "@/lib/auth/server";
import type { SessionUser } from "@/lib/auth/types";

const API_INTERNAL_BASE = process.env.API_INTERNAL_BASE ?? "http://api:8000/api/v1";

export type ServerApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number };

export async function serverApiGet<T>(path: string): Promise<ServerApiResult<T>> {
  const store = await cookies();
  const refreshToken = store.get(REFRESH_COOKIE)?.value;
  if (!refreshToken) return { ok: false, status: 401 };

  let accessToken: string;
  try {
    const tokens = await refreshTokenFlow(refreshToken);
    accessToken = tokens.access_token;
  } catch {
    return { ok: false, status: 401 };
  }

  const res = await fetch(`${API_INTERNAL_BASE}${path}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!res.ok) return { ok: false, status: res.status };
  return { ok: true, data: (await res.json()) as T };
}

/** Server-side session user (mints a token from the refresh cookie). */
export async function serverSessionUser(): Promise<SessionUser | null> {
  const store = await cookies();
  const refreshToken = store.get(REFRESH_COOKIE)?.value;
  if (!refreshToken) return null;
  try {
    const tokens = await refreshTokenFlow(refreshToken);
    return (await fetchMe(tokens.access_token)) as SessionUser;
  } catch {
    return null;
  }
}

/** Permission check helper for RSC pages ("*" grants everything). */
export function canServerUser(user: SessionUser | null, permission: string): boolean {
  return !!user && (user.permissions.includes("*") || user.permissions.includes(permission));
}