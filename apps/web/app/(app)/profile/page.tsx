"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { RequireAuth } from "@/components/providers/require-auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { UserProfile } from "@/lib/challenges/types";
import type { BadgeEarned } from "@/lib/badges/types";

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
  const [badges, setBadges] = useState<BadgeEarned[]>([]);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api
      .get<UserProfile>("/users/me")
      .then(setProfile)
      .catch(() => setProfile(null));

    api
      .get<BadgeEarned[]>("/badges/me")
      .then(setBadges)
      .catch(() => setBadges([]));
  }, []);

  function copyPortfolioLink() {
    if (!profile) return;
    const url = `${window.location.origin}/portfolio/${profile.id}`;
    navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <RequireAuth>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <div className="rounded-lg border bg-card p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
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

            {profile ? (
              <div className="flex flex-wrap items-center gap-2">
                <Link href={`/portfolio/${profile.id}`}>
                  <Button variant="outline" size="sm">
                    View Public Portfolio
                  </Button>
                </Link>
                <Button size="sm" onClick={copyPortfolioLink}>
                  {copied ? "Link Copied!" : "Share Portfolio"}
                </Button>
              </div>
            ) : null}
          </div>
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          <StatCard label="Points" value={profile?.points ?? 0} />
          <StatCard label="Solved" value={profile?.solved_count ?? 0} />
          <StatCard label="Attempts" value={profile?.attempts ?? 0} />
        </div>

        {/* Badges Showcase */}
        <div className="mt-8">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              Earned Badges ({badges.length})
            </h2>
            <Link href="/badges" className="text-sm text-primary hover:underline">
              View all available badges →
            </Link>
          </div>
          {badges.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">
              No badges unlocked yet. Solve challenges to earn your first badge!
            </p>
          ) : (
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {badges.map((b) => (
                <div
                  key={b.id}
                  className="flex items-center gap-3 rounded-lg border bg-card/60 p-3 shadow-xs"
                >
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-2xl">
                    {b.icon ?? "🏅"}
                  </div>
                  <div className="overflow-hidden">
                    <p className="font-medium text-sm truncate">{b.name}</p>
                    <p className="text-xs text-muted-foreground line-clamp-1">
                      {b.description ?? "Achievement unlocked"}
                    </p>
                    <p className="text-[10px] text-muted-foreground/80 mt-0.5">
                      Earned {new Date(b.earned_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Solves */}
        <div className="mt-8">
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