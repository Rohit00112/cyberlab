"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { RequireAuth } from "@/components/providers/require-auth";
import { AnimatedNumber } from "@/components/motion/animated-number";
import { BadgeIcon } from "@/components/badges/badge-icon";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Progress,
  ProgressLabel,
} from "@/components/ui/progress";
import { api } from "@/lib/api";
import type { BadgeEarned, SkillOut, SkillProfile } from "@/lib/skills/types";
import { AwardIcon, StarIcon, TargetIcon } from "lucide-react";

const STAT_ICONS = [StarIcon, TargetIcon, AwardIcon];

function StatCard({ label, value, index }: { label: string; value: number; index: number }) {
  const Icon = STAT_ICONS[index % STAT_ICONS.length];
  return (
    <Card className="group relative overflow-hidden">
      <div aria-hidden className="absolute -top-8 -right-8 size-24 rounded-full bg-primary/5 transition-transform duration-300 group-hover:scale-150" />
      <CardContent className="relative pt-6">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">{label}</p>
          <span className="grid size-8 place-items-center rounded-lg bg-primary/10 text-primary [&_svg]:size-4">
            <Icon />
          </span>
        </div>
        <p className="mt-2 text-3xl font-bold tabular-nums">
          <AnimatedNumber value={value} />
        </p>
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
            <div className="contents">
        <div>
          <h1 className="text-2xl font-semibold">Skills &amp; badges</h1>
          <p className="mt-1 text-muted-foreground">
            Competency is scored from solved challenges weighted by difficulty.
          </p>
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          <StatCard label="Points" value={profile?.total_points ?? 0} index={0} />
          <StatCard label="Solved" value={profile?.solved_count ?? 0} index={1} />
          <StatCard label="Badges" value={badges.length} index={2} />
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
                      <BadgeIcon badge={badge} className="size-6 shrink-0" />
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
      </div>
    </RequireAuth>
  );
}