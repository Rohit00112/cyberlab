"use client";

import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/components/providers/auth-provider";

/**
 * Client-side route guard. Renders children only for authenticated users and
 * redirects unauthenticated visitors to /auth/login.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status, login } = useAuth();

  useEffect(() => {
    if (status === "unauthenticated") login();
  }, [status, login]);

  if (status !== "authenticated") {
    return (
      <main className="flex flex-1 items-center justify-center p-6">
        <p className="text-muted-foreground">Loading…</p>
      </main>
    );
  }

  return <>{children}</>;
}