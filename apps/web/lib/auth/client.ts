/**
 * Client-side session helpers. The access token lives only in memory
 * (module-level); refresh is handled by server routes using the httpOnly cookie.
 */
import type { Session, SessionUser } from "@/lib/auth/types";

let accessToken: string | null = null;
let user: SessionUser | null = null;

export function setSession(session: Session | null) {
  accessToken = session?.accessToken ?? null;
  user = session?.user ?? null;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getSessionUser(): SessionUser | null {
  return user;
}

export function getRoles(): string[] {
  return user?.roles ?? [];
}

export function hasAnyRole(...roles: string[]): boolean {
  return roles.some((role) => user?.roles.includes(role));
}

export function hasPermission(permission: string): boolean {
  return user?.permissions.includes("*") || (user?.permissions.includes(permission) ?? false);
}