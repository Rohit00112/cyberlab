"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { RequireAuth } from "@/components/providers/require-auth";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { UserStats } from "@/lib/challenges/types";

function StatCard({
  label,
  value,
  suffix,
}: {
  label: string;
  value: number | null;
  suffix?: string;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="mt-1 text-3xl font-semibold tabular-nums">
          {value === null ? "—" : `${value}${suffix ?? ""}`}
        </p>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState<UserStats | null>(null);

  useEffect(() => {
    api
      .get<UserStats>("/submissions/stats")
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

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
        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          <StatCard label="Points" value={stats?.points ?? null} />
          <StatCard label="Solved" value={stats?.solved_count ?? null} />
          <StatCard label="Attempts" value={stats?.attempts ?? null} />
        </div>
        <div className="mt-6 flex gap-3">
          <Link href="/challenges">
            <Button>Browse challenges</Button>
          </Link>
          <Link href="/leaderboard">
            <Button variant="outline">View leaderboard</Button>
          </Link>
        </div>
      </main>
    </RequireAuth>
  );
}