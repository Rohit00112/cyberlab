import { redirect, notFound } from "next/navigation";
import Link from "next/link";

import { CompetitionAdminActions } from "@/components/admin/competition-actions";
import { CompetitionChallengePicker } from "@/components/admin/competition-challenge-picker";
import { CompetitionForm } from "@/components/admin/competition-form";
import { CompetitionStatusBadge } from "@/components/competitions/competition-status-badge";
import { Button } from "@/components/ui/button";
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { Challenge } from "@/lib/challenges/types";
import type { Competition } from "@/lib/competitions/types";

export const dynamic = "force-dynamic";

export default async function ManageCompetitionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "competition.manage")) redirect("/dashboard");

  const { id } = await params;
  const result = await serverApiGet<Competition>(`/competitions/${id}`);
  if (!result.ok) {
    if (result.status === 404) notFound();
    redirect("/auth/login");
  }
  const competition = result.data;

  const challengesResult = await serverApiGet<Challenge[]>("/challenges");
  const available = challengesResult.ok ? challengesResult.data : [];
  const fieldsLocked = ["live", "finished", "archived"].includes(competition.status);

  return (
    <>
            <div className="contents">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold">{competition.title}</h1>
            <CompetitionStatusBadge status={competition.status} />
          </div>
          <div className="flex items-center gap-2">
            <Link href={`/admin/competitions/${competition.id}/analytics`}>
              <Button variant="outline" size="sm">
                Analytics
              </Button>
            </Link>
            <Link href={`/competitions/${competition.id}`}>
              <Button variant="outline" size="sm">
                View public
              </Button>
            </Link>
          </div>
        </div>

        {competition.freeze_leaderboard ? (
          <p className="mt-2 text-sm text-amber-600">
            Leaderboard is frozen — new solves are not scored.
          </p>
        ) : null}
        <p className="mt-1 text-sm text-muted-foreground">
          {competition.participant_count} participants · {competition.team_count} teams
          · {competition.challenge_count} challenges
        </p>

        <section className="mt-6 rounded-lg border p-4">
          <h2 className="mb-2 font-medium">State machine</h2>
          <CompetitionAdminActions competition={competition} />
        </section>

        <section className="mt-6 rounded-lg border p-4">
          <h2 className="mb-2 font-medium">Challenges</h2>
          <CompetitionChallengePicker
            competitionId={competition.id}
            current={competition.challenges}
            available={available}
          />
        </section>

        <section className="mt-6 rounded-lg border p-4">
          <h2 className="mb-2 font-medium">Details</h2>
          {fieldsLocked ? (
            <p className="text-sm text-muted-foreground">
              This competition is live or finished — fields are locked.
            </p>
          ) : (
            <CompetitionForm
              mode="edit"
              competitionId={competition.id}
              initial={{
                title: competition.title,
                description: competition.description ?? "",
                rules: competition.rules ?? "",
                startAt: competition.start_at ?? "",
                endAt: competition.end_at ?? "",
                registrationEndsAt: competition.registration_ends_at ?? "",
                allowTeams: competition.allow_teams,
                maxTeamSize: competition.max_team_size,
                scoringMode: competition.scoring_mode,
              }}
            />
          )}
        </section>
      </div>
    </>
  );
}