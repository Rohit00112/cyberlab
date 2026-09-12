/**
 * Browser fetch wrapper for the IIC CyberLab API.
 * - attaches the in-memory access token
 * - on 401, refreshes once via the server route and retries
 */
import { getAccessToken, setAccessToken } from "@/lib/auth/client";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  detail?: string;
  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

interface ApiOptions extends RequestInit {
  authenticated?: boolean;
  token?: string | null;
}

async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { authenticated = true, token, headers, ...rest } = options;
  const resolveToken = token !== undefined ? token : getAccessToken();

  const run = (tok: string | null) =>
    fetch(`${API_BASE}${path}`, {
      ...rest,
      headers: {
        "content-type": "application/json",
        ...(authenticated && tok ? { Authorization: `Bearer ${tok}` } : {}),
        ...headers,
      },
    });

  let res = await run(resolveToken);

  if (res.status === 401 && authenticated) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      res = await run(refreshed);
    }
  }

  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : undefined;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail || `Request failed (${res.status})`, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function refreshAccessToken(): Promise<string | null> {
  try {
    const res = await fetch("/api/auth/refresh", { method: "POST" });
    if (!res.ok) return null;
    const data = await res.json();
    setAccessToken(data.accessToken);
    return data.accessToken;
  } catch {
    return null;
  }
}

export const api = {
  get: <T>(path: string, options?: ApiOptions) => apiFetch<T>(path, options),
  post: <T>(path: string, body?: unknown, options?: ApiOptions) =>
    apiFetch<T>(path, { ...options, method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown, options?: ApiOptions) =>
    apiFetch<T>(path, { ...options, method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string, options?: ApiOptions) =>
    apiFetch<T>(path, { ...options, method: "DELETE" }),
};