import { redirect } from "next/navigation";

import { AppNav } from "@/components/app-nav";
import { CompetitionStatusFilter } from "@/components/competitions/competition-status-filter";
import { CompetitionStatusBadge } from "@/components/competitions/competition-status-badge";
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
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Competitions</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Timed CTF events. Register before they start, solve challenges, climb
              the leaderboard.
            </p>
          </div>
          <CompetitionStatusFilter />
        </div>

        <div className="mt-6">
          {competitions.length === 0 ? (
            <p className="text-muted-foreground">
              No competitions yet. Check back soon.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Window</TableHead>
                  <TableHead>Challenges</TableHead>
                  <TableHead>Participants</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {competitions.map((competition) => (
                  <TableRow key={competition.id}>
                    <TableCell>
                      <a
                        href={`/competitions/${competition.id}`}
                        className="font-medium hover:underline"
                      >
                        {competition.title}
                      </a>
                      <p className="text-xs text-muted-foreground">
                        {competition.description ?? "No description"}
                      </p>
                    </TableCell>
                    <TableCell>
                      <CompetitionStatusBadge status={competition.status} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {competition.start_at && competition.end_at ? (
                        <>
                          {new Date(competition.start_at).toLocaleString()}
                          <br />
                          {new Date(competition.end_at).toLocaleString()}
                        </>
                      ) : (
                        "TBD"
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">
                        {competition.challenge_count}
                      </Badge>
                    </TableCell>
                    <TableCell>{competition.participant_count}</TableCell>
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