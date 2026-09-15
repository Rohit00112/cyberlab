import { redirect } from "next/navigation";

import { LeaderboardTable } from "@/components/leaderboard/leaderboard-table";
import { serverApiGet } from "@/lib/api-server";
import type { LeaderboardEntry } from "@/lib/challenges/types";

export const dynamic = "force-dynamic";

export default async function LeaderboardPage() {
  const result = await serverApiGet<LeaderboardEntry[]>("/leaderboard");
  if (!result.ok) redirect("/auth/login");
  const entries = result.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Leaderboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Ranked by total points; ties break on earliest solve.
        </p>
      </div>

      {entries.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-16 text-center">
          <p className="text-sm font-medium">No solves yet</p>
          <p className="mt-1 text-sm text-muted-foreground">Be the first to crack a flag.</p>
        </div>
      ) : (
        <LeaderboardTable entries={entries} />
      )}
    </div>
  );
}