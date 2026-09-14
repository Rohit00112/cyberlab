import { redirect, notFound } from "next/navigation";

import { AppNav } from "@/components/app-nav";
import { CompetitionLeaderboard } from "@/components/competitions/leaderboard";
import { CompetitionRegisterCard } from "@/components/competitions/register-card";
import { CompetitionStatusBadge } from "@/components/competitions/competition-status-badge";
import { CompetitionCountdown } from "@/components/competitions/countdown";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { Competition, LeaderboardEntry } from "@/lib/competitions/types";

export const dynamic = "force-dynamic";

export default async function CompetitionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");

  const { id } = await params;
  const result = await serverApiGet<Competition>(`/competitions/${id}`);
  if (!result.ok) {
    if (result.status === 404) notFound();
    redirect("/auth/login");
  }
  const competition = result.data;

  const leaderboardResult = await serverApiGet<{ items: LeaderboardEntry[] }>(
    `/competitions/${id}/leaderboard`,
  );
  const leaderboard = leaderboardResult.ok
    ? leaderboardResult.data.items
    : [];

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold">{competition.title}</h1>
              <CompetitionStatusBadge status={competition.status} />
              {competition.freeze_leaderboard ? (
                <Badge variant="outline">Leaderboard frozen</Badge>
              ) : null}
            </div>
            {competition.description ? (
              <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                {competition.description}
              </p>
            ) : null}
            <div className="mt-3">
              <CompetitionCountdown
                status={competition.status}
                startAt={competition.start_at}
                endAt={competition.end_at}
              />
            </div>
          </div>
          <dl className="text-sm">
            <div className="flex justify-between gap-6">
              <dt className="text-muted-foreground">Starts</dt>
              <dd className="tabular-nums">
                {competition.start_at
                  ? new Date(competition.start_at).toLocaleString()
                  : "TBD"}
              </dd>
            </div>
            <div className="flex justify-between gap-6">
              <dt className="text-muted-foreground">Ends</dt>
              <dd className="tabular-nums">
                {competition.end_at
                  ? new Date(competition.end_at).toLocaleString()
                  : "TBD"}
              </dd>
            </div>
            <div className="flex justify-between gap-6">
              <dt className="text-muted-foreground">Registration</dt>
              <dd className="tabular-nums">
                {competition.registration_ends_at
                  ? new Date(competition.registration_ends_at).toLocaleString()
                  : "Open while scheduling"}
              </dd>
            </div>
            <div className="flex justify-between gap-6">
              <dt className="text-muted-foreground">Mode</dt>
              <dd>{competition.allow_teams ? "Teams" : "Solo"}</dd>
            </div>
          </dl>
        </div>

        {competition.rules ? (
          <div className="mt-6 rounded-lg border p-4">
            <h2 className="font-medium">Rules</h2>
            <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">
              {competition.rules}
            </p>
          </div>
        ) : null}

        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <section className="space-y-4">
            <CompetitionRegisterCard competition={competition} />
            <div className="rounded-lg border p-4">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-medium">
                  Challenges ({competition.challenge_count})
                </h2>
              </div>
              {competition.challenges.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No challenges attached yet.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Title</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead className="text-right">Points</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {competition.challenges.map((entry) => (
                      <TableRow key={entry.challenge.id}>
                        <TableCell className="font-medium">
                          {entry.challenge.title}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {entry.challenge.category}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {entry.points ?? entry.challenge.points}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          </section>

          <section>
            <div className="rounded-lg border p-4">
              <h2 className="mb-3 font-medium">Leaderboard</h2>
              <CompetitionLeaderboard
                competitionId={competition.id}
                initial={leaderboard}
              />
            </div>
          </section>
        </div>
      </main>
    </>
  );
}