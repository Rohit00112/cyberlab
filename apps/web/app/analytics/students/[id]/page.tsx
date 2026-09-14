import Link from "next/link";
import { redirect } from "next/navigation";

import { AppNav } from "@/components/app-nav";
import { Badge } from "@/components/ui/badge";
import { Progress, ProgressLabel } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { StudentAnalytics } from "@/lib/skills/types";

export const dynamic = "force-dynamic";

function StatCard({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-lg border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

export default async function StudentAnalyticsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "analytics.view")) redirect("/dashboard");

  const { id } = await params;
  const result = await serverApiGet<StudentAnalytics>(`/analytics/students/${id}`);
  if (!result.ok) {
    if (result.status === 404) redirect("/analytics");
    if (result.status === 403) redirect("/dashboard");
    redirect("/auth/login");
  }
  const student = result.data;

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <Link href="/analytics" className="text-sm text-muted-foreground hover:text-foreground">
          ← Analytics
        </Link>
        <h1 className="mt-3 text-2xl font-semibold">
          {student.display_name ?? "Student analytics"}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">{student.email ?? id}</p>

        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Points" value={student.total_points} />
          <StatCard label="Solved" value={student.solved_count} />
          <StatCard label="Attempts" value={student.attempts} />
          <StatCard label="Hint reveals" value={student.hint_reveals} />
        </div>

        <section className="mt-8 grid gap-8 lg:grid-cols-2">
          <div>
            <h2 className="text-lg font-semibold">Skills</h2>
            <div className="mt-4 space-y-4">
              {student.skills.length === 0 ? (
                <p className="text-muted-foreground">No skill evidence yet.</p>
              ) : (
                student.skills.map((skill) => (
                  <Progress key={skill.skill.id} value={skill.score} className="items-center gap-3">
                    <ProgressLabel className="shrink-0">
                      {skill.skill.name}
                      <span className="ml-1 text-xs font-normal text-muted-foreground">
                        {skill.solved_count} solve{skill.solved_count === 1 ? "" : "s"}
                      </span>
                    </ProgressLabel>
                    <span className="text-sm font-semibold tabular-nums">{skill.score}</span>
                  </Progress>
                ))
              )}
            </div>
          </div>
          <div>
            <h2 className="text-lg font-semibold">Badges</h2>
            <div className="mt-4 flex flex-wrap gap-2">
              {student.badges.length === 0 ? (
                <p className="text-muted-foreground">No badges earned yet.</p>
              ) : (
                student.badges.map((badge) => (
                  <Badge key={badge.code} variant="secondary" className="gap-1.5 px-3 py-1.5">
                    <span aria-hidden>{badge.icon ?? "🏅"}</span>
                    {badge.name}
                  </Badge>
                ))
              )}
            </div>
          </div>
        </section>

        <section className="mt-8">
          <h2 className="text-lg font-semibold">Challenge history</h2>
          <div className="mt-3">
            {student.challenges.length === 0 ? (
              <p className="text-muted-foreground">No challenge attempts yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Challenge</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead className="text-right">Points</TableHead>
                    <TableHead className="text-right">Attempts</TableHead>
                    <TableHead className="text-right">Hints</TableHead>
                    <TableHead className="text-right">Solved</TableHead>
                    <TableHead className="text-right">Solved at</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {student.challenges.map((challenge) => (
                    <TableRow key={challenge.challenge_id}>
                      <TableCell className="font-medium">
                        <Link href={`/challenges/${challenge.challenge_id}`} className="hover:underline">
                          {challenge.title}
                        </Link>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {challenge.category}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {challenge.earned_points}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{challenge.attempts}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {challenge.hints_revealed}
                      </TableCell>
                      <TableCell className="text-right">
                        {challenge.solved ? (
                          <span className="text-green-600">Yes</span>
                        ) : (
                          <span className="text-muted-foreground">No</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground tabular-nums">
                        {formatDate(challenge.solved_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </section>
      </main>
    </>
  );
}