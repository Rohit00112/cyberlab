"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { PageHeader } from "@/components/page-header";
import { RequireAuth } from "@/components/providers/require-auth";
import { useAuth } from "@/components/providers/auth-provider";
import { hasPermission } from "@/lib/auth/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { api } from "@/lib/api";
import { RecommendationCard } from "@/components/challenges/recommendation-card";
import type {
  ChallengeRecommendation,
  Lab,
  UserProfile,
  UserStats,
} from "@/lib/challenges/types";
import {
  ActivityIcon,
  ArrowRightIcon,
  AwardIcon,
  CrosshairIcon,
  FlaskConicalIcon,
  RadarIcon,
  SparklesIcon,
  TargetIcon,
  TrophyIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Announcement } from "@/lib/notifications/types";
import type { BadgeEarned } from "@/lib/badges/types";

function AnimatedNumber({ value }: { value: number }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    let frame = 0;
    const start = performance.now();
    const duration = 800;
    function step(now: number) {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(eased * value));
      if (progress < 1) frame = requestAnimationFrame(step);
    }
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return <>{display.toLocaleString()}</>;
}

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string;
  value: number | null;
  hint?: string;
  icon: typeof TargetIcon;
}) {
  return (
    <Card className="group relative overflow-hidden transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md dark:hover:shadow-[0_0_28px_-12px_var(--cyber)]">
      <div
        aria-hidden
        className="absolute -top-8 -right-8 size-24 rounded-full bg-primary/5 transition-transform duration-300 group-hover:scale-150"
      />
      <CardContent className="relative pt-6">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">{label}</p>
          <span className="grid size-8 place-items-center rounded-lg bg-primary/10 text-primary transition-colors [&_svg]:size-4">
            <Icon />
          </span>
        </div>
        <p className="mt-2 text-3xl font-bold tabular-nums">
          {value === null ? "—" : <AnimatedNumber value={value} />}
        </p>
        {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

function labRemainingFraction(lab: Lab) {
  if (!lab.expires_at || !lab.created_at) return null;
  const created = new Date(lab.created_at).getTime();
  const expires = new Date(lab.expires_at).getTime();
  const now = Date.now();
  if (expires <= now) return 0;
  if (expires <= created) return null;
  return Math.max(0.04, Math.min(1, (expires - now) / (expires - created)));
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState<UserStats | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [labs, setLabs] = useState<Lab[] | null>(null);
  const [recommendations, setRecommendations] = useState<ChallengeRecommendation[]>([]);
  const [announcement, setAnnouncement] = useState<Announcement | null>(null);
  const [dismissedAnn, setDismissedAnn] = useState(false);
  const [badges, setBadges] = useState<BadgeEarned[]>([]);

  useEffect(() => {
    api
      .get<UserStats>("/submissions/stats")
      .then(setStats)
      .catch(() => setStats(null));

    api
      .get<UserProfile>("/users/me")
      .then(setProfile)
      .catch(() => setProfile(null));

    if (hasPermission("lab.launch")) {
      api
        .get<Lab[]>("/labs")
        .then(setLabs)
        .catch(() => setLabs(null));
    }

    api
      .get<ChallengeRecommendation[]>("/recommendations/challenges?limit=6")
      .then(setRecommendations)
      .catch(() => setRecommendations([]));

    api
      .get<Announcement[]>("/announcements")
      .then((items) => {
        if (items && items.length > 0) setAnnouncement(items[0]);
      })
      .catch(() => setAnnouncement(null));

    api
      .get<BadgeEarned[]>("/badges/me")
      .then(setBadges)
      .catch(() => setBadges([]));
  }, []);

  const activeLabs = labs?.filter(
    (lab) => lab.status === "running" || lab.status === "provisioning"
  );

  const skillCounts = Array.from(
    new Set((profile?.recent_solves ?? []).flatMap((solve) => solve.skills))
  )
    .map((skill) => ({
      skill,
      count: (profile?.recent_solves ?? []).filter((s) => s.skills.includes(skill)).length,
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);
  const maxSkillCount = Math.max(...skillCounts.map((s) => s.count), 1);

  const initials = (user?.display_name ?? user?.email ?? "U")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");

  return (
    <RequireAuth>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        {announcement && !dismissedAnn ? (
          <div className="mb-6 flex items-start justify-between gap-4 rounded-xl border border-cyber/40 bg-gradient-to-r from-cyber/10 via-cyber/5 to-card p-4">
            <div className="flex items-start gap-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-cyber/15 text-cyber [&_svg]:size-4.5">
                <SparklesIcon />
              </span>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold tracking-wider text-cyber uppercase">
                    Platform notice
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {new Date(announcement.created_at).toLocaleDateString()}
                  </span>
                </div>
                <h3 className="mt-0.5 text-sm font-semibold">{announcement.title}</h3>
                <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                  {announcement.body}
                </p>
                <Link
                  href="/announcements"
                  className="mt-2 inline-block text-xs font-medium text-cyber hover:underline"
                >
                  Read full notice →
                </Link>
              </div>
            </div>
            <button
              onClick={() => setDismissedAnn(true)}
              className="text-xs text-muted-foreground hover:text-foreground"
              aria-label="Dismiss notice"
            >
              ✕
            </button>
          </div>
        ) : null}

        <PageHeader
          title={
            <span className="flex items-center gap-3">
              <span className="grid size-11 place-items-center rounded-xl bg-gradient-to-br from-cyber to-cyber-2 text-primary-foreground font-semibold shadow-[0_0_20px_-6px_var(--cyber)]">
                {initials || "U"}
              </span>
              <span>
                Welcome back, <span className="text-cyber-gradient">{user?.display_name ?? "student"}</span>
              </span>
            </span>
          }
          description="Your mission feed — resume where you left off."
        >
          <Button render={<Link href="/challenges" />}>
            Next challenge
            <ArrowRightIcon />
          </Button>
          <Button variant="outline" render={<Link href="/profile" />}>
            <AwardIcon />
            Profile
          </Button>
        </PageHeader>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Points" value={stats?.points ?? null} icon={TrophyIcon} hint="Total score" />
          <StatCard label="Solved" value={stats?.solved_count ?? null} icon={TargetIcon} hint="Challenges cracked" />
          <StatCard label="Attempts" value={stats?.attempts ?? null} icon={ActivityIcon} hint="Flag submissions" />
          <StatCard label="Badges" value={badges.length || null} icon={AwardIcon} hint="Achievements earned" />
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          {/* Active labs */}
          {activeLabs && activeLabs.length > 0 ? (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <FlaskConicalIcon className="size-4 text-primary" />
                    Active labs
                  </CardTitle>
                  <Link href="/labs" className="text-xs font-medium text-primary hover:underline">
                    Manage
                  </Link>
                </div>
                <CardDescription>Live environments with expiry timers</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {activeLabs.slice(0, 4).map((lab) => {
                  const remaining = labRemainingFraction(lab);
                  return (
                    <div key={lab.id}>
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">
                            {lab.challenge_title ?? lab.challenge_slug}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {lab.status === "provisioning"
                              ? "Booting container…"
                              : lab.expires_at
                                ? `Auto-expires at ${new Date(lab.expires_at).toLocaleTimeString()}`
                                : "No expiry set"}
                          </p>
                        </div>
                        <Badge
                          variant={lab.status === "running" ? "default" : "secondary"}
                          className="uppercase"
                        >
                          {lab.status}
                        </Badge>
                      </div>
                      {remaining !== null ? (
                        <Progress value={remaining * 100} className="mt-2 h-1.5" />
                      ) : null}
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          ) : labs ? (
            <Card className="border-dashed">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FlaskConicalIcon className="size-4 text-primary" />
                  Labs
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  No running labs. Launch a sandboxed environment from any lab challenge.
                </p>
                <Button className="mt-4" variant="outline" render={<Link href="/challenges" />}>
                  Start a lab
                  <ArrowRightIcon />
                </Button>
              </CardContent>
            </Card>
          ) : null}

          {/* Skills */}
          {skillCounts.length > 0 ? (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <RadarIcon className="size-4 text-primary" />
                    Skill radar
                  </CardTitle>
                  <Link href="/skills" className="text-xs font-medium text-primary hover:underline">
                    Full profile
                  </Link>
                </div>
                <CardDescription>Skills exercised by your recent solves</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {skillCounts.map(({ skill, count }) => (
                  <div key={skill}>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="font-medium">{skill}</span>
                      <span className="text-muted-foreground">
                        {count} {count === 1 ? "solve" : "solves"}
                      </span>
                    </div>
                    <Progress value={(count / maxSkillCount) * 100} className="h-2" />
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </div>

        {/* Badges */}
        {badges.length > 0 ? (
          <Card className="mt-6">
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <AwardIcon className="size-4 text-primary" />
                  Unlocked badges
                  <Badge variant="secondary" className="ml-1">
                    {badges.length}
                  </Badge>
                </CardTitle>
                <CardDescription>Shout-worthy milestones along your learning curve</CardDescription>
              </div>
              <Link href="/badges" className="text-xs font-medium text-primary hover:underline">
                All badges
              </Link>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {badges.slice(0, 6).map((b) => (
                <div
                  key={b.id}
                  className={cn(
                    "group rounded-xl border p-3 text-center transition-all duration-200",
                    "hover:-translate-y-0.5 hover:border-cyber/40 hover:shadow-[0_0_18px_-8px_var(--cyber)]"
                  )}
                >
                  <span className="text-3xl transition-transform group-hover:scale-110 inline-block">
                    {b.icon ?? "🏅"}
                  </span>
                  <p className="mt-2 truncate text-xs font-semibold">{b.name}</p>
                  <p className="mt-0.5 text-[10px] text-muted-foreground">
                    {new Date(b.earned_at).toLocaleDateString()}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        ) : null}

        {recommendations.length > 0 ? (
          <div className="mt-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 font-semibold">
                <CrosshairIcon className="size-4 text-primary" />
                Recommended next
              </h2>
              <Link href="/challenges" className="text-xs font-medium text-primary hover:underline">
                Browse all
              </Link>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {recommendations.map((rec) => (
                <RecommendationCard key={rec.challenge_id} recommendation={rec} />
              ))}
            </div>
          </div>
        ) : null}
      </main>
    </RequireAuth>
  );
}