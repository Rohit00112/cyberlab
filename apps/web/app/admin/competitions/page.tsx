import Link from "next/link";
import { redirect } from "next/navigation";

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
import type { CompetitionSummary } from "@/lib/competitions/types";

export const dynamic = "force-dynamic";

export default async function AdminCompetitionsPage() {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "competition.manage")) redirect("/dashboard");

  const result = await serverApiGet<CompetitionSummary[]>("/competitions");
  if (!result.ok) redirect("/auth/login");
  const competitions = result.data;

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">Competition management</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Create events, attach challenges, drive the state machine, freeze
              leaderboards.
            </p>
          </div>
          <Link href="/admin/competitions/new">
            <Button>New competition</Button>
          </Link>
        </div>

        <div className="mt-6">
          {competitions.length === 0 ? (
            <p className="text-muted-foreground">No competitions yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Window</TableHead>
                  <TableHead>Challenges</TableHead>
                  <TableHead>Participants</TableHead>
                  <TableHead className="text-right">Manage</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {competitions.map((competition) => (
                  <TableRow key={competition.id}>
                    <TableCell className="font-medium">
                      {competition.title}
                      <p className="text-xs font-normal text-muted-foreground">
                        {competition.slug}
                      </p>
                    </TableCell>
                    <TableCell>
                      <CompetitionStatusBadge status={competition.status} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {competition.start_at
                        ? new Date(competition.start_at).toLocaleString()
                        : "TBD"}
                    </TableCell>
                    <TableCell>{competition.challenge_count}</TableCell>
                    <TableCell>{competition.participant_count}</TableCell>
                    <TableCell className="text-right">
                      <Link href={`/admin/competitions/${competition.id}`}>
                        <Button variant="outline" size="sm">
                          Manage
                        </Button>
                      </Link>
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