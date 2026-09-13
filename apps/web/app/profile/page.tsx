"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { RequireAuth } from "@/components/providers/require-auth";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { UserProfile } from "@/lib/challenges/types";

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="mt-1 text-3xl font-semibold tabular-nums">{value}</p>
      </CardContent>
    </Card>
  );
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);

  useEffect(() => {
    api
      .get<UserProfile>("/users/me")
      .then(setProfile)
      .catch(() => setProfile(null));
  }, []);

  return (
    <RequireAuth>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <div className="rounded-lg border bg-card p-6">
          <h1 className="text-2xl font-semibold">
            {profile?.display_name ?? "Profile"}
          </h1>
          <p className="mt-1 text-muted-foreground">{profile?.email}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {profile?.roles.map((role) => (
              <Badge key={role} variant="secondary">
                {role}
              </Badge>
            ))}
          </div>
          {profile?.created_at ? (
            <p className="mt-3 text-sm text-muted-foreground">
              Member since{" "}
              {new Date(profile.created_at).toLocaleDateString()}
            </p>
          ) : null}
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          <StatCard label="Points" value={profile?.points ?? 0} />
          <StatCard label="Solved" value={profile?.solved_count ?? 0} />
          <StatCard label="Attempts" value={profile?.attempts ?? 0} />
        </div>

        <div className="mt-6">
          <h2 className="text-lg font-semibold">Recent solves</h2>
          {profile && profile.recent_solves.length === 0 ? (
            <p className="mt-2 text-muted-foreground">
              No challenges solved yet.{" "}
              <Link href="/challenges" className="underline">
                Browse the catalogue
              </Link>
              .
            </p>
          ) : (
            <ul className="mt-3 divide-y rounded-lg border">
              {profile?.recent_solves.map((solve) => (
                <li key={solve.challenge_id} className="p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <Link
                        href={`/challenges/${solve.challenge_id}`}
                        className="font-medium hover:underline"
                      >
                        {solve.title}
                      </Link>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        {solve.skills.map((skill) => (
                          <Badge key={skill} variant="outline">
                            {skill}
                          </Badge>
                        ))}
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="font-semibold tabular-nums">+{solve.points}</p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(solve.solved_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>
    </RequireAuth>
  );
}