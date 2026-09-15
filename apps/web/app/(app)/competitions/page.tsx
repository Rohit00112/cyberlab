import { redirect } from "next/navigation";

import { CompetitionCard } from "@/components/competitions/competition-card";
import { CompetitionStatusFilter } from "@/components/competitions/competition-status-filter";
import { serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { CompetitionSummary } from "@/lib/competitions/types";

export const dynamic = "force-dynamic";

export default async function CompetitionsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");

  const { status } = await searchParams;
  const path = `/competitions${status ? `?status_filter=${encodeURIComponent(status)}` : ""}`;
  const result = await serverApiGet<CompetitionSummary[]>(path);
  if (!result.ok) redirect("/auth/login");
  const competitions = result.data;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Competitions</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Timed CTF events. Register before they start, solve, and climb the leaderboard.
          </p>
        </div>
        <CompetitionStatusFilter />
      </div>

      {competitions.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-16 text-center">
          <p className="text-sm font-medium">No competitions yet</p>
          <p className="mt-1 text-sm text-muted-foreground">Check back soon — the next event is being prepared.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {competitions.map((competition) => (
            <CompetitionCard key={competition.id} competition={competition} />
          ))}
        </div>
      )}
    </div>
  );
}