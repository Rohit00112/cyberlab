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
import type { LeaderboardEntry } from "@/lib/challenges/types";

export const dynamic = "force-dynamic";

export default async function LeaderboardPage() {
  const result = await serverApiGet<LeaderboardEntry[]>("/leaderboard");
  if (!result.ok) redirect("/auth/login");
  const entries = result.data;

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-4xl flex-1 p-6">
        <h1 className="text-2xl font-semibold">Leaderboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Ranked by total points; ties break on earliest solve.
        </p>
        <div className="mt-4">
          {entries.length === 0 ? (
            <p className="text-muted-foreground">
              No solves yet — be the first to crack a flag.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-14">Rank</TableHead>
                  <TableHead>Player</TableHead>
                  <TableHead className="text-right">Solved</TableHead>
                  <TableHead className="text-right">Points</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {entries.map((entry) => (
                  <TableRow key={entry.user_id}>
                    <TableCell className="font-mono tabular-nums">{entry.rank}</TableCell>
                    <TableCell className="font-medium">
                      {entry.display_name ?? "Anonymous"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{entry.solved_count}</TableCell>
                    <TableCell className="text-right font-semibold tabular-nums text-primary">
                      {entry.points}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </main>
    </>
  );
}