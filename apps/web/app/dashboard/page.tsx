"use client";

import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { RequireAuth } from "@/components/providers/require-auth";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";

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
          Browse the catalogue to start working on challenges.
        </p>
        <div className="mt-4">
          <Link href="/challenges">
            <Button>Browse challenges</Button>
          </Link>
        </div>
      </main>
    </RequireAuth>
  );
}