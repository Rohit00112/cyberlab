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
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { ResearchMetrics } from "@/lib/research/types";

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

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
}

function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export default async function ResearchInsightsPage() {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "analytics.research")) redirect("/dashboard");

  const result = await serverApiGet<ResearchMetrics>("/research/metrics");
  if (!result.ok) redirect("/auth/login");
  const metrics = result.data;

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <div>
          <h1 className="text-2xl font-semibold">Research insights</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Platform-wide research metrics (PRD §71). Generated{" "}
            {new Date(metrics.generated_at).toLocaleString()}.
          </p>
        </div>

        <h2 className="mt-8 text-lg font-semibold">Learning</h2>
        <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Assessed students" value={metrics.learning.assessed_users} />
          <StatCard label="Completion rate" value={percent(metrics.learning.completion_rate)} />
          <StatCard label="Avg. skill delta" value={metrics.learning.avg_skill_delta} />
          <StatCard label="Retention" value={percent(metrics.learning.retention_rate)} />
        </div>

        <h2 className="mt-8 text-lg font-semibold">Engagement</h2>
        <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Weekly active users" value={metrics.engagement.weekly_active_users} />
          <StatCard label="Challenges attempted" value={metrics.engagement.challenges_attempted} />
          <StatCard label="Hints used" value={metrics.engagement.hints_used} />
          <StatCard
            label="Median return"
            value={metrics.engagement.median_return_days ?? "—"}
            suffix={metrics.engagement.median_return_days !== null ? " days" : undefined}
          />
        </div>

        <h2 className="mt-8 text-lg font-semibold">Recommendation quality</h2>
        <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Served" value={metrics.recommendations.served} />
          <StatCard label="Accepted" value={metrics.recommendations.accepted} />
          <StatCard label="Solved" value={metrics.recommendations.solved} />
          <StatCard
            label="Completion rate"
            value={percent(metrics.recommendations.completion_rate)}
          />
        </div>

        {metrics.recommendations.per_source && metrics.recommendations.per_source.length > 0 ? (
          <div className="mt-4">
            <h3 className="text-sm font-medium text-muted-foreground">Per-backend breakdown</h3>
            <Table className="mt-2">
              <TableHeader>
                <TableRow>
                  <TableHead>Backend</TableHead>
                  <TableHead className="text-right">Served</TableHead>
                  <TableHead className="text-right">Accepted</TableHead>
                  <TableHead className="text-right">Solved</TableHead>
                  <TableHead className="text-right">Acceptance rate</TableHead>
                  <TableHead className="text-right">Completion rate</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {metrics.recommendations.per_source.map((src) => (
                  <TableRow key={src.source}>
                    <TableCell className="font-mono font-medium">{src.source}</TableCell>
                    <TableCell className="text-right tabular-nums">{src.served}</TableCell>
                    <TableCell className="text-right tabular-nums">{src.accepted}</TableCell>
                    <TableCell className="text-right tabular-nums">{src.solved}</TableCell>
                    <TableCell className="text-right tabular-nums">{percent(src.acceptance_rate)}</TableCell>
                    <TableCell className="text-right tabular-nums">{percent(src.completion_rate)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}

        <section className="mt-8">
          <h2 className="text-lg font-semibold">Challenge quality</h2>
          <div className="mt-3">
            {metrics.challenge_quality.length === 0 ? (
              <p className="text-muted-foreground">No published challenges yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Challenge</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead className="text-right">Success rate</TableHead>
                    <TableHead className="text-right">Median solve time</TableHead>
                    <TableHead className="text-right">Abandonment</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {metrics.challenge_quality.map((row) => (
                    <TableRow key={row.challenge_id}>
                      <TableCell className="font-medium">{row.title}</TableCell>
                      <TableCell>{row.slug.split("_")[0] ?? row.slug}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {percent(row.success_rate)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatDuration(row.median_solve_seconds)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {percent(row.abandonment_rate)}
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