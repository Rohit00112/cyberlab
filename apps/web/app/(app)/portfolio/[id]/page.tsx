import { notFound } from "next/navigation";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { BadgeIcon } from "@/components/badges/badge-icon";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { serverApiGet } from "@/lib/api-server";

export const dynamic = "force-dynamic";

interface PortfolioData {
  id: string;
  display_name: string | null;
  created_at: string | null;
  points: number;
  solved_count: number;
  attempts: number;
  rank: number | null;
  recent_solves: {
    challenge_id: string;
    slug: string;
    title: string;
    points: number;
    skills: string[];
    solved_at: string;
  }[];
  earned_badges: {
    id: string;
    code: string;
    name: string;
    description: string | null;
    icon: string | null;
    skill_name: string | null;
    earned_at: string;
  }[];
  skills: {
    skill_id: string;
    name: string;
    score: number;
    confidence: number;
    solved_count: number;
  }[];
  verification_hash: string;
}

export default async function StudentPortfolioPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const res = await serverApiGet<PortfolioData>(`/users/${id}/portfolio`);

  if (!res.ok) {
    notFound();
  }

  const student = res.data;

  return (
    <>
            <div className="contents">
        {/* Verification Credential Banner */}
        <div className="rounded-xl border border-primary/30 bg-gradient-to-br from-primary/10 via-card to-background p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-xs font-semibold tracking-wider text-primary uppercase">
                  Verified CyberLab Cybersecurity Portfolio
                </span>
              </div>
              <h1 className="mt-2 text-3xl font-bold tracking-tight">
                {student.display_name ?? "Anonymous Student"}
              </h1>
              {student.created_at ? (
                <p className="mt-1 text-sm text-muted-foreground">
                  CyberLab Member since{" "}
                  {new Date(student.created_at).toLocaleDateString(undefined, {
                    month: "long",
                    year: "numeric",
                  })}
                </p>
              ) : null}
            </div>

            <div className="flex flex-col items-end gap-1.5">
              <span className="rounded bg-muted px-2.5 py-1 font-mono text-[11px] text-muted-foreground">
                VERIFIED HASH: #{student.verification_hash}
              </span>
              <span className="text-[10px] text-muted-foreground">
                Cryptographically validated against CyberLab state
              </span>
            </div>
          </div>
        </div>

        {/* Aggregate Stats */}
        <div className="mt-6 grid gap-4 sm:grid-cols-4">
          <Card>
            <CardContent className="pt-6">
              <p className="text-xs text-muted-foreground uppercase font-medium">Rank</p>
              <p className="mt-1 text-3xl font-bold tabular-nums text-primary">
                {student.rank ? `#${student.rank}` : "Unranked"}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-xs text-muted-foreground uppercase font-medium">Total Points</p>
              <p className="mt-1 text-3xl font-bold tabular-nums">
                {student.points.toLocaleString()}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-xs text-muted-foreground uppercase font-medium">Solves</p>
              <p className="mt-1 text-3xl font-bold tabular-nums">
                {student.solved_count}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-xs text-muted-foreground uppercase font-medium">Badges</p>
              <p className="mt-1 text-3xl font-bold tabular-nums">
                {student.earned_badges.length}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Skill Evidence & Competency */}
        <section className="mt-8 rounded-lg border p-6 bg-card">
          <h2 className="text-lg font-semibold">Skill Evidence & Mastery</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Brier-scored competency scores calculated across verified challenge categories.
          </p>

          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {student.skills.length === 0 ? (
              <p className="text-sm text-muted-foreground col-span-2">
                No skill profiles recorded yet.
              </p>
            ) : (
              student.skills.map((skill) => (
                <div key={skill.skill_id} className="space-y-1.5 rounded-md border p-3 bg-muted/20">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium">{skill.name}</span>
                    <span className="font-semibold tabular-nums text-primary">
                      {Math.round(skill.score * 100)}%
                    </span>
                  </div>
                  <Progress value={Math.round(skill.score * 100)} className="h-1.5" />
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-0.5">
                    <span>{skill.solved_count} challenge{skill.solved_count === 1 ? "" : "s"} solved</span>
                    <span>Confidence: {Math.round(skill.confidence * 100)}%</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        {/* Earned Badges */}
        <section className="mt-8">
          <h2 className="text-lg font-semibold">
            Unlocked Credentials & Badges ({student.earned_badges.length})
          </h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {student.earned_badges.length === 0 ? (
              <p className="text-sm text-muted-foreground col-span-3">
                No badges unlocked yet.
              </p>
            ) : (
              student.earned_badges.map((b) => (
                <div
                  key={b.id}
                  className="flex items-start gap-3 rounded-lg border bg-card p-3.5 shadow-xs"
                >
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                    <BadgeIcon badge={b} className="size-5.5" />
                  </div>
                  <div className="overflow-hidden">
                    <p className="font-medium text-sm truncate">{b.name}</p>
                    <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
                      {b.description ?? "CyberLab verified achievement"}
                    </p>
                    <p className="text-[10px] text-primary font-medium mt-1">
                      Unlocked {new Date(b.earned_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        {/* Verified Challenge Solves */}
        <section className="mt-8">
          <h2 className="text-lg font-semibold">
            Verified Challenge Solves ({student.recent_solves.length})
          </h2>
          <div className="mt-3 divide-y rounded-lg border overflow-hidden">
            {student.recent_solves.length === 0 ? (
              <div className="p-6 text-center text-sm text-muted-foreground">
                No solves on record.
              </div>
            ) : (
              student.recent_solves.map((solve) => (
                <div key={solve.challenge_id} className="flex items-center justify-between gap-4 p-4 bg-card">
                  <div>
                    <span className="font-medium text-sm">{solve.title}</span>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      {solve.skills.map((skill) => (
                        <Badge key={skill} variant="outline" className="text-[10px]">
                          {skill}
                        </Badge>
                      ))}
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <span className="font-semibold tabular-nums text-sm text-emerald-500">
                      +{solve.points} pts
                    </span>
                    <p className="text-[11px] text-muted-foreground">
                      {new Date(solve.solved_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <div className="mt-10 border-t pt-6 text-center text-xs text-muted-foreground">
          <p>
            Official student record issued by{" "}
            <Link href="/" className="font-medium underline">
              IIC CyberLab
            </Link>{" "}
            · Learn. Practice. Compete. Defend.
          </p>
        </div>
      </div>
    </>
  );
}
