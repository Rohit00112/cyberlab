"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { setAccessToken, setSession } from "@/lib/auth/client";
import type { Session, SessionUser } from "@/lib/auth/types";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: SessionUser | null;
  login: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  status: "loading",
  user: null,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<SessionUser | null>(null);

  useEffect(() => {
    let active = true;
    fetch("/api/auth/session")
      .then(async (res) => {
        if (!active) return;
        if (res.ok) {
          const session = (await res.json()) as Session;
          setSession(session);
          setUser(session.user);
          setStatus("authenticated");
        } else {
          setSession(null);
          setStatus("unauthenticated");
        }
      })
      .catch(() => {
        if (!active) return;
        setSession(null);
        setStatus("unauthenticated");
      });
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(() => {
    setAccessToken(null);
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full-page nav starts the OIDC/PKCE flow
    window.location.assign(`${window.location.origin}/auth/login`);
  }, []);

  const logout = useCallback(() => {
    setAccessToken(null);
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full-page nav needed to clear cookies
    window.location.assign(`${window.location.origin}/auth/logout`);
  }, []);

  return (
    <AuthContext.Provider value={{ status, user, login, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}