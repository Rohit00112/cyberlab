import { redirect } from "next/navigation";

import { AppNav } from "@/components/app-nav";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { serverApiGet } from "@/lib/api-server";
import type { AnalyticsSummary, SubmissionReview } from "@/lib/challenges/types";

export const dynamic = "force-dynamic";

function StatCard({
  label,
  value,
  suffix,
}: {
  label: string;
  value: string | number;
  suffix?: string;
}) {
  return (
    <div className="rounded-lg border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">
        {value}
        {suffix ? <span className="text-base text-muted-foreground">{suffix}</span> : null}
      </p>
    </div>
  );
}

export default async function AnalyticsPage() {
  const [summaryResult, reviewResult] = await Promise.all([
    serverApiGet<AnalyticsSummary>("/analytics/summary"),
    serverApiGet<SubmissionReview[]>("/submissions/review?limit=20"),
  ]);
  const denied =
    (summaryResult.ok ? 0 : summaryResult.status) === 403 ||
    (reviewResult.ok ? 0 : reviewResult.status) === 403;
  if (!summaryResult.ok || !reviewResult.ok) {
    if (denied) redirect("/dashboard");
    redirect("/auth/login");
  }
  const summary = summaryResult.data;
  const submissions = reviewResult.data;

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <h1 className="text-2xl font-semibold">Faculty Analytics</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Platform-wide submission review and performance breakdown.
        </p>

        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Students" value={summary.total_users} />
          <StatCard label="Submissions" value={summary.total_submissions} />
          <StatCard label="Solves" value={summary.total_solves} />
          <StatCard
            label="Success rate"
            value={(summary.success_rate * 100).toFixed(1)}
            suffix="%"
          />
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <StatCard label="Points awarded" value={summary.total_points_awarded} />
        </div>

        <section className="mt-8">
          <h2 className="text-lg font-semibold">Recent submissions</h2>
          <div className="mt-3">
            {submissions.length === 0 ? (
              <p className="text-muted-foreground">
                No student submissions yet.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Student</TableHead>
                    <TableHead>Challenge</TableHead>
                    <TableHead className="text-right">Result</TableHead>
                    <TableHead className="text-right">Points</TableHead>
                    <TableHead className="text-right">Submitted</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {submissions.map((sub) => (
                    <TableRow key={sub.id}>
                      <TableCell className="font-medium">
                        {sub.display_name ?? "Anonymous"}
                      </TableCell>
                      <TableCell>{sub.challenge_title ?? sub.challenge_id}</TableCell>
                      <TableCell className="text-right">
                        {sub.is_correct ? (
                          <span className="text-green-600">Correct</span>
                        ) : (
                          <span className="text-destructive">Incorrect</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {sub.is_correct ? sub.earned_points : "—"}
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground tabular-nums">
                        {new Date(sub.created_at).toLocaleString()}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </section>

        <section className="mt-8 grid gap-8 lg:grid-cols-2">
          <div>
            <h2 className="text-lg font-semibold">Per-challenge performance</h2>
            <div className="mt-3">
              {summary.top_challenges.length === 0 ? (
                <p className="text-muted-foreground">No challenge activity yet.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Challenge</TableHead>
                      <TableHead className="text-right">Attempts</TableHead>
                      <TableHead className="text-right">Solves</TableHead>
                      <TableHead className="text-right">Rate</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {summary.top_challenges.map((row) => (
                      <TableRow key={row.challenge_id}>
                        <TableCell className="font-medium">{row.title}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          {row.attempts}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {row.solves}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {row.attempts
                            ? `${((row.solves / row.attempts) * 100).toFixed(0)}%`
                            : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          </div>
          <div>
            <h2 className="text-lg font-semibold">Top students</h2>
            <div className="mt-3">
              {summary.top_students.length === 0 ? (
                <p className="text-muted-foreground">No solves yet.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-14">Rank</TableHead>
                      <TableHead>Student</TableHead>
                      <TableHead className="text-right">Solved</TableHead>
                      <TableHead className="text-right">Points</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {summary.top_students.map((row) => (
                      <TableRow key={row.user_id}>
                        <TableCell className="font-mono tabular-nums">
                          {row.rank}
                        </TableCell>
                        <TableCell className="font-medium">
                          {row.display_name ?? "Anonymous"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {row.solved_count}
                        </TableCell>
                        <TableCell className="text-right font-semibold tabular-nums text-primary">
                          {row.points}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          </div>
        </section>
      </main>
    </>
  );
}