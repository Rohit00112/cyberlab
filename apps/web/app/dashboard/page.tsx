"use client";

import { AppNav } from "@/components/app-nav";
import { RequireAuth } from "@/components/providers/require-auth";
import { useAuth } from "@/components/providers/auth-provider";

export default function DashboardPage() {
  const { user } = useAuth();

  return (
    <RequireAuth>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <h1 className="text-2xl font-semibold">
          Welcome, {user?.display_name ?? "student"}
        </h1>
        <p className="mt-2 text-muted-foreground">
          Dashboard content arrives with the challenge catalogue (Stage 3/6).
        </p>
      </main>
    </RequireAuth>
  );
}