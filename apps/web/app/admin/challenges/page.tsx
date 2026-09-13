import { redirect } from "next/navigation";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { ChallengeActions } from "@/components/admin/challenge-actions";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { Challenge } from "@/lib/challenges/types";
import { difficultyLabel, statusLabel } from "@/lib/challenges/types";

export const dynamic = "force-dynamic";

const STATUS_VARIANT: Record<string, "secondary" | "default" | "outline"> = {
  published: "default",
  draft: "secondary",
  archived: "outline",
};

export default async function AdminChallengesPage() {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "challenge.edit")) redirect("/dashboard");

  const result = await serverApiGet<Challenge[]>("/challenges?limit=200");
  if (!result.ok) redirect("/auth/login");
  const challenges = result.data;

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Challenge management</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Create, edit, publish, and archive the challenge catalogue.
            </p>
          </div>
          <Link href="/admin/challenges/new" className={buttonVariants()}>
            New challenge
          </Link>
        </div>

        <div className="mt-6">
          {challenges.length === 0 ? (
            <p className="text-muted-foreground">
              No challenges yet — create the first one.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Challenge</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Difficulty</TableHead>
                  <TableHead className="text-right">Points</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {challenges.map((challenge) => (
                  <TableRow key={challenge.id}>
                    <TableCell className="font-medium">
                      <Link
                        href={`/admin/challenges/${challenge.id}/edit`}
                        className="hover:underline"
                      >
                        {challenge.title}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {challenge.category}
                    </TableCell>
                    <TableCell>{difficultyLabel(challenge.difficulty)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {challenge.points}
                    </TableCell>
                    <TableCell>
                      <Badge variant={STATUS_VARIANT[challenge.status] ?? "secondary"}>
                        {statusLabel(challenge.status)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <ChallengeActions challenge={challenge} />
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