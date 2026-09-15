import { redirect, notFound } from "next/navigation";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { CompetitionStatusBadge } from "@/components/competitions/competition-status-badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { CompetitionAnalytics } from "@/lib/competitions/types";

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

function formatMinutes(minutes?: number | null): string {
  if (minutes === null || minutes === undefined) return "—";
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hrs = Math.floor(minutes / 60);
  const rem = Math.round(minutes % 60);
  return `${hrs}h ${rem}m`;
}

export default async function CompetitionAnalyticsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "competition.manage")) redirect("/dashboard");

  const { id } = await params;
  const result = await serverApiGet<CompetitionAnalytics>(`/competitions/${id}/analytics`);
  if (!result.ok) {
    if (result.status === 404) notFound();
    redirect("/admin/competitions");
  }
  const analytics = result.data;

  const overallSolveRate =
    analytics.participant_count > 0 && analytics.per_challenge.length > 0
      ? ((analytics.total_solves / (analytics.participant_count * analytics.per_challenge.length)) * 100).toFixed(1)
      : "0.0";

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-5xl flex-1 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold">{analytics.title} · Analytics</h1>
            <CompetitionStatusBadge status={analytics.status} />
          </div>
          <div className="flex items-center gap-2">
            <Link href={`/admin/competitions/${analytics.competition_id}`}>
              <Button variant="outline" size="sm">
                Back to manage
              </Button>
            </Link>
            <Link href={`/competitions/${analytics.competition_id}`}>
              <Button variant="outline" size="sm">
                Public view
              </Button>
            </Link>
          </div>
        </div>

        <p className="mt-1 text-sm text-muted-foreground">
          Per-event solve rates, participant engagement, and score distribution (PRD §24).
        </p>

        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Total Participants" value={analytics.participant_count} />
          <StatCard label="Active Solvers" value={analytics.active_solvers} />
          <StatCard label="Total Solves" value={analytics.total_solves} />
          <StatCard label="Avg. Solve Rate" value={`${overallSolveRate}%`} />
        </div>

        <section className="mt-8 rounded-lg border p-4">
          <h2 className="text-lg font-semibold">Challenge Performance</h2>
          <div className="mt-3">
            {analytics.per_challenge.length === 0 ? (
              <p className="text-sm text-muted-foreground">No challenges configured yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Challenge</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead className="text-right">Points</TableHead>
                    <TableHead className="text-right">Solves</TableHead>
                    <TableHead className="text-right">Solve Rate</TableHead>
                    <TableHead className="text-right">First Solve</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {analytics.per_challenge.map((ch) => (
                    <TableRow key={ch.challenge_id}>
                      <TableCell className="font-medium">{ch.challenge_title}</TableCell>
                      <TableCell>{ch.category}</TableCell>
                      <TableCell className="text-right tabular-nums">{ch.points}</TableCell>
                      <TableCell className="text-right tabular-nums">{ch.solves}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {(ch.solve_rate * 100).toFixed(1)}%
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatMinutes(ch.time_to_first_solve_minutes)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </section>

        <section className="mt-8 rounded-lg border p-4">
          <h2 className="text-lg font-semibold">Score Distribution</h2>
          <div className="mt-3">
            {analytics.score_distribution.length === 0 ? (
              <p className="text-sm text-muted-foreground">No scores recorded yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Score Range</TableHead>
                    <TableHead className="text-right">Participants</TableHead>
                    <TableHead className="text-right">Percentage</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {analytics.score_distribution.map((b) => {
                    const pct =
                      analytics.participant_count > 0
                        ? ((b.count / analytics.participant_count) * 100).toFixed(1)
                        : "0.0";
                    return (
                      <TableRow key={b.range_label}>
                        <TableCell className="font-medium">{b.range_label}</TableCell>
                        <TableCell className="text-right tabular-nums">{b.count}</TableCell>
                        <TableCell className="text-right tabular-nums">{pct}%</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </div>
        </section>
      </main>
    </>
  );
}
