"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { RequireAuth } from "@/components/providers/require-auth";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Progress,
  ProgressLabel,
} from "@/components/ui/progress";
import { api } from "@/lib/api";
import type { BadgeEarned, SkillOut, SkillProfile } from "@/lib/skills/types";

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

export default function SkillsPage() {
  const [profile, setProfile] = useState<SkillProfile | null>(null);
  const [badges, setBadges] = useState<BadgeEarned[]>([]);
  const [taxonomy, setTaxonomy] = useState<SkillOut[]>([]);

  useEffect(() => {
    api
      .get<SkillProfile>("/skills/me")
      .then(setProfile)
      .catch(() => setProfile(null));
    api
      .get<BadgeEarned[]>("/badges/me")
      .then(setBadges)
      .catch(() => setBadges([]));
    api
      .get<SkillOut[]>("/skills")
      .then(setTaxonomy)
      .catch(() => setTaxonomy([]));
  }, []);

  const earned = profile?.skills.filter((s) => s.score > 0) ?? [];

  return (
    <RequireAuth>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <div>
          <h1 className="text-2xl font-semibold">Skills &amp; badges</h1>
          <p className="mt-1 text-muted-foreground">
            Competency is scored from solved challenges weighted by difficulty.
          </p>
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          <StatCard label="Points" value={profile?.total_points ?? 0} />
          <StatCard label="Solved" value={profile?.solved_count ?? 0} />
          <StatCard label="Badges" value={badges.length} />
        </div>

        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-lg">Skill competency</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 pt-0">
            {profile === null ? (
              <p className="text-muted-foreground">Loading…</p>
            ) : earned.length === 0 ? (
              <p className="text-muted-foreground">
                Solve challenges to build up your skill profile.{" "}
                <Link href="/challenges" className="underline">
                  Browse the catalogue
                </Link>
                .
              </p>
            ) : (
              earned.map((skill) => (
                <Progress key={skill.skill.id} value={skill.score} className="items-center gap-3">
                  <ProgressLabel className="w-44 shrink-0">
                    {skill.skill.name}
                    <span className="ml-1 text-xs font-normal text-muted-foreground">
                      {skill.solved_count} solve{skill.solved_count === 1 ? "" : "s"}
                    </span>
                  </ProgressLabel>
                  <span className="ml-auto text-sm text-muted-foreground tabular-nums">
                    {skill.score}
                  </span>
                </Progress>
              ))
            )}
          </CardContent>
        </Card>

        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-lg">Earned badges</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {badges.length === 0 ? (
              <p className="text-muted-foreground">
                No badges yet — keep solving challenges.
              </p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {badges.map((badge) => (
                  <div
                    key={badge.id}
                    className="rounded-lg border p-3 flex items-start gap-3"
                  >
                    <span className="text-2xl" aria-hidden>
                      {badge.icon ?? "🏅"}
                    </span>
                    <div className="min-w-0">
                      <p className="font-medium">{badge.name}</p>
                      {badge.description ? (
                        <p className="mt-0.5 text-sm text-muted-foreground">
                          {badge.description}
                        </p>
                      ) : null}
                      <p className="mt-1 text-xs text-muted-foreground">
                        Earned {new Date(badge.earned_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-lg">Skill taxonomy</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {taxonomy.length === 0 ? (
              <p className="text-muted-foreground">No skills defined yet.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {taxonomy.map((skill) => (
                  <Badge key={skill.id} variant="outline">
                    {skill.icon ? (
                      <span className="mr-1" aria-hidden>
                        {skill.icon}
                      </span>
                    ) : null}
                    {skill.name}
                    <span className="ml-1 text-muted-foreground">
                      {skill.challenge_count}
                    </span>
                  </Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </RequireAuth>
  );
}